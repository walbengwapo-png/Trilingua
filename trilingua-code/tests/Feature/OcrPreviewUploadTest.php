<?php

namespace Tests\Feature;

use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationJob;
use App\Models\User;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class OcrPreviewUploadTest extends TestCase
{
    use RefreshDatabase;

    public function test_existing_positional_job_uuid_is_preserved(): void
    {
        $job = new TranslateDocumentJob('input.pdf', '.pdf', 16, 'English', 'Cebuano',
            'auto', '', 1, null, 'balanced', null, 'local', null, 'existing-uuid');
        $this->assertSame('existing-uuid', $job->uuid());
        $this->assertSame('strict', $job->ocrMode);
    }

    public function test_pdf_uploads_queue_with_ocr_disabled_even_for_legacy_strict_requests(): void
    {
        config(['queue.default' => 'database']);
        $storage = \Mockery::mock(StorageService::class);
        $storage->shouldReceive('uploadWithFallback')->once()->andReturn([
            'backend' => 'supabase', 'storage_path' => 'TEST-ONLY/original.pdf',
        ]);
        $this->app->instance(StorageService::class, $storage);
        $user = User::factory()->create();
        $this->actingAs($user)->postJson('/translate', [
            'source_lang' => 'English', 'target_lang' => 'Cebuano', 'ocr_mode' => 'strict',
            'document' => UploadedFile::fake()->createWithContent('fixture.pdf', "%PDF-1.4\nTEST FIXTURE"),
        ])->assertOk()->assertJsonPath('status', 'processing');
        $payload = json_decode(DB::table('jobs')->first()->payload, true);
        $job = unserialize($payload['data']['command']);
        $this->assertInstanceOf(TranslateDocumentJob::class, $job);
        $this->assertSame(TranslationJob::PDF_UPLOAD_OCR_MODE, $job->ocrMode);
    }

    public function test_invalid_mode_is_rejected_before_dispatch(): void
    {
        $this->actingAs(User::factory()->create())->postJson('/translate', [
            'source_lang' => 'English', 'target_lang' => 'Cebuano', 'ocr_mode' => 'preview',
            'document' => UploadedFile::fake()->createWithContent('fixture.pdf', "%PDF-1.4\nTEST FIXTURE"),
        ])->assertUnprocessable()->assertJsonValidationErrors('ocr_mode');
        $this->assertSame(0, DB::table('jobs')->count());
    }

    public function test_image_uploads_are_rejected_before_dispatch(): void
    {
        $this->actingAs(User::factory()->create())->postJson('/translate', [
            'source_lang' => 'English', 'target_lang' => 'Cebuano',
            'document' => UploadedFile::fake()->image('photo.png', 240, 240),
        ])->assertUnprocessable()->assertJsonValidationErrors('document');
        $this->assertSame(0, DB::table('jobs')->count());
    }

    public function test_preview_and_strict_jobs_do_not_reuse_each_other(): void
    {
        $strict = TranslationJob::payloadHash(7, 'fixture-hash', 'English', 'Cebuano');
        $preview = TranslationJob::payloadHash(7, 'fixture-hash', 'English', 'Cebuano', 'balanced', 'auto', null, 'preview');
        $disabled = TranslationJob::payloadHash(7, 'fixture-hash', 'English', 'Cebuano', ocrMode: TranslationJob::PDF_UPLOAD_OCR_MODE);
        $this->assertNotSame($strict, $preview);
        $this->assertNotSame($strict, $disabled);
        $this->assertNotSame($preview, $disabled);
        $this->assertSame(hash('sha256', '7|fixture-hash|English|Cebuano|balanced|auto|'), $strict);
    }

    public function test_manager_forwards_preview_to_engine_and_preserves_unverified_summary(): void
    {
        Http::fake(['*' => Http::response([
            'file_base64' => base64_encode('%PDF-TEST'), 'download_filename' => 'fixture_ocr_preview.pdf',
            'content_summary' => ['status' => 'complete', 'ocr_mode' => 'preview', 'ocr_verified' => false],
        ])]);
        $result = app(TranslationManager::class)->translateDocument(
            UploadedFile::fake()->createWithContent('fixture.pdf', '%PDF-TEST'),
            'English', 'Cebuano', 'auto', 'fast', 'preview',
        );
        Http::assertSent(fn ($request) => (collect($request->data())->firstWhere('name', 'ocr_mode')['contents'] ?? null) === 'preview');
        $this->assertFalse($result['content_summary']['ocr_verified']);
    }

    public function test_manager_forwards_pdf_render_checkpoint_id(): void
    {
        $jobId = (string) \Illuminate\Support\Str::uuid();
        Http::fake(['*' => Http::response(['file_base64' => base64_encode('%PDF-TEST')])]);

        app(TranslationManager::class)->translateDocument(
            UploadedFile::fake()->createWithContent('fixture.pdf', '%PDF-TEST'),
            'English', 'Cebuano', renderCheckpointId: $jobId,
        );

        Http::assertSent(fn ($request) => collect($request->data())
            ->pluck('contents', 'name')->get('render_checkpoint_id') === $jobId);
    }

    public function test_complete_preview_cannot_be_mislabelled_verified(): void
    {
        $user = User::factory()->create(['is_admin' => true]);
        $history = \App\Models\TranslationHistory::create([
            'user_id' => $user->id, 'translation_type' => 'document', 'status' => 'completed',
            'source_language' => 'English', 'target_language' => 'Cebuano', 'review_status' => 'pending',
            'sidecar' => ['content_summary' => ['status' => 'complete', 'ocr_mode' => 'preview', 'ocr_verified' => false]],
        ]);
        $this->expectException(\App\Exceptions\TranslationException::class);
        $this->expectExceptionMessage('unverified OCR preview');
        app(\App\Services\Admin\ReviewService::class)->verifyDocument($history->id, $user->id);
    }
}
