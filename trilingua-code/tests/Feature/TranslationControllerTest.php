<?php

namespace Tests\Feature;

use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationJob;
use App\Models\User;
use App\Services\BlockService;
use App\Services\HistoryService;
use App\Services\MetricsService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\DB;
use Mockery;
use Tests\TestCase;

class TranslationControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_document_translation_creates_durable_job_and_returns_job_id(): void
    {
        config(['queue.default' => 'database']);

        $user = User::factory()->create();

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('uploadWithFallback')
            ->once()
            ->andReturn([
                'backend' => 'supabase',
                'storage_path' => 'user/originals/abc.docx',
                'signed_url' => 'https://example.test/original',
                'signed_url_expires_at' => now()->toIso8601String(),
            ]);
        $this->app->instance(StorageService::class, $storage);

        $file = UploadedFile::fake()->createWithContent(
            'sample.docx',
            'PK' . random_bytes(256)
        );

        $response = $this->actingAs($user)->post('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => $file,
        ], ['Accept' => 'application/json']);

        $response->assertOk();
        $response->assertJsonPath('status', 'processing');
        $response->assertJsonStructure(['job_id', 'original_filename']);

        // Durable row created with canonical content hash + opaque storage key.
        $jobRow = TranslationJob::where('user_id', $user->id)->firstOrFail();
        $this->assertSame(64, strlen((string) $jobRow->payload_hash));
        $this->assertSame(TranslationJob::STATUS_QUEUED, $jobRow->status);
        $this->assertSame('user/originals/abc.docx', $jobRow->original_storage_path);

        // A single queued database job exists.
        $this->assertSame(1, DB::table('jobs')->count());
        $queued = DB::table('jobs')->first();
        $payload = json_decode($queued->payload, true);
        /** @var TranslateDocumentJob $queuedJob */
        $queuedJob = unserialize($payload['data']['command']);
        $this->assertInstanceOf(TranslateDocumentJob::class, $queuedJob);
        $this->assertSame((int) $jobRow->id, $queuedJob->translationJobId);
    }

    public function test_document_extension_spoof_is_rejected_before_processing(): void
    {
        $user = User::factory()->create();

        // NUL bytes = binary without DOCX zip magic; claim .docx → must 422.
        $file = UploadedFile::fake()->createWithContent(
            'malware.docx',
            "\x00\x00MZ\x90\x00" . random_bytes(64)
        );

        $response = $this->actingAs($user)->post('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => $file,
        ], ['Accept' => 'application/json']);

        $response->assertStatus(422);
        $this->assertSame(0, TranslationJob::count());
        $this->assertSame(0, DB::table('jobs')->count());
    }

    public function test_upload_quota_blocks_excessive_daily_documents(): void
    {
        config(['translation.upload.max_daily_files' => 1]);

        $user = User::factory()->create();

        // One document already counted today.
        \App\Models\TranslationHistory::create([
            'user_id'          => $user->id,
            'translation_type' => 'document',
            'source_language'  => 'English',
            'target_language'  => 'Cebuano',
            'created_at'       => now()->subMinute()->toIso8601String(),
            'status'           => 'completed',
        ]);

        $file = UploadedFile::fake()->createWithContent('e.docx', 'PK' . random_bytes(64));

        $response = $this->actingAs($user)->post('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => $file,
        ], ['Accept' => 'application/json']);

        $response->assertStatus(429);
        $this->assertSame(0, TranslationJob::count());
    }

    protected function tearDown(): void
    {
        Mockery::close();
        parent::tearDown();
    }
}