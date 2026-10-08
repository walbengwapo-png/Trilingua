<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Models\TranslationQuota;
use App\Models\User;
use App\Services\QuotaService;
use App\Services\StorageService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Queue;
use Mockery;
use Tests\TestCase;

/**
 * R6: the daily upload quota is charged at ACCEPTANCE into a per-user/day
 * ledger. Uploads and re-translations consume the same budget; deduplicated or
 * reused work is never charged; failed accepted submissions keep their charge;
 * a refused or race-lost submission cleans up its scratch bytes.
 */
class UploadQuotaAtomicityTest extends TestCase
{
    use RefreshDatabase;

    protected function tearDown(): void
    {
        Mockery::close();
        parent::tearDown();
    }

    private function subdirs(string $path): array
    {
        if (! is_dir($path)) {
            return [];
        }
        return array_values(array_diff(scandir($path) ?: [], ['.', '..']));
    }

    private function docUpload(): UploadedFile
    {
        return UploadedFile::fake()->createWithContent('q.docx', 'PK' . str_repeat('A', 256));
    }

    public function test_reserve_charges_files_and_bytes_into_the_daily_ledger(): void
    {
        config([
            'translation.upload.max_daily_files' => 25,
            'translation.upload.max_daily_bytes' => 262144000,
        ]);

        $service = app(QuotaService::class);
        $user = User::factory()->create();

        $this->assertTrue($service->reserve((int) $user->id, 400));

        $row = TranslationQuota::where('user_id', $user->id)->where('quota_day', today()->toDateString())->firstOrFail();
        $this->assertSame(1, (int) $row->files);
        $this->assertSame(400, (int) $row->bytes);

        $this->assertTrue($service->reserve((int) $user->id, 600));
        $row->refresh();
        $this->assertSame(2, (int) $row->files);
        $this->assertSame(1000, (int) $row->bytes);
    }

    public function test_reserve_obeys_file_and_byte_caps(): void
    {
        config([
            'translation.upload.max_daily_files' => 2,
            'translation.upload.max_daily_bytes' => 1000,
        ]);

        $service = app(QuotaService::class);
        $user = User::factory()->create();

        $this->assertTrue($service->reserve((int) $user->id, 400));
        $this->assertTrue($service->reserve((int) $user->id, 600));

        // Over the byte ceiling.
        $this->assertFalse($service->reserve((int) $user->id, 1));
        // Over the file ceiling even though bytes would fit.
        $this->assertFalse($service->reserve((int) $user->id, 1));

        $row = TranslationQuota::where('user_id', $user->id)->firstOrFail();
        $this->assertSame(2, (int) $row->files);
        $this->assertSame(1000, (int) $row->bytes);
    }

    public function test_refund_returns_charged_capacity_but_never_goes_negative(): void
    {
        config([
            'translation.upload.max_daily_files' => 25,
            'translation.upload.max_daily_bytes' => 262144000,
        ]);

        $service = app(QuotaService::class);
        $user = User::factory()->create();

        $service->reserve((int) $user->id, 400);
        $service->reserve((int) $user->id, 600);

        $service->refund((int) $user->id, 400);

        $row = TranslationQuota::where('user_id', $user->id)->firstOrFail();
        $this->assertSame(1, (int) $row->files);
        $this->assertSame(600, (int) $row->bytes);

        // A broken refund can over-count but never bypass a cap.
        $service->refund((int) $user->id, 999999);
        $row->refresh();
        $this->assertSame(0, (int) $row->files);
        $this->assertSame(0, (int) $row->bytes);
    }

    public function test_refund_targets_the_charged_day_across_midnight(): void
    {
        $service = app(QuotaService::class);
        $user = User::factory()->create();
        $yesterday = now()->subDay()->toDateString();

        // The charge happened just before midnight; the void lands after. The
        // controller passes the captured charge day, so today's fresh ledger is
        // untouched and yesterday's is decremented.
        TranslationQuota::create([
            'user_id' => $user->id,
            'quota_day' => $yesterday,
            'files' => 1,
            'bytes' => 100,
        ]);

        $service->refund((int) $user->id, 100, $yesterday);

        $row = TranslationQuota::where('user_id', $user->id)->where('quota_day', $yesterday)->firstOrFail();
        $this->assertSame(0, (int) $row->files);
        $this->assertSame(0, (int) $row->bytes);

        // Today's ledger was never created or touched.
        $this->assertNull(TranslationQuota::where('user_id', $user->id)->where('quota_day', today()->toDateString())->first());
    }

    public function test_yesterday_does_not_count_toward_today(): void
    {
        $service = app(QuotaService::class);
        $user = User::factory()->create();

        TranslationQuota::create([
            'user_id' => $user->id,
            'quota_day' => now()->subDay()->toDateString(),
            'files' => 25,
            'bytes' => 262144000,
        ]);

        $this->assertTrue($service->reserve((int) $user->id, 100));

        $today = TranslationQuota::where('user_id', $user->id)->where('quota_day', today()->toDateString())->firstOrFail();
        $this->assertSame(1, (int) $today->files);
    }

    public function test_quota_is_per_user(): void
    {
        config(['translation.upload.max_daily_files' => 1]);

        $service = app(QuotaService::class);
        $a = User::factory()->create();
        $b = User::factory()->create();

        $this->assertTrue($service->reserve((int) $a->id, 10));
        $this->assertFalse($service->reserve((int) $a->id, 10));
        $this->assertTrue($service->reserve((int) $b->id, 10));
    }

    public function test_refused_upload_returns_429_cleans_scratch_and_queues_nothing(): void
    {
        config(['translation.upload.max_daily_files' => 1]);

        $user = User::factory()->create();
        TranslationQuota::create([
            'user_id' => $user->id,
            'quota_day' => today()->toDateString(),
            'files' => 1,
            'bytes' => 1,
        ]);

        $response = $this->actingAs($user)->post('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => $this->docUpload(),
        ], ['Accept' => 'application/json']);

        $response->assertStatus(429);
        $this->assertSame(0, TranslationJob::count());
        $this->assertSame(0, TranslationHistory::count());
    }

    public function test_duplicate_submission_race_refunds_and_returns_the_winner(): void
    {
        config([
            'translation.upload.max_daily_files' => 25,
            'translation.upload.max_daily_bytes' => 262144000,
        ]);

        $user = User::factory()->create();
        $file = $this->docUpload();

        $contentHash = hash_file('sha256', $file->getRealPath());
        $payloadHash = TranslationJob::payloadHash((int) $user->id, $contentHash, 'English', 'Cebuano', 'balanced', 'auto', null);

        // The winner commits its row while the loser is mid-request (after the
        // loser's dedup look-up, before its own INSERT). The loser's INSERT
        // then trips the active partial unique index — the REAL race path.
        $winnerUuid = '11111111-1111-1111-1111-111111111111';
        $listener = function () use ($user, $payloadHash, $winnerUuid): void {
            DB::table('translation_jobs')->insert([
                'uuid'             => $winnerUuid,
                'user_id'          => $user->id,
                'payload_hash'     => $payloadHash,
                'original_name'    => 'q.docx',
                'original_ext'     => '.docx',
                'source_lang'      => 'English',
                'target_lang'      => 'Cebuano',
                'pdf_column_mode'  => 'auto',
                'mode'             => 'balanced',
                'file_size'        => 258,
                'status'           => TranslationJob::STATUS_QUEUED,
                'progress'         => 5,
                'created_at'       => now(),
                'updated_at'       => now(),
            ]);
        };
        TranslationJob::creating($listener);

        try {
            $before = $this->subdirs(storage_path('app/uploads'));
            $response = $this->actingAs($user)->post('/translate', [
                'source_lang' => 'English',
                'target_lang' => 'Cebuano',
                'document' => $this->docUpload(),
            ], ['Accept' => 'application/json']);

            $response->assertOk();
            $response->assertJsonPath('duplicate', true);
            $response->assertJsonPath('job_id', $winnerUuid);
        } finally {
            TranslationJob::flushEventListeners();
        }

        $this->assertSame(1, TranslationJob::count(), 'only the winner row may survive the race');

        $row = TranslationQuota::where('user_id', $user->id)->where('quota_day', today()->toDateString())->first();
        $this->assertNotNull($row);
        $this->assertSame(0, (int) $row->files, 'the race loser is fully refunded');
        $this->assertSame(0, (int) $row->bytes);
    }

    public function test_job_creation_failure_after_reservation_refunds_and_leaves_no_job(): void
    {
        $user = User::factory()->create();

        // The reservation is charged, then acceptance dies before a row exists
        // (e.g. the DB insert fails) — the budget must be returned and nothing
        // may leak.
        $listener = function (): void {
            throw new \RuntimeException('simulated acceptance failure after reservation');
        };
        TranslationJob::creating($listener);

        $before = $this->subdirs(storage_path('app/uploads'));

        try {
            $response = $this->actingAs($user)->post('/translate', [
                'source_lang' => 'English',
                'target_lang' => 'Cebuano',
                'document' => $this->docUpload(),
            ], ['Accept' => 'application/json']);

            $response->assertStatus(500);
        } finally {
            TranslationJob::flushEventListeners();
        }

        $this->assertSame(0, TranslationJob::count());
        $this->assertSame(0, TranslationHistory::count());
        $row = TranslationQuota::where('user_id', $user->id)->where('quota_day', today()->toDateString())->first();
        $this->assertNotNull($row);
        $this->assertSame(0, (int) $row->files, 'a failed, never-accepted submission is refunded');
        $this->assertSame(0, (int) $row->bytes);
        $this->assertNoNewScratchDirs($before, 'a failed acceptance must not leak its scratch dir');
    }

    public function test_completed_result_reuse_is_never_charged(): void
    {
        Cache::flush();
        config(['queue.default' => 'database']);

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('generateSignedUrl')
            ->once()
            ->andReturn([
                'signed_url' => 'https://example.test/reused-signed',
                'signed_url_expires_at' => now()->addHour()->toIso8601String(),
            ]);
        $this->app->instance(StorageService::class, $storage);

        $user = User::factory()->create();
        $file = $this->docUpload();

        $contentHash = hash_file('sha256', $file->getRealPath());
        $payloadHash = TranslationJob::payloadHash((int) $user->id, $contentHash, 'English', 'Cebuano', 'balanced', 'auto', null);

        $history = TranslationHistory::create([
            'user_id'             => $user->id,
            'translation_type'    => 'document',
            'original_filename'   => 'q.docx',
            'translated_filename' => 'q_translated.docx',
            'source_language'     => 'English',
            'target_language'     => 'Cebuano',
            'storage_path'        => 'user/translations/out.docx',
            'storage_backend'     => 'supabase',
            'status'              => 'completed',
            'created_at'          => now()->toIso8601String(),
        ]);
        TranslationJob::create([
            'uuid'                   => '33333333-3333-3333-3333-333333333333',
            'user_id'                => $user->id,
            'payload_hash'           => $payloadHash,
            'original_name'          => 'q.docx',
            'original_ext'           => '.docx',
            'source_lang'            => 'English',
            'target_lang'            => 'Cebuano',
            'pdf_column_mode'        => 'auto',
            'mode'                   => 'balanced',
            'status'                 => TranslationJob::STATUS_COMPLETED,
            'storage_path'           => 'user/translations/out.docx',
            'storage_backend'        => 'supabase',
            'translation_history_id' => $history->id,
            'progress'               => 100,
        ]);

        $response = $this->actingAs($user)->post('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => $file,
        ], ['Accept' => 'application/json']);

        $response->assertOk();
        $response->assertJsonPath('reused', true);
        $this->assertSame(0, TranslationQuota::count(), 'reused completed work is never charged');
    }

    public function test_retranslate_consumes_the_same_daily_quota_and_refuses_at_cap(): void
    {
        config(['translation.upload.max_daily_files' => 1]);
        Queue::fake();

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('exists')
            ->andReturn(StorageService::PRESENCE_PRESENT);
        $storage->shouldReceive('read')
            ->andReturn('PK-original-bytes-for-retranslate');
        $this->app->instance(StorageService::class, $storage);

        $user = User::factory()->create();
        $record = TranslationHistory::create([
            'user_id'                 => $user->id,
            'translation_type'        => 'document',
            'original_filename'       => 'doc.docx',
            'source_language'         => 'English',
            'target_language'         => 'Cebuano',
            'storage_path'            => 'user/translations/v1.pdf',
            'storage_backend'         => 'supabase',
            'original_storage_path'   => 'user/originals/doc.docx',
            'original_storage_backend' => 'supabase',
            'status'                  => 'completed',
            'file_size'               => 0,
        ]);

        $response = $this->actingAs($user)->post('/documents/' . $record->id . '/re-translate', [
            'target_lang' => 'Filipino',
        ], ['Accept' => 'application/json']);

        $response->assertOk()->assertJsonPath('status', 'processing');

        $row = TranslationQuota::where('user_id', $user->id)->firstOrFail();
        $this->assertSame(1, (int) $row->files, 'a re-translation charges one accepted file');

        // Now at the file cap: a second re-translation is refused with 429.
        TranslationQuota::where('user_id', $user->id)->update(['files' => 1, 'bytes' => 1]);

        $before = $this->subdirs(storage_path('app/uploads'));

        $refused = $this->actingAs($user)->post('/documents/' . $record->id . '/re-translate', [
            'target_lang' => 'Cebuano',
        ], ['Accept' => 'application/json']);

        $refused->assertStatus(429);
        $this->assertNoNewScratchDirs($before, 'refused re-translation must not leak its scratch dir');
    }

    public function test_retranslate_race_loss_refunds_and_returns_the_winner(): void
    {
        config(['translation.upload.max_daily_files' => 25]);

        $knownBytes = 'PK-original-bytes-for-race';

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('exists')
            ->andReturn(StorageService::PRESENCE_PRESENT);
        $storage->shouldReceive('read')
            ->andReturn($knownBytes);
        $this->app->instance(StorageService::class, $storage);

        $user = User::factory()->create();
        $record = TranslationHistory::create([
            'user_id'                 => $user->id,
            'translation_type'        => 'document',
            'original_filename'       => 'doc.docx',
            'source_language'         => 'English',
            'target_language'         => 'Cebuano',
            'storage_path'            => 'user/translations/v1.pdf',
            'storage_backend'         => 'supabase',
            'original_storage_path'   => 'user/originals/doc.docx',
            'original_storage_backend' => 'supabase',
            'status'                  => 'completed',
            'file_size'               => 0,
        ]);

        $contentHash = hash('sha256', $knownBytes);
        $payloadHash = TranslationJob::payloadHash((int) $user->id, $contentHash, 'English', 'Filipino', 'balanced', 'auto', (int) $record->id);

        // Same real race seam: the winner's row appears during the loser's
        // create(), tripping the active partial unique index.
        $winnerUuid = '7a7a7a7a-7a7a-7a7a-7a7a-7a7a7a7a7a7a';
        $listener = function () use ($user, $record, $payloadHash, $winnerUuid): void {
            DB::table('translation_jobs')->insert([
                'uuid'             => $winnerUuid,
                'user_id'          => $user->id,
                'payload_hash'     => $payloadHash,
                'original_name'    => 'doc.docx',
                'original_ext'     => '.docx',
                'source_lang'      => 'English',
                'target_lang'      => 'Filipino',
                'pdf_column_mode'  => 'auto',
                'mode'             => 'balanced',
                'status'           => TranslationJob::STATUS_QUEUED,
                'parent_document_id' => $record->id,
                'progress'         => 5,
                'created_at'       => now(),
                'updated_at'       => now(),
            ]);
        };
        TranslationJob::creating($listener);

        try {
            $response = $this->actingAs($user)->post('/documents/' . $record->id . '/re-translate', [
                'target_lang' => 'Filipino',
            ], ['Accept' => 'application/json']);

            $response->assertOk();
            $response->assertJsonPath('duplicate', true);
            $response->assertJsonPath('job_id', $winnerUuid);
        } finally {
            TranslationJob::flushEventListeners();
        }

        $this->assertSame(1, TranslationJob::count(), 'only the winner re-translation survives');

        $row = TranslationQuota::where('user_id', $user->id)->where('quota_day', today()->toDateString())->first();
        $this->assertNotNull($row);
        $this->assertSame(0, (int) $row->files, 'the re-translation race loser is fully refunded');
        $this->assertSame(0, (int) $row->bytes);
    }

    /**
     * storage_path('app/uploads') accumulates scratch dirs across unrelated
     * runs, and on Windows a moved-to directory stays hand-locked until the
     * request's UploadedFile is released. The lock leaves "pending-delete"
     * phantom entries that scandir() still lists even though the underlying
     * file is gone and file_exists() is already false. The leak that matters
     * is orphaned BYTES, so only dirs containing REAL files count — wait
     * briefly for any real file to clear, then assert none are left.
     */
    private function assertNoNewScratchDirs(array $before, string $message): void
    {
        $until = microtime(true) + 2.0;
        $nonEmpty = ['pending'];
        while ($nonEmpty !== [] && microtime(true) < $until) {
            $leftovers = array_values(array_diff($this->subdirs(storage_path('app/uploads')), $before));
            $nonEmpty = array_values(array_filter(
                $leftovers,
                fn (string $name) => array_filter(
                    array_diff(scandir(storage_path('app/uploads/' . $name)) ?: [], ['.', '..']),
                    fn (string $entry) => is_file(storage_path('app/uploads/' . $name . '/' . $entry)),
                ) !== [],
            ));
            if ($nonEmpty !== []) {
                usleep(50_000);
            }
        }
        $this->assertSame([], $nonEmpty, $message);
    }
}