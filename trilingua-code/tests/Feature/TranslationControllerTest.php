<?php

namespace Tests\Feature;

use App\Http\Controllers\TranslationController;
use App\Services\HistoryService;
use App\Services\StorageService;
use App\Services\TranslationService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Storage;
use Tests\TestCase;

class TranslationControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_document_translation_returns_inline_download_payload_when_storage_fails(): void
    {
        $user = \App\Models\User::factory()->create();

        $tempPath = storage_path('app/testing/fallback-translated.docx');
        if (!is_dir(dirname($tempPath))) {
            mkdir(dirname($tempPath), 0755, true);
        }
        file_put_contents($tempPath, 'fake translated content');

        $service = $this->createMock(TranslationService::class);
        $service->method('translateDocument')->willReturn($tempPath);
        $service->method('getOriginalOutputName')->willReturn('sample_translated.docx');

        $storage = $this->createMock(StorageService::class);
        $storage->expects($this->exactly(2))
            ->method('uploadFile')
            ->willReturnOnConsecutiveCalls(
                ['storage_path' => 'user/originals/test.docx', 'signed_url' => 'https://example.test/original', 'signed_url_expires_at' => now()->toIso8601String()],
                $this->throwException(new \RuntimeException('storage unavailable'))
            );

        $history = $this->createMock(HistoryService::class);
        $history->method('insertRecord')->willReturn(new \App\Models\TranslationHistory());

        $this->app->instance(TranslationService::class, $service);
        $this->app->instance(StorageService::class, $storage);
        $this->app->instance(HistoryService::class, $history);

        $file = UploadedFile::fake()->create('sample.docx', 1024, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');

        $response = $this->actingAs($user)
            ->postJson('/translate', [
                'source_lang' => 'English',
                'target_lang' => 'Cebuano',
                'document' => $file,
            ]);

        $response->assertOk();
        $response->assertJsonFragment([
            'download_filename' => 'sample_translated.docx',
        ]);
        $response->assertJsonPath('download_mode', 'inline');
        $this->assertNotEmpty($response->json('download_data'));

        @unlink($tempPath);
    }
}
