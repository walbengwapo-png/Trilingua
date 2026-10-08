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
use Illuminate\Support\Facades\DB;
use Mockery;
use Tests\TestCase;

/**
 * R4 completion integrity: the job may ONLY mark itself completed once a
 * history row is durably linked to the owner/job/file and review blocks are
 * persisted inside one transaction. History/block DB failures are terminal,
 * recoverable, and recorded on the state row — never silently swallowed into a
 * "completed" state the status endpoint cannot resolve. A retry resumes the
 * already-persisted object and history row instead of duplicating them.
 */
class TranslateDocumentJobHistoryIntegrityTest extends TestCase
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
            'uuid'                    => (string) \Illuminate\Support\Str::uuid(),
            'user_id'                 => 42,
            'payload_hash'            => hash('sha256', 'payload'),
            'original_name'           => 'input.pdf',
            'original_ext'            => '.pdf',
            'source_lang'             => 'English',
            'target_lang'             => 'Cebuano',
            'pdf_column_mode'         => 'auto',
            'mode'                    => 'balanced',
            'file_size'               => 16,
            'status'                  => TranslationJob::STATUS_QUEUED,
            'original_storage_path'   => '42/originals/input.pdf',
            'original_storage_backend'=> 'supabase',
        ]);
    }

    private function mockEngine(TranslationManager $translationManager): void
    {
        $translationManager->shouldReceive('translateDocument')
            ->once()
            ->andReturn([
                'download_filename' => 'out.pdf',
                'body' => '%PDF-1.4 translated',
                'blocks' => [],
                'sidecar' => null,
                'metrics' => [],
            ]);
    }

    private function makeTempFile(): string
    {
        $path = sys_get_temp_dir() . '/trilingua-r4-' . uniqid('', true) . '.pdf';
        file_put_contents($path, '%PDF-1.4 source');
        return $path;
    }

    public function test_history_insert_failure_is_terminal_recoverable_and_records_the_object(): void
    {
        Cache::flush();
        $jobRow = $this->makeQueuedRow();
        $temp = $this->makeTempFile();

        $translationManager = Mockery::mock(TranslationManager::class);
        $this->mockEngine($translationManager);

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('uploadWithFallback')
            ->once()
            ->andReturn([
                'backend' => 'supabase',
                'storage_path' => '42/translations/abc.pdf',
                'signed_url' => 'https://example.test/signed',
                'signed_url_expires_at' => now()->addHour()->toIso8601String(),
            ]);

        $historyService = Mockery::mock(HistoryService::class);
        $historyService->shouldReceive('insertRecord')
            ->once()
            ->andThrow(new \RuntimeException('database unavailable'));

        $blockService = Mockery::mock(BlockService::class);
        $blockService->shouldNotReceive('persistBlocks');
        $metricsService = Mockery::mock(MetricsService::class);
        $metricsService->shouldNotReceive('persistDocumentMetrics');

        $job = new TranslateDocumentJob(
            'input.pdf', '.pdf', 16, 'English', 'Cebuano', 'auto',
            $temp, 42, '42/originals/input.pdf', 'balanced', null, 'supabase', (int) $jobRow->id
        );
        $job->uuid();
        $job->handle($translationManager, $storage, $historyService, $blockService, $metricsService);

        $jobRow->refresh();
        $this->assertSame(TranslationJob::STATUS_FAILED, $jobRow->status);
        $this->assertTrue($jobRow->recoverable, 'A durable original exists, so the job must remain recoverable.');
        $this->assertNotNull($jobRow->terminal_failed_at);
        $this->assertStringContainsString('database unavailable', strtolower((string) $jobRow->error));
        $this->assertNull($jobRow->translation_history_id);
        $this->assertSame('42/translations/abc.pdf', $jobRow->translated_storage_path, 'The durably stored object must be recorded for cleanup/reuse.');
        $this->assertSame('supabase', $jobRow->translated_storage_backend);

        $this->assertSame(0, TranslationHistory::where('job_id', $job->uuid())->count(), 'The history insert must have rolled back.');
        $this->assertSame('failed', Cache::get('translation_job_' . $job->uuid())['status'] ?? null);

        @unlink($temp);
    }

    public function test_block_persistence_failure_rolls_back_history_and_fails_terminal(): void
    {
        Cache::flush();
        $jobRow = $this->makeQueuedRow();
        $temp = $this->makeTempFile();

        $translationManager = Mockery::mock(TranslationManager::class);
        $this->mockEngine($translationManager);

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('uploadWithFallback')
            ->once()
            ->andReturn([
                'backend' => 'supabase',
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
            ->andThrow(new \RuntimeException('block row rejected'));
        $metricsService = Mockery::mock(MetricsService::class);
        $metricsService->shouldNotReceive('persistDocumentMetrics');

        $job = new TranslateDocumentJob(
            'input.pdf', '.pdf', 16, 'English', 'Cebuano', 'auto',
            $temp, 42, '42/originals/input.pdf', 'balanced', null, 'supabase', (int) $jobRow->id
        );
        $job->uuid();
        try {
            $job->handle($translationManager, $storage, $historyService, $blockService, $metricsService);
        } catch (\Throwable $caught) {
            $this->fail('The job must swallow failures into the terminal state, but threw: '.$caught->getMessage());
        }

        $jobRow->refresh();
        $this->assertSame(TranslationJob::STATUS_FAILED, $jobRow->status);
        $this->assertTrue($jobRow->recoverable);
        $this->assertNull($jobRow->translation_history_id);
        $this->assertSame('42/translations/abc.pdf', $jobRow->translated_storage_path);
        $this->assertSame(0, TranslationHistory::where('job_id', $job->uuid())->count(), 'History insert must roll back with the failed block write.');

        @unlink($temp);
    }

    public function test_retry_resumes_the_recorded_object_and_existing_history_row(): void
    {
        Cache::flush();
        $jobRow = $this->makeQueuedRow();
        $temp = $this->makeTempFile();

        TranslationHistory::create([
            'user_id'             => 42,
            'translation_type'    => 'document',
            'original_filename'   => 'input.pdf',
            'translated_filename' => 'out.pdf',
            'source_language'     => 'English',
            'target_language'     => 'Cebuano',
            'storage_path'        => '42/translations/resume.pdf',
            'storage_backend'     => 'supabase',
            'status'              => 'completed',
            'review_status'       => 'pending',
            'job_id'              => $jobRow->uuid,
            'created_at'          => now(),
        ]);
        TranslationJob::whereKey($jobRow->id)->update([
            'translated_storage_path'    => '42/translations/resume.pdf',
            'translated_storage_backend' => 'supabase',
        ]);
        $jobRow->refresh();

        $translationManager = Mockery::mock(TranslationManager::class);
        $this->mockEngine($translationManager);

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldNotReceive('uploadWithFallback');
        $storage->shouldNotReceive('read');

        $historyService = Mockery::mock(HistoryService::class);
        $historyService->shouldNotReceive('insertRecord');
        $blockService = Mockery::mock(BlockService::class);
        $blockService->shouldNotReceive('persistBlocks');
        $metricsService = Mockery::mock(MetricsService::class);
        $metricsService->shouldReceive('persistDocumentMetrics')->once()->andReturn(true);

        $job = new TranslateDocumentJob(
            'input.pdf', '.pdf', 16, 'English', 'Cebuano', 'auto',
            $temp, 42, '42/originals/input.pdf', 'balanced', null, 'supabase',
            (int) $jobRow->id, $jobRow->uuid
        );
        $job->uuid();
        $job->handle($translationManager, $storage, $historyService, $blockService, $metricsService);

        $jobRow->refresh();
        $this->assertSame(TranslationJob::STATUS_COMPLETED, $jobRow->status);
        $this->assertSame(1, TranslationHistory::where('job_id', $job->uuid())->count(), 'No second history row may be created on replay.');
        $history = TranslationHistory::where('job_id', $job->uuid())->first();
        $this->assertSame('42/translations/resume.pdf', $history->storage_path);
        $this->assertSame((int) $history->id, (int) $jobRow->translation_history_id);

        @unlink($temp);
    }
}