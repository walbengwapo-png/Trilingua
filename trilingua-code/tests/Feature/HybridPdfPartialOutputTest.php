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
}
