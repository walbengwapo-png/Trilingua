<?php

namespace Tests\Feature\Admin;

use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationBlock;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Services\BlockService;
use App\Services\HistoryService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class ReviewBlocksPersistenceTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Helper: build the JSON envelope the Python service now returns.
     */
    private function envelope(): array
    {
        $blocks = [
            [
                'block_index' => 0,
                'block_type' => 'paragraph',
                'source_text' => 'Hello world',
                'ai_translated_text' => 'Kumusta kalibutan',
                'current_text' => 'Kumusta kalibutan',
                'quality_score' => 92,
                'quality_issues' => [['severity' => 'low', 'category' => 'tone']],
            ],
            [
                'block_index' => 1,
                'block_type' => 'paragraph',
                'source_text' => 'Good morning',
                'ai_translated_text' => 'Maayong buntag',
                'current_text' => 'Maayong buntag',
                'quality_score' => 85,
                'quality_issues' => [],
            ],
        ];

        return [
            'file_base64' => base64_encode('fake-translated-file-bytes'),
            'blocks' => $blocks,
            'sidecar' => [
                'version' => 2,
                'format' => '.txt',
                'source_lang' => 'English',
                'target_lang' => 'Cebuano',
                'pdf_column_mode' => 'auto',
                'blocks' => $blocks,
            ],
            'download_filename' => 'sample_translated.txt',
            'mime_type' => 'text/plain',
        ];
    }

    public function test_translated_blocks_land_in_translation_blocks_after_translation(): void
    {
        $user = \App\Models\User::factory()->create(['is_admin' => true]);

        Http::fake([
            '*/translate/document' => Http::response($this->envelope(), 200),
        ]);

        // Create a temp original file.
        $tempPath = storage_path('app/testing/' . uniqid('orig-') . '.txt');
        if (!is_dir(dirname($tempPath))) {
            mkdir(dirname($tempPath), 0755, true);
        }
        file_put_contents($tempPath, 'hello world');

        $translationManager = app(\App\Services\Translation\TranslationManager::class);
        $storageService = \Mockery::mock(\App\Services\StorageService::class);
        $storageService->shouldReceive('uploadWithFallback')->once()->andReturn([
            'backend' => 'supabase',
            'storage_path' => '5/output.txt',
            'signed_url' => 'https://example.test/output',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        $metricsService = \Mockery::mock(\App\Services\MetricsService::class);

        $job = new TranslateDocumentJob(
            'sample.txt',
            '.txt',
            11,
            'English',
            'Cebuano',
            'auto',
            $tempPath,
            $user->id,
            '5/originals/sample.txt',
        );

        $job->handle(
            $translationManager,
            $storageService,
            app(HistoryService::class),
            app(BlockService::class),
            $metricsService,
        );

        // ── Proof: blocks persisted with correct owners and values.
        $history = TranslationHistory::where('user_id', $user->id)->latest('id')->firstOrFail();
        $blocks = $history->blocks()->orderBy('block_index')->get();

        $this->assertCount(2, $blocks);
        $this->assertSame('pending', $blocks[0]->status);

        // ai_translated_text and current_text are set from the envelope.
        $this->assertSame('Kumusta kalibutan', $blocks[0]->ai_translated_text);
        $this->assertSame('Kumusta kalibutan', $blocks[0]->current_text);
        $this->assertSame('paragraph', $blocks[0]->block_type);
        $this->assertSame('Maayong buntag', $blocks[1]->current_text);

        // Quality rolled up onto the history row. (92 + 85) / 2 = 88.5 → 88
        $this->assertSame(89, $history->quality_score);

        // Sidecar persisted for regeneration.
        $this->assertIsArray($history->sidecar);
        $this->assertSame('.txt', $history->sidecar['format'] ?? null);

        @unlink($tempPath);
    }

    public function test_ai_translated_text_is_never_overwritten_without_edit_log(): void
    {
        $user = \App\Models\User::factory()->create(['is_admin' => true]);
        $admin = \App\Models\User::factory()->create(['is_admin' => true]);

        $history = TranslationHistory::create([
            'user_id' => $user->id,
            'translation_type' => 'document',
            'original_filename' => 'sample.txt',
            'translated_filename' => 'sample_translated.txt',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'original_storage_path' => '5/originals/sample.txt',
            'status' => 'completed',
            'review_status' => 'pending',
            'sidecar' => [
                'version' => 2,
                'format' => '.txt',
                'source_lang' => 'English',
                'target_lang' => 'Cebuano',
                'blocks' => [
                    ['block_index' => 0, 'text' => 'Kumusta kalibon', 'current_text' => 'Kumusta kalibon'],
                ],
            ],
        ]);

        $block = TranslationBlock::create([
            'translation_history_id' => $history->id,
            'block_index' => 0,
            'block_type' => 'paragraph',
            'source_text' => 'Hello world',
            'ai_translated_text' => 'Kumusta kalibon',
            'current_text' => 'Kumusta kalibon',
            'status' => 'pending',
        ]);

        // Mock the downstream collaborators so no real regeneration or
        // Supabase round-trip happens — we only assert the audit invariant.
        $translationManager = \Mockery::mock(\App\Services\Translation\TranslationManager::class);
        $translationManager->shouldReceive('regenerateDocument')
            ->once()
            ->andReturn([
                'body' => 'regenerated-file-bytes',
                'download_filename' => 'sample_regenerated.txt',
                'mime_type' => 'text/plain',
            ]);

        $storage = \Mockery::mock(\App\Services\StorageService::class);
        // Original read (backend-aware) + readability verification of the new object.
        $storage->shouldReceive('read')->andReturn('original-bytes');
        $storage->shouldReceive('uploadWithFallback')->once()->andReturn([
            'backend' => 'supabase',
            'storage_path' => $history->user_id . '/translations/regenerated.txt',
            'signed_url' => 'https://example.test/regenerated',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        $storage->shouldReceive('delete')->never();

        $this->app->instance(\App\Services\Translation\TranslationManager::class, $translationManager);
        $this->app->instance(\App\Services\StorageService::class, $storage);

        $review = app(\App\Services\Admin\ReviewService::class);

        $review->saveAndRegenerate(
            $history->id,
            $admin->id,
            [$block->id => 'Kumusta kalibutan'],
        );

        // The incoming override was probably consumed by a mocked translation
        // manager — this test only asserts the audit-log invariant is held.
        $freshBlock = $block->fresh();
        $log = TranslationEditLog::where('translation_block_id', $block->id)->latest('id')->first();

        // current_text reflects the admin edit.
        $this->assertSame('Kumusta kalibutan', $freshBlock->current_text);
        // ai_translated_text is immutable — untouched.
        $this->assertSame('Kumusta kalibon', $freshBlock->ai_translated_text);
        // The edit was audited with the PREVIOUS value.
        $this->assertNotNull($log);
        $this->assertSame('edit', $log->action);
        $this->assertSame('Kumusta kalibon', $log->previous_text);
        $this->assertSame('Kumusta kalibutan', $log->new_text);

        // The success path published the draft: revisions match, the pointer
        // moved to the canonical translations key, the backend was persisted,
        // and a publish audit row was appended.
        $fresh = $history->fresh();
        $this->assertSame(1, (int) $fresh->draft_revision);
        $this->assertSame(1, (int) $fresh->published_revision);
        $this->assertFalse($fresh->hasUnpublishedEdits());
        $this->assertSame('supabase', $fresh->storage_backend);
        $this->assertStringContainsString(
            $fresh->user_id . '/translations/',
            (string) $fresh->storage_path,
            'Regenerated outputs must use the canonical translations key.',
        );
        $publish = TranslationEditLog::where('translation_history_id', $history->id)->where('action', 'publish')->latest('id')->first();
        $this->assertNotNull($publish);
    }
}