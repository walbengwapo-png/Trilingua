<?php

namespace Tests\Unit;

use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Services\BlockService;
use App\Services\HistoryService;
use App\Services\MetricsService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Mockery;
use Tests\TestCase;

/**
 * An operator Retry replays a job whose worker-local scratch was cleaned at
 * terminal failure. Prove that a durable original is reconstructed at handle()
 * time, and that a job with NO durable original fails honestly as
 * unrecoverable instead of being silently replayed.
 */
class TranslateDocumentJobRecoveryTest extends TestCase
{
    use RefreshDatabase;

    protected function tearDown(): void
    {
        Mockery::close();
        parent::tearDown();
    }

    private function makeQueuedRow(): TranslationJob
    {
        \App\Models\User::factory()->create(['id' => 42]);

        return TranslationJob::create([
            'uuid'          => (string) \Illuminate\Support\Str::uuid(),
            'user_id'       => 42,
            'payload_hash'  => hash('sha256', 'payload'),
            'original_name' => 'input.pdf',
            'original_ext'  => '.pdf',
            'source_lang'   => 'English',
            'target_lang'   => 'Cebuano',
            'pdf_column_mode' => 'auto',
            'mode'          => 'balanced',
            'file_size'     => 16,
            'status'        => TranslationJob::STATUS_QUEUED,
        ]);
    }

    private function mockCompletionDependencies(StorageService $storage, string $backend): array
    {
        $translationManager = Mockery::mock(TranslationManager::class);
        $translationManager->shouldReceive('translateDocument')
            ->once()
            ->andReturn([
                'download_filename' => 'out.pdf',
                'body' => '%PDF-1.4 translated',
                'blocks' => [],
                'sidecar' => null,
                'metrics' => [],
            ]);

        $storage->shouldReceive('uploadWithFallback')
            ->once()
            ->andReturn([
                'backend' => $backend,
                'storage_path' => '42/translations/abc.pdf',
                'signed_url' => 'https://example.test/signed',
                'signed_url_expires_at' => now()->addHour()->toIso8601String(),
            ]);

        $historyService = Mockery::mock(HistoryService::class);
        $historyService->shouldReceive('insertRecord')
            ->once()
            ->andReturnUsing(fn (array $data) => TranslationHistory::create($data));
        $blockService = Mockery::mock(BlockService::class);
        $blockService->shouldReceive('persistBlocks')
            ->once()
            ->with(Mockery::type(TranslationHistory::class), [], null)
            ->andReturn(0);
        $metricsService = Mockery::mock(MetricsService::class);
        $metricsService->shouldReceive('persistDocumentMetrics')->once()->andReturn(true);

        return [$translationManager, $historyService, $blockService, $metricsService];
    }

    public function test_missing_scratch_is_reconstructed_from_a_supabase_original(): void
    {
        Cache::flush();
        $jobRow = $this->makeQueuedRow();
        $missingTemp = sys_get_temp_dir() . '/trilingua-missing-' . uniqid('', true) . '.pdf';

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('read')
            ->once()
            ->with('supabase', '42/originals/input.pdf')
            ->andReturn('%PDF-1.4 reconstructed');
        [$translationManager, $historyService, $blockService, $metricsService] = $this->mockCompletionDependencies($storage, 'supabase');

        $job = new TranslateDocumentJob(
            'input.pdf', '.pdf', 16, 'English', 'Cebuano', 'auto',
            $missingTemp, 42, '42/originals/input.pdf', 'balanced', null, 'supabase', (int) $jobRow->id
        );
        $job->uuid();
        $job->handle($translationManager, $storage, $historyService, $blockService, $metricsService);

        $jobRow->refresh();
        $this->assertSame(TranslationJob::STATUS_COMPLETED, $jobRow->status);
        $this->assertSame(100, $jobRow->progress);
        $this->assertSame('supabase', $jobRow->storage_backend);

        $this->assertSame('completed', Cache::get('translation_job_' . $job->uuid())['status'] ?? null);
    }

    public function test_missing_scratch_is_reconstructed_from_a_local_backend_original(): void
    {
        Cache::flush();
        $jobRow = $this->makeQueuedRow();
        $missingTemp = sys_get_temp_dir() . '/trilingua-missing-' . uniqid('', true) . '.pdf';

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('read')
            ->once()
            ->with('local', '42/originals/local-input.pdf')
            ->andReturn('%PDF-1.4 local');
        [$translationManager, $historyService, $blockService, $metricsService] = $this->mockCompletionDependencies($storage, 'local');

        $job = new TranslateDocumentJob(
            'input.pdf', '.pdf', 16, 'English', 'Cebuano', 'auto',
            $missingTemp, 42, '42/originals/local-input.pdf', 'balanced', null, 'local', (int) $jobRow->id
        );
        $job->uuid();
        $job->handle($translationManager, $storage, $historyService, $blockService, $metricsService);

        $jobRow->refresh();
        $this->assertSame(TranslationJob::STATUS_COMPLETED, $jobRow->status);
        $this->assertSame('local', $jobRow->storage_backend);
    }

    public function test_missing_scratch_and_no_durable_original_terminates_as_unrecoverable(): void
    {
        Cache::flush();
        $jobRow = $this->makeQueuedRow();
        $missingTemp = sys_get_temp_dir() . '/trilingua-missing-' . uniqid('', true) . '.pdf';

        $translationManager = Mockery::mock(TranslationManager::class);
        $translationManager->shouldNotReceive('translateDocument');
        $storage = Mockery::mock(StorageService::class);
        $storage->shouldNotReceive('read');
        $historyService = Mockery::mock(HistoryService::class);
        $historyService->shouldNotReceive('insertRecord');
        $blockService = Mockery::mock(BlockService::class);
        $metricsService = Mockery::mock(MetricsService::class);

        $job = new TranslateDocumentJob(
            'input.pdf', '.pdf', 16, 'English', 'Cebuano', 'auto',
            $missingTemp, 42, null, 'balanced', null, 'supabase', (int) $jobRow->id
        );
        $job->uuid();
        $job->handle($translationManager, $storage, $historyService, $blockService, $metricsService);

        $jobRow->refresh();
        $this->assertSame(TranslationJob::STATUS_FAILED, $jobRow->status);
        $this->assertFalse($jobRow->recoverable);
        $this->assertNotNull($jobRow->terminal_failed_at);
        $this->assertStringContainsString('cannot be replayed', (string) $jobRow->error);

        $this->assertSame('failed', Cache::get('translation_job_' . $job->uuid())['status'] ?? null);
    }
}