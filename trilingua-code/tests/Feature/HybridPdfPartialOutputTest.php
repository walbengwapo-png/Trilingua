<?php

namespace Tests\Feature;

use App\Exceptions\TranslationException;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Services\Admin\ReviewService;
use App\Services\BlockService;
use App\Services\StorageService;
use App\Services\Translation\CompletedDownloadResolver;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class HybridPdfPartialOutputTest extends TestCase
{
    use RefreshDatabase;

    public function test_all_held_envelope_survives_history_status_review_and_download(): void
    {
        $user = User::factory()->create(['is_admin' => true]);
        $history = TranslationHistory::create([
            'user_id' => $user->id, 'translation_type' => 'document',
            'original_filename' => 'scan.pdf', 'translated_filename' => 'scan_untranslated.pdf',
            'source_language' => 'English', 'target_language' => 'Cebuano',
            'status' => 'completed', 'review_status' => 'pending',
            'storage_backend' => StorageService::BACKEND_LOCAL, 'storage_path' => 'output.pdf',
        ]);
        $sidecar = ['version' => 3, 'blocks' => [],
            'content_summary' => ['status' => 'untranslated', 'translated' => 0, 'held' => 1, 'passthrough' => 0],
            'extraction' => ['warnings' => ['Original region retained: ocr_acceptance_hold.']],
            'render_plan' => ['version' => 1, 'regions' => [
                ['page' => 0, 'source_kind' => 'raster', 'bbox' => [0, 0, 100, 100],
                    'status' => 'held', 'reason' => 'ocr_acceptance_hold'],
            ]],
        ];
        $this->assertSame(0, app(BlockService::class)->persistBlocks($history, [], $sidecar));
        $history->refresh();
        $this->assertSame($sidecar, $history->sidecar);
        $this->assertSame(0, $history->blocks()->count());
        $storage = \Mockery::mock(StorageService::class);
        $storage->shouldReceive('exists')->andReturn(StorageService::PRESENCE_PRESENT);
        $this->app->instance(StorageService::class, $storage);
        $payload = app(CompletedDownloadResolver::class)->resolve($history);
        $this->assertSame('untranslated', $payload['content_summary']['status']);
        $this->assertSame('scan_untranslated.pdf', $payload['download_filename']);
        $this->assertNotEmpty($payload['warnings']);
        $this->actingAs($user)->get("/history/{$history->id}")->assertOk()->assertJsonPath('sidecar.content_summary.status', 'untranslated');
        $this->get(route('history.view', $history->id))->assertOk()->assertSee('held regions retain the original language');
        $this->get(route('admin.review.show', $history->id))->assertOk()->assertSee('ocr_acceptance_hold');
        $this->get('/documents')->assertOk()->assertSee('held regions retain their original language')->assertDontSee('100% Complete');
        $this->expectException(TranslationException::class);
        app(ReviewService::class)->verifyDocument($history->id, $user->id);
    }

    public function test_legacy_empty_blocks_do_not_discard_existing_sidecar(): void
    {
        $user = User::factory()->create();
        $history = TranslationHistory::create(['user_id' => $user->id, 'translation_type' => 'document',
            'status' => 'completed', 'source_language' => 'English', 'target_language' => 'Cebuano', 'sidecar' => ['version' => 2, 'blocks' => []]]);
        app(BlockService::class)->persistBlocks($history, []);
        $this->assertSame(2, $history->refresh()->sidecar['version']);
    }

    public function test_partial_extraction_is_not_counted_as_complete_document_volume(): void
    {
        $user = User::factory()->create();
        $history = TranslationHistory::create(['user_id' => $user->id, 'translation_type' => 'document',
            'status' => 'completed', 'source_language' => 'English', 'target_language' => 'Cebuano']);
        app(BlockService::class)->persistBlocks($history, [
            ['block_index' => 0, 'source_text' => 'Known native words', 'ai_translated_text' => 'Fixed translation'],
        ], ['content_summary' => ['status' => 'partial', 'translated' => 1, 'held' => 1]]);
        $this->assertNull($history->refresh()->document_word_count);
        if ($history->source_word_metadata !== null) {
            $this->assertNull($history->source_word_metadata['count']);
            $this->assertSame('partial', $history->source_word_metadata['completeness']);
        }
    }

    public function test_text_verification_action_cannot_clear_incomplete_document_status(): void
    {
        $admin = User::factory()->create(['is_admin' => true]);
        foreach (['partial', 'untranslated'] as $status) {
            $history = TranslationHistory::create(['user_id' => $admin->id, 'translation_type' => 'document',
                'status' => 'completed', 'review_status' => 'pending', 'source_language' => 'English',
                'target_language' => 'Cebuano', 'sidecar' => ['content_summary' => ['status' => $status, 'held' => 1]]]);
            $this->actingAs($admin)->postJson("/admin/review/{$history->id}/verify")
                ->assertStatus(500)->assertJsonMissing(['success' => true]);
            $this->assertSame('pending', $history->refresh()->review_status);
            $this->assertSame($status, $history->sidecar['content_summary']['status']);
        }
    }

    public function test_history_does_not_show_100_percent_for_incomplete_documents(): void
    {
        $user = User::factory()->create();
        foreach (['partial', 'untranslated'] as $status) {
            TranslationHistory::create(['user_id' => $user->id, 'translation_type' => 'document',
                'original_filename' => 'source.pdf', 'translated_filename' => $status . '.pdf',
                'status' => 'completed', 'source_language' => 'English', 'target_language' => 'Cebuano',
                'sidecar' => ['content_summary' => ['status' => $status, 'held' => 1]]]);
        }
        $this->actingAs($user)->get('/history')->assertOk()
            ->assertSee('Content: Partial')->assertSee('Content: Untranslated')
            ->assertDontSee('<span class="match-badge">100%</span>', false);
    }

    public function test_region_reason_is_escaped_in_review_html(): void
    {
        $admin = User::factory()->create(['is_admin' => true]);
        $reason = '<img src=x onerror="window.marker=1">';
        $history = TranslationHistory::create(['user_id' => $admin->id, 'translation_type' => 'document',
            'original_filename' => 'source.pdf', 'status' => 'completed', 'review_status' => 'pending',
            'source_language' => 'English', 'target_language' => 'Cebuano', 'sidecar' => [
                'content_summary' => ['status' => 'untranslated', 'translated' => 0, 'held' => 1, 'passthrough' => 0],
                'render_plan' => ['regions' => [['region_id' => 'fixed', 'page' => 0, 'source_kind' => 'raster',
                    'bbox' => [0,0,100,100], 'status' => 'held', 'reason' => $reason]]],
            ]]);
        $this->actingAs($admin)->get(route('admin.review.show',$history->id))->assertOk()
            ->assertSee($reason)->assertDontSee($reason,false);
    }
}
