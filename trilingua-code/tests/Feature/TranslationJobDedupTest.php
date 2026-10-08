<?php

namespace Tests\Feature;

use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Models\User;
use App\Services\BlockService;
use App\Services\HistoryService;
use App\Services\MetricsService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Mockery;
use Tests\TestCase;

class TranslationJobDedupTest extends TestCase
{
    use RefreshDatabase;

    /**
     * A byte-identical .docx payload (real ZIP magic so content sniffing passes).
     */
    private function docUpload(): UploadedFile
    {
        return UploadedFile::fake()->createWithContent(
            'duplicate.docx',
            'PK' . str_repeat('A', 512)
        );
    }

    public function test_identical_concurrent_submissions_yield_one_job_and_one_history_row(): void
    {
        // Use the real database queue so the first job is still queued when
        // the second identical submission arrives.
        config(['queue.default' => 'database']);
        Cache::flush();

        // The controller uploads the ORIGINAL through StorageService (twice:
        // the first submission and the Filipino variant); the job uploads the
        // translated output. Both go through uploadWithFallback — route each
        // by storage path so responses differ.
        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('uploadWithFallback')
            ->times(3)
            ->andReturn([
                'backend' => 'supabase',
                'storage_path' => 'user/originals/test.docx',
                'signed_url' => 'https://example.test/signed',
                'signed_url_expires_at' => now()->toIso8601String(),
            ]);
        $this->app->instance(StorageService::class, $storage);

        $user = User::factory()->create();

        $first = $this->actingAs($user)->post('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => $this->docUpload(),
        ], ['Accept' => 'application/json']);
        $first->assertOk()->assertJsonPath('status', 'processing');

        // One durable state-machine row + one queued database job.
        $this->assertSame(1, DB::table('translation_jobs')->count());
        $this->assertSame(1, TranslationJob::where('status', TranslationJob::STATUS_QUEUED)->count());
        $this->assertSame(1, DB::table('jobs')->count());

        // Second identical submission while the first is queued: dedups to the
        // existing active job (byte-identical content → same payload_hash).
        $dup = $this->actingAs($user)->post('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => $this->docUpload(),
        ], ['Accept' => 'application/json']);
        $dup->assertOk();
        $dup->assertJsonPath('duplicate', true);
        $this->assertSame(1, DB::table('translation_jobs')->count(), 'no duplicate job row may be created');
        $this->assertSame(1, DB::table('jobs')->count(), 'no duplicate job may be queued');
        $this->assertSame(0, TranslationHistory::count(), 'nothing processed yet');

        // A different target language shares NO canonical payload — new job.
        $other = $this->actingAs($user)->post('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Filipino',
            'document' => $this->docUpload(),
        ], ['Accept' => 'application/json']);
        $other->assertOk();
        $this->assertSame(2, DB::table('translation_jobs')->count());

        // Process the first queued job exactly once.
        $job = $this->hydrateQueuedJob();

        $manager = Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('translateDocument')
            ->once()
            ->andReturn([
                'download_filename' => 'duplicate_translated.docx',
                'body' => 'translated file body',
                'blocks' => [],
                'sidecar' => null,
                'metrics' => [],
            ]);

        // Real HistoryService so insertRecord() genuinely persists the row.
        $history = app(HistoryService::class);

        $blocks = Mockery::mock(BlockService::class);
        $blocks->shouldReceive('persistBlocks')->once();

        $metrics = Mockery::mock(MetricsService::class);
        $metrics->shouldReceive('persistDocumentMetrics')->once();

        $job->handle($manager, $storage, $history, $blocks, $metrics);

        $this->assertSame(1, TranslationHistory::count(), 'one queued job must write one history row');
        $jobRow = TranslationJob::first();
        $this->assertSame('completed', $jobRow->status);
        $this->assertSame('supabase', $jobRow->storage_backend);
        $this->assertNotNull($jobRow->storage_path, 'completed job must reference stored output');
    }

    public function test_payload_hash_is_content_based_not_name_or_size_based(): void
    {
        $contentHash = hash('sha256', 'PK-same-bytes');
        $a = TranslationJob::payloadHash(7, $contentHash, 'English', 'Cebuano', 'fast', 'auto', null);
        $b = TranslationJob::payloadHash(7, $contentHash, 'English', 'Cebuano', 'fast', 'auto', null);
        $c = TranslationJob::payloadHash(7, $contentHash, 'English', 'Filipino', 'fast', 'auto', null);

        $this->assertSame($a, $b);
        $this->assertNotSame($a, $c, 'different target language must not dedup');
    }

    public function test_completed_identical_submission_reuses_the_result(): void
    {
        Cache::flush();
        config(['queue.default' => 'database']);

        // The reused-result path signs a fresh Supabase URL (no uploads happen).
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

        // Pre-existing completed work with this exact content, linked to a history row.
        $history = TranslationHistory::create([
            'user_id'             => $user->id,
            'translation_type'    => 'document',
            'original_filename'   => 'duplicate.docx',
            'translated_filename' => 'duplicate_translated.docx',
            'source_language'     => 'English',
            'target_language'     => 'Cebuano',
            'storage_path'        => 'user/translations/out.docx',
            'storage_backend'     => 'supabase',
            'status'              => 'completed',
            'created_at'          => now()->toIso8601String(),
        ]);
        TranslationJob::create([
            'uuid'                   => '22222222-2222-2222-2222-222222222222',
            'user_id'                => $user->id,
            'payload_hash'           => $payloadHash,
            'original_name'          => 'duplicate.docx',
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
        $this->assertSame(1, DB::table('translation_jobs')->count(), 'no new job row for reused work');
        $this->assertSame(0, DB::table('jobs')->count(), 'no new job queued for reused work');
    }

    private function hydrateQueuedJob(): TranslateDocumentJob
    {
        $row = DB::table('jobs')
            ->where('attempts', 0)
            ->orderBy('id')
            ->first() ?? DB::table('jobs')->firstOrFail();
        $payload = json_decode($row->payload, true);

        /** @var TranslateDocumentJob $job */
        $job = unserialize($payload['data']['command']);
        $this->assertInstanceOf(TranslateDocumentJob::class, $job);

        return $job;
    }

    protected function tearDown(): void
    {
        Mockery::close();
        parent::tearDown();
    }
}