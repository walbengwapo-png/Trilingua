<?php

namespace Tests\Unit;

use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Notifications\TranslationCompleted;
use App\Services\BlockService;
use App\Services\HistoryService;
use App\Services\MetricsService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Notification;
use Mockery;
use Tests\TestCase;

/**
 * F1 / X1 — completion authority.
 *
 * A worker may only announce success when markCompleted() actually performed the
 * transition. When another actor has already made the row terminal, this
 * attempt's own side effects must be compensated without creating a duplicate
 * history row, deleting a pre-existing valid row, or removing an object another
 * worker still needs.
 *
 * X1 — a retryable attempt that will be released back onto the queue must not
 * first be driven into a terminal `failed` state, which would leave the row
 * disagreeing with the queue for the whole backoff window.
 */
class TranslateDocumentJobCompletionAuthorityTest extends TestCase
{
    use RefreshDatabase;

    protected function tearDown(): void
    {
        Mockery::close();
        parent::tearDown();
    }

    private function makeRow(string $status = TranslationJob::STATUS_QUEUED): TranslationJob
    {
        \App\Models\User::factory()->create(['id' => 42]);

        return TranslationJob::create([
            'uuid'                     => (string) \Illuminate\Support\Str::uuid(),
            'user_id'                  => 42,
            'payload_hash'             => hash('sha256', 'payload'),
            'original_name'            => 'input.pdf',
            'original_ext'             => '.pdf',
            'source_lang'              => 'English',
            'target_lang'              => 'Cebuano',
            'pdf_column_mode'          => 'auto',
            'mode'                     => 'balanced',
            'file_size'                => 16,
            'status'                   => $status,
            'original_storage_path'    => '42/originals/input.pdf',
            'original_storage_backend' => 'supabase',
        ]);
    }

    private function makeTempFile(): string
    {
        $path = sys_get_temp_dir() . '/trilingua-auth-' . uniqid('', true) . '.pdf';
        file_put_contents($path, '%PDF-1.4 source');

        return $path;
    }

    private function mockHappyEngine(TranslationManager $tm): void
    {
        $tm->shouldReceive('translateDocument')->once()->andReturn([
            'download_filename' => 'out.pdf',
            'body' => '%PDF-1.4 translated',
            'blocks' => [],
            'sidecar' => null,
            'metrics' => [],
        ]);
    }

    /**
     * Upload succeeds, then — mid-flight, after the worker already captured its
     * in-memory model — another actor rewrites the authoritative row. The
     * worker's own markCompleted() will then be refused at the database layer.
     */
    private function mockUploadWithInterference(StorageService $storage, TranslationJob $row, array $interference, string $path = '42/translations/mine.pdf'): void
    {
        $storage->shouldReceive('uploadWithFallback')
            ->once()
            ->andReturnUsing(function () use ($row, $interference, $path) {
                TranslationJob::whereKey($row->getKey())->update($interference);

                return [
                    'backend' => 'supabase',
                    'storage_path' => $path,
                    'signed_url' => 'https://example.test/signed',
                    'signed_url_expires_at' => now()->addHour()->toIso8601String(),
                ];
            });
    }

    private function runJob(TranslationJob $row, string $temp, string $presetUuid): TranslateDocumentJob
    {
        $job = new TranslateDocumentJob(
            'input.pdf', '.pdf', 16, 'English', 'Cebuano', 'auto',
            $temp, 42, '42/originals/input.pdf', 'balanced', null, 'supabase',
            (int) $row->id, $presetUuid
        );
        $job->uuid();

        return $job;
    }

    /**
     * F1: the authoritative row was made terminal by another actor before the
     * worker reached markCompleted(). The worker must not announce success.
     */
    public function test_refused_completion_never_announces_success(): void
    {
        Cache::flush();
        Notification::fake();

        $row = $this->makeRow();
        $temp = $this->makeTempFile();

        $tm = Mockery::mock(TranslationManager::class);
        $this->mockHappyEngine($tm);

        $storage = Mockery::mock(StorageService::class);
        $this->mockUploadWithInterference($storage, $row, [
            'status' => TranslationJob::STATUS_FAILED,
            'recoverable' => false,
            'terminal_failed_at' => now(),
        ]);

        $historyService = Mockery::mock(HistoryService::class);
        $historyService->shouldReceive('insertRecord')
            ->once()
            ->andReturnUsing(fn (array $data) => TranslationHistory::create($data));

        $blockService = Mockery::mock(BlockService::class);
        $blockService->shouldReceive('persistBlocks')->once()->andReturn(true);

        $metricsService = Mockery::mock(MetricsService::class);
        $metricsService->shouldReceive('persistDocumentMetrics')->once()->andReturn(true);

        $job = $this->runJob($row, $temp, $row->uuid);
        $job->handle($tm, $storage, $historyService, $blockService, $metricsService);

        $row->refresh();
        $this->assertSame(TranslationJob::STATUS_FAILED, $row->status, 'The authoritative terminal state must survive.');

        $cached = Cache::get('translation_job_' . $row->uuid);
        $this->assertNotSame(
            'completed',
            $cached['status'] ?? null,
            'A refused completion must not publish a completed cache result.'
        );

        Notification::assertNotSentTo(\App\Models\User::find(42), TranslationCompleted::class);

        @unlink($temp);
    }

    /**
     * F1: another worker already completed the row. This attempt lost the race
     * and must behave idempotently — no second completion notification, no
     * duplicate history row, and no deletion of the pre-existing valid row.
     */
    public function test_already_completed_row_is_idempotent_not_a_second_completion(): void
    {
        Cache::flush();
        Notification::fake();

        $row = $this->makeRow();
        $temp = $this->makeTempFile();

        // A pre-existing, valid history row belonging to the winning attempt.
        $winner = TranslationHistory::create([
            'user_id'             => 42,
            'translation_type'    => 'document',
            'original_filename'   => 'input.pdf',
            'translated_filename' => 'winner.pdf',
            'source_language'     => 'English',
            'target_language'     => 'Cebuano',
            'storage_path'        => '42/translations/winner.pdf',
            'storage_backend'     => 'supabase',
            'status'              => 'completed',
            'review_status'       => 'pending',
            'job_id'              => $row->uuid,
            'created_at'          => now(),
        ]);

        $tm = Mockery::mock(TranslationManager::class);
        $this->mockHappyEngine($tm);

        $storage = Mockery::mock(StorageService::class);
        $this->mockUploadWithInterference($storage, $row, [
            'status' => TranslationJob::STATUS_COMPLETED,
            'storage_path' => '42/translations/winner.pdf',
            'storage_backend' => 'supabase',
            'translation_history_id' => $winner->id,
            'progress' => 100,
        ], '42/translations/loser.pdf');

        $historyService = Mockery::mock(HistoryService::class);
        $historyService->shouldNotReceive('insertRecord');

        $blockService = Mockery::mock(BlockService::class);
        $blockService->shouldNotReceive('persistBlocks');

        $metricsService = Mockery::mock(MetricsService::class);
        $metricsService->shouldReceive('persistDocumentMetrics')->once()->andReturn(true);

        $job = $this->runJob($row, $temp, $row->uuid);
        $job->handle($tm, $storage, $historyService, $blockService, $metricsService);

        $this->assertNotNull(
            TranslationHistory::find($winner->id),
            'A pre-existing valid history row must never be deleted by a losing attempt.'
        );
        $this->assertSame(
            1,
            TranslationHistory::where('job_id', $row->uuid)->count(),
            'A losing attempt must not create a duplicate history row.'
        );

        Notification::assertNotSentTo(\App\Models\User::find(42), TranslationCompleted::class);

        @unlink($temp);
    }

    /**
     * F1: a refused completion against a non-completed terminal row must remove
     * the history row THIS attempt created, so the owner's history list and the
     * admin review queue never show work the authoritative job disclaims.
     */
    public function test_refused_completion_removes_only_the_history_row_this_attempt_created(): void
    {
        Cache::flush();
        Notification::fake();

        $row = $this->makeRow();
        $temp = $this->makeTempFile();

        $tm = Mockery::mock(TranslationManager::class);
        $this->mockHappyEngine($tm);

        $storage = Mockery::mock(StorageService::class);
        $this->mockUploadWithInterference($storage, $row, [
            'status' => TranslationJob::STATUS_FAILED,
            'recoverable' => false,
            'terminal_failed_at' => now(),
        ]);

        $historyService = Mockery::mock(HistoryService::class);
        $historyService->shouldReceive('insertRecord')
            ->once()
            ->andReturnUsing(fn (array $data) => TranslationHistory::create($data));

        $blockService = Mockery::mock(BlockService::class);
        $blockService->shouldReceive('persistBlocks')->once()->andReturn(true);

        $metricsService = Mockery::mock(MetricsService::class);
        $metricsService->shouldReceive('persistDocumentMetrics')->once()->andReturn(true);

        $job = $this->runJob($row, $temp, $row->uuid);
        $job->handle($tm, $storage, $historyService, $blockService, $metricsService);

        $this->assertSame(
            0,
            TranslationHistory::where('job_id', $row->uuid)->count(),
            'A history row claiming completion under a refused transition must be compensated away.'
        );

        @unlink($temp);
    }

    /**
     * X1: a retryable failure releases the job back onto the queue. The state
     * row must remain active so the API never reports "failed" for work that is
     * still legitimately scheduled to run.
     */
    public function test_retryable_failure_keeps_the_row_active_for_the_released_retry(): void
    {
        Cache::flush();

        $row = $this->makeRow();
        $temp = $this->makeTempFile();

        $tm = Mockery::mock(TranslationManager::class);
        $tm->shouldReceive('translateDocument')
            ->once()
            ->andThrow(new \App\Exceptions\TranslationException('upstream timed out', 504));

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldNotReceive('uploadWithFallback');

        $historyService = Mockery::mock(HistoryService::class);
        $historyService->shouldNotReceive('insertRecord');

        $blockService = Mockery::mock(BlockService::class);
        $blockService->shouldNotReceive('persistBlocks');

        $metricsService = Mockery::mock(MetricsService::class);
        $metricsService->shouldNotReceive('persistDocumentMetrics');

        $job = $this->runJob($row, $temp, $row->uuid);
        $job->handle($tm, $storage, $historyService, $blockService, $metricsService);

        $row->refresh();
        $this->assertContains(
            $row->status,
            TranslationJob::ACTIVE_STATUSES,
            'An attempt that will be released for retry must leave the row active, not terminal-failed.'
        );
        $this->assertNull(
            $row->terminal_failed_at,
            'A retryable attempt must not stamp a terminal failure.'
        );

        @unlink($temp);
    }
}
