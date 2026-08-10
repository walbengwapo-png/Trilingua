<?php

namespace Tests\Feature\Admin;

use App\Models\TranslationBlock;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

/**
 * End-to-end HTTP coverage for the /admin write-action routes: prove each
 * routes through middleware (admin-only), performs the transition, and audits
 * the previous/new text.
 */
class AdminWriteHttpTest extends TestCase
{
    use RefreshDatabase;

    private function makeAdmin(): User
    {
        return User::factory()->create(['is_admin' => true]);
    }

    private function makeUser(): User
    {
        return User::factory()->create(['is_admin' => false]);
    }

    private function makeTextRecord(User $submitter, array $overrides = []): TranslationHistory
    {
        return TranslationHistory::create(array_merge([
            'user_id' => $submitter->id,
            'translation_type' => 'text',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'source_text' => 'Hello world',
            'translated_text' => 'Kumusta kalibutan',
            'status' => 'completed',
            'review_status' => 'pending',
            'quality_score' => 70,
        ], $overrides));
    }

    private function makeDocRecord(User $submitter): TranslationHistory
    {
        $history = TranslationHistory::create([
            'user_id' => $submitter->id,
            'translation_type' => 'document',
            'original_filename' => 'contract.pdf',
            'translated_filename' => 'contract_ceb.pdf',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'original_storage_path' => '1/originals/contract.pdf',
            'status' => 'completed',
            'review_status' => 'pending',
            'quality_score' => 60,
        ]);

        TranslationBlock::create([
            'translation_history_id' => $history->id,
            'block_index' => 0,
            'block_type' => 'paragraph',
            'source_text' => 'Hello world',
            'ai_translated_text' => 'Kumusta kalibutan',
            'current_text' => 'Kumusta kalibutan',
            'quality_score' => 90,
            'status' => 'pending',
        ]);

        return $history;
    }

    // ── Middleware ──────────────────────────────────────────────────────

    public function test_write_routes_are_forbidden_for_non_admin(): void
    {
        $user = $this->makeUser();
        $record = $this->makeTextRecord($user);

        $this->actingAs($user)
            ->postJson("/admin/review/{$record->id}/verify")
            ->assertForbidden();

        $this->assertSame('pending', $record->fresh()->review_status);
    }

    public function test_write_routes_redirect_guests_to_login(): void
    {
        $record = $this->makeTextRecord($this->makeUser());

        $this->postJson("/admin/review/{$record->id}/verify")
            ->assertUnauthorized();
    }

    // ── Text write actions over HTTP ─────────────────────────────────────

    public function test_http_text_verify(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeTextRecord($this->makeUser());

        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/verify")
            ->assertOk()
            ->assertJson(['success' => true, 'status' => 'verified']);

        $this->assertSame('verified', $record->fresh()->review_status);
        $log = TranslationEditLog::where('translation_history_id', $record->id)->latest('id')->first();
        $this->assertNotNull($log);
        $this->assertSame('verify', $log->action);
    }

    public function test_http_text_update_validates_and_edits(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeTextRecord($this->makeUser());

        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/update", ['translated_text' => 'Bag-ong hubad'])
            ->assertOk()
            ->assertJson(['success' => true, 'status' => 'edited']);

        $fresh = $record->fresh();
        $this->assertSame('edited', $fresh->review_status);
        $this->assertSame('Bag-ong hubad', $fresh->translated_text);

        $log = TranslationEditLog::where('translation_history_id', $record->id)->latest('id')->first();
        $this->assertSame('Kumusta kalibutan', $log->previous_text);
        $this->assertSame('Bag-ong hubad', $log->new_text);
    }

    public function test_http_text_flag_with_reason(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeTextRecord($this->makeUser());

        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/flag", ['reason' => 'hallucination', 'note' => 'Added words'])
            ->assertOk()
            ->assertJson(['success' => true, 'status' => 'flagged']);

        $fresh = $record->fresh();
        $this->assertSame('flagged', $fresh->review_status);
        $this->assertSame('hallucination', $fresh->flag_reason);
    }

    public function test_http_text_flag_rejects_invalid_reason(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeTextRecord($this->makeUser());

        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/flag", ['reason' => 'bad'])
            ->assertStatus(422);

        $this->assertSame('pending', $record->fresh()->review_status);
    }

    // ── Document write actions over HTTP ─────────────────────────────────

    public function test_http_document_verify_cascades_to_blocks(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $block = $history->blocks->first();

        $this->actingAs($admin)
            ->postJson("/admin/review/{$history->id}/verify-document")
            ->assertOk()
            ->assertJson(['success' => true, 'status' => 'verified']);

        $this->assertSame('verified', $history->fresh()->review_status);
        $this->assertSame('verified', $block->fresh()->status);
    }

    public function test_http_block_update_edits_current_and_preserves_ai(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $block = $history->blocks->first();

        $this->actingAs($admin)
            ->postJson("/admin/review/{$history->id}/blocks/{$block->id}/update", ['current_text' => 'Edited text'])
            ->assertOk();

        $fresh = $block->fresh();
        $this->assertSame('edited', $fresh->status);
        $this->assertSame('Edited text', $fresh->current_text);
        $this->assertSame('Kumusta kalibutan', $fresh->ai_translated_text);
    }

    public function test_http_document_flag_cascades_to_blocks(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $block = $history->blocks->first();

        $this->actingAs($admin)
            ->postJson("/admin/review/{$history->id}/flag-document", ['reason' => 'mistranslation', 'note' => 'Check this'])
            ->assertOk()
            ->assertJson(['success' => true, 'status' => 'flagged']);

        $this->assertSame('flagged', $history->fresh()->review_status);
        $this->assertSame('flagged', $block->fresh()->status);
        $this->assertSame('mistranslation', $block->fresh()->flag_reason);
    }

    public function test_http_document_flag_rejects_missing_reason(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());

        $this->actingAs($admin)
            ->postJson("/admin/review/{$history->id}/flag-document", ['reason' => ''])
            ->assertStatus(422);

        $this->assertSame('pending', $history->fresh()->review_status);
    }

    public function test_http_save_regenerate_returns_new_and_original_links(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());

        // Mock the storage + translation manager so no real Supabase/Python call.
        $storage = \Mockery::mock(\App\Services\StorageService::class);
        $storage->shouldReceive('downloadFile')->once()->andReturn('original-bytes');
        $storage->shouldReceive('uploadFile')->once()->andReturn([
            'storage_path' => '1/regenerated.pdf',
            'signed_url' => 'https://supabase.test/regenerated',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        $storage->shouldReceive('generateSignedUrl')->once()->andReturn([
            'signed_url' => 'https://supabase.test/original',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        $this->app->instance(\App\Services\StorageService::class, $storage);

        $translationManager = \Mockery::mock(\App\Services\Translation\TranslationManager::class);
        $translationManager->shouldReceive('regenerateDocument')
            ->once()
            ->andReturn([
                'body' => 'regenerated-bytes',
                'download_filename' => 'contract_regenerated.pdf',
                'mime_type' => 'application/pdf',
            ]);
        $this->app->instance(\App\Services\Translation\TranslationManager::class, $translationManager);

        Http::fake();

        $this->actingAs($admin)
            ->postJson("/admin/review/{$history->id}/save-regenerate")
            ->assertOk()
            ->assertJson([
                'success' => true,
                'new_download_url' => 'https://supabase.test/regenerated',
                'original_download_url' => 'https://supabase.test/original',
            ]);
    }

    public function test_http_save_regenerate_persists_unsaved_block_edits(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $block = $history->blocks->first();

        $storage = \Mockery::mock(\App\Services\StorageService::class);
        $storage->shouldReceive('downloadFile')->once()->andReturn('original-bytes');
        $storage->shouldReceive('uploadFile')->once()->andReturn([
            'storage_path' => '1/regenerated.pdf',
            'signed_url' => 'https://supabase.test/regenerated',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        $storage->shouldReceive('generateSignedUrl')->once()->andReturn([
            'signed_url' => 'https://supabase.test/original',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        $this->app->instance(\App\Services\StorageService::class, $storage);

        // The regeneration must be driven by the posted edit, proving unsaved
        // textarea changes make it into the reconstructed document.
        $translationManager = \Mockery::mock(\App\Services\Translation\TranslationManager::class);
        $translationManager->shouldReceive('regenerateDocument')
            ->once()
            ->withArgs(function ($originalBytes, $originalName, $sidecar, $overrides) {
                return ($overrides[0] ?? null) === 'Unsa nga hubad';
            })
            ->andReturn([
                'body' => 'regenerated-bytes',
                'download_filename' => 'contract_regenerated.pdf',
                'mime_type' => 'application/pdf',
            ]);
        $this->app->instance(\App\Services\Translation\TranslationManager::class, $translationManager);

        Http::fake();

        $this->actingAs($admin)
            ->postJson("/admin/review/{$history->id}/save-regenerate", [
                'blocks' => [$block->id => 'Unsa nga hubad'],
            ])
            ->assertOk()
            ->assertJsonPath('edited_blocks', 1);

        // The edit was persisted through the audited path before regeneration.
        $fresh = $block->fresh();
        $this->assertSame('Unsa nga hubad', $fresh->current_text);
        $this->assertSame('edited', $fresh->status);
        $this->assertSame('Kumusta kalibutan', $fresh->ai_translated_text);
        $this->assertSame('edited', $history->fresh()->review_status);

        $log = TranslationEditLog::where('translation_history_id', $history->id)->latest('id')->first();
        $this->assertNotNull($log);
        $this->assertSame('edit', $log->action);
        $this->assertSame('Kumusta kalibutan', $log->previous_text);
        $this->assertSame('Unsa nga hubad', $log->new_text);
    }

    // ── Dashboard ───────────────────────────────────────────────────────

    public function test_admin_dashboard_renders(): void
    {
        $admin = $this->makeAdmin();
        $this->makeTextRecord($this->makeUser(), ['review_status' => 'verified']);
        $this->makeTextRecord($this->makeUser(), ['review_status' => 'flagged', 'flag_reason' => 'mistranslation']);

        $this->actingAs($admin)
            ->get('/admin')
            ->assertOk()
            ->assertSee('Admin Dashboard')
            ->assertSee('Mistranslation')
            ->assertSee('Verified');
    }
}