<?php

namespace Tests\Unit;

use App\Jobs\TranslateDocumentJob;
use App\Exceptions\TranslationException;
use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Services\HistoryService;
use App\Services\StorageService;
use App\Services\BlockService;
use App\Services\MetricsService;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Mockery;
use Tests\TestCase;

class TranslateDocumentJobTest extends TestCase
{
    use RefreshDatabase;

    protected function tearDown(): void
    {
        Mockery::close();
        parent::tearDown();
    }

    public function test_it_marks_job_failed_when_the_translated_output_is_empty(): void
    {
        Cache::flush();

        $tempDir = sys_get_temp_dir() . '/trilingua-job-' . uniqid('', true);
        mkdir($tempDir, 0777, true);

        $originalPath = $tempDir . '/input.pdf';
        file_put_contents($originalPath, 'original-file');

        $outputPath = $tempDir . '/translated.pdf';
        file_put_contents($outputPath, '');

        $translationManager = Mockery::mock(TranslationManager::class);
        $translationManager->shouldReceive('translateDocument')
            ->once()
            ->andReturn([
                'download_filename' => 'translated.pdf',
                'body' => '',
            ]);

        // No original storage path is set, so the job first backfills the
        // original durably, then fails once the (empty) translated output is
        // detected — before any translated upload happens.
        $storageService = Mockery::mock(StorageService::class);
        $storageService->shouldReceive('uploadWithFallback')
            ->once()
            ->andReturn([
                'backend' => 'supabase',
                'storage_path' => '1/originals/backfill.pdf',
                'signed_url' => 'https://example.test/signed',
                'signed_url_expires_at' => now()->addHour()->toIso8601String(),
            ]);

        $historyService = Mockery::mock(HistoryService::class);
        $historyService->shouldNotReceive('insertRecord');
        $blockService = Mockery::mock(BlockService::class);
        $metricsService = Mockery::mock(MetricsService::class);

        $job = new TranslateDocumentJob(
            'input.pdf',
            '.pdf',
            123,
            'English',
            'Cebuano',
            'auto',
            $originalPath,
            1,
            null
        );

        $job->uuid();
        $job->handle($translationManager, $storageService, $historyService, $blockService, $metricsService);

        $result = Cache::get('translation_job_' . $job->uuid());

        $this->assertSame('failed', $result['status'] ?? null);
        $this->assertStringContainsString('empty', strtolower((string) ($result['error'] ?? '')));

        @unlink($outputPath);
        @unlink($originalPath);
        @rmdir($tempDir);
    }

    public function test_it_persists_progress_and_completes_with_a_durable_upload(): void
    {
        Cache::flush();

        $tempDir = sys_get_temp_dir() . '/trilingua-job-' . uniqid('', true);
        mkdir($tempDir, 0777, true);

        $originalPath = $tempDir . '/input.pdf';
        file_put_contents($originalPath, '%PDF-1.4 fake');

        $jobRow = TranslationJob::create([
            'uuid'         => '11111111-1111-1111-1111-111111111111',
            'user_id'      => 42,
            'payload_hash' => hash('sha256', 'payload'),
            'original_name'=> 'input.pdf',
            'original_ext' => '.pdf',
            'source_lang'  => 'English',
            'target_lang'  => 'Cebuano',
            'pdf_column_mode' => 'auto',
            'mode'         => 'balanced',
            'file_size'    => 16,
            'status'       => TranslationJob::STATUS_QUEUED,
        ]);

        \App\Models\User::factory()->create(['id' => 42]);

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

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('uploadWithFallback')
            ->times(2)
            ->andReturn([
                'backend' => 'supabase',
                'storage_path' => '42/translations/abc.pdf',
                'signed_url' => 'https://example.test/signed',
                'signed_url_expires_at' => now()->addHour()->toIso8601String(),
            ]);

        $history = Mockery::mock(HistoryService::class);
        $history->shouldReceive('insertRecord')
            ->once()
            ->andReturnUsing(fn (array $data) => TranslationHistory::create($data));

        $blocks = Mockery::mock(BlockService::class);
        $blocks->shouldReceive('persistBlocks')
            ->once()
            ->with(Mockery::type(TranslationHistory::class), [], null)
            ->andReturn(0);

        $metrics = Mockery::mock(MetricsService::class);
        $metrics->shouldReceive('persistDocumentMetrics')->once()->andReturn(true);

        $job = new TranslateDocumentJob(
            'input.pdf', '.pdf', 16, 'English', 'Cebuano', 'auto',
            $originalPath, 42, null, 'balanced', null, 'supabase', (int) $jobRow->id
        );

        $job->uuid();
        $job->handle($translationManager, $storage, $history, $blocks, $metrics);

        $jobRow->refresh();
        $this->assertSame('completed', $jobRow->status);
        $this->assertSame(100, $jobRow->progress);
        $this->assertSame('supabase', $jobRow->storage_backend);
        $this->assertSame('42/translations/abc.pdf', $jobRow->storage_path);

        $result = Cache::get('translation_job_' . $job->uuid());
        $this->assertSame('completed', $result['status'] ?? null);
        $this->assertFileDoesNotExist($originalPath, 'Worker scratch should be released after durable completion.');

        @rmdir($tempDir);
    }

    public function test_retryable_failure_keeps_original_upload_for_the_next_attempt(): void
    {
        Cache::flush();

        $tempDir = sys_get_temp_dir().'/trilingua-job-'.uniqid('', true);
        mkdir($tempDir, 0777, true);
        $originalPath = $tempDir.'/input.pdf';
        file_put_contents($originalPath, '%PDF-1.4 original');

        $translationManager = Mockery::mock(TranslationManager::class);
        $translationManager->shouldReceive('translateDocument')
            ->once()
            ->andThrow(new TranslationException('Translation service timed out.', 504));

        $storage = Mockery::mock(StorageService::class);
        $history = Mockery::mock(HistoryService::class);
        $blocks = Mockery::mock(BlockService::class);
        $metrics = Mockery::mock(MetricsService::class);

        $job = new TranslateDocumentJob(
            'input.pdf', '.pdf', 16, 'English', 'Cebuano', 'auto',
            $originalPath, 42, '42/originals/input.pdf'
        );
        $job->uuid();
        $job->handle($translationManager, $storage, $history, $blocks, $metrics);

        $this->assertFileExists($originalPath, 'A retry must retain the source upload.');
        $this->assertSame('processing', Cache::get('translation_job_'.$job->uuid())['status'] ?? null);

        @unlink($originalPath);
        @rmdir($tempDir);
    }
}
