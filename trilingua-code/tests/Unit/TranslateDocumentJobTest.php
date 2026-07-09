<?php

namespace Tests\Unit;

use App\Jobs\TranslateDocumentJob;
use App\Services\HistoryService;
use App\Services\StorageService;
use App\Services\TranslationService;
use Illuminate\Support\Facades\Cache;
use Mockery;
use Tests\TestCase;

class TranslateDocumentJobTest extends TestCase
{
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

        $translationService = Mockery::mock(TranslationService::class);
        $translationService->shouldReceive('translateDocument')
            ->once()
            ->andReturn($outputPath);
        $translationService->shouldNotReceive('getOriginalOutputName');

        $storageService = Mockery::mock(StorageService::class);
        $storageService->shouldNotReceive('uploadFile');

        $historyService = Mockery::mock(HistoryService::class);
        $historyService->shouldNotReceive('insertRecord');

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
        $job->handle($translationService, $storageService, $historyService);

        $result = Cache::get('translation_job_' . $job->uuid());

        $this->assertSame('failed', $result['status'] ?? null);
        $this->assertStringContainsString('empty', strtolower((string) ($result['error'] ?? '')));

        @unlink($outputPath);
        @unlink($originalPath);
        @rmdir($tempDir);
    }
}
