<?php

namespace Tests\Feature\Admin;

use App\Models\StorageCleanupOutbox;
use App\Models\TranslationBlock;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * Package B: stale-submission protection for draft editing and publication.
 *
 * A request based on an old draft revision or an old file pointer must NOT
 * overwrite newer draft text or republish over a newer file; it returns HTTP 409
 * and leaves state (and the previous published file) intact.
 */
class ReviewConcurrencyGuardTest extends TestCase
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

    private function makeDocRecord(User $submitter, array $overrides = []): TranslationHistory
    {
        $record = TranslationHistory::create(array_merge([
            'user_id' => $submitter->id,
            'translation_type' => 'document',
            'original_filename' => 'contract.pdf',
            'translated_filename' => 'contract_ceb.pdf',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'original_storage_path' => '1/originals/contract.pdf',
            'original_storage_backend' => StorageService::BACKEND_SUPABASE,
            'storage_path' => '1/translations/v1.pdf',
            'storage_backend' => StorageService::BACKEND_SUPABASE,
            'status' => 'completed',
            'review_status' => 'pending',
            'quality_score' => 60,
        ], $overrides));

        TranslationBlock::create([
            'translation_history_id' => $record->id,
            'block_index' => 0,
            'block_type' => 'paragraph',
            'source_text' => 'Hello world',
            'ai_translated_text' => 'Kumusta kalibutan',
            'current_text' => 'Kumusta kalibutan',
            'published_text' => 'Kumusta kalibutan',
            'quality_score' => 90,
            'status' => 'pending',
        ]);

        return $record;
    }

    public function test_block_update_with_stale_revision_returns_409_and_does_not_overwrite_draft(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $block = $record->blocks->first();

        // Another admin already moved the draft to revision 3.
        $record->forceFill(['draft_revision' => 3])->save();

        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/blocks/{$block->id}/update", [
                'current_text' => 'STALE OVERWRITE',
                'expected_draft_revision' => 0,
            ])
            ->assertStatus(409);

        $this->assertSame('Kumusta kalibutan', $block->fresh()->current_text, 'A stale edit must not overwrite newer draft text.');
        $this->assertSame(3, (int) $record->fresh()->draft_revision);
    }

    public function test_block_update_with_matching_revision_succeeds(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $block = $record->blocks->first();

        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/blocks/{$block->id}/update", [
                'current_text' => 'Bag-ong hubad',
                'expected_draft_revision' => 0,
            ])
            ->assertOk()
            ->assertJson(['success' => true, 'draft' => true]);

        $this->assertSame('Bag-ong hubad', $block->fresh()->current_text);
        $this->assertSame(1, (int) $record->fresh()->draft_revision);
    }

    public function test_publish_with_stale_pointer_returns_409_and_keeps_previous_file(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());

        $storage = \Mockery::mock(StorageService::class);
        $storage->shouldReceive('read')->andReturn('original-bytes');
        $storage->shouldReceive('uploadWithFallback')->once()->andReturn([
            'backend' => StorageService::BACKEND_SUPABASE,
            'storage_path' => '1/translations/candidate.pdf',
            'signed_url' => 'https://supabase.test/candidate',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        // On conflict the candidate object is cleaned up.
        $storage->shouldReceive('delete')->once()->with(StorageService::BACKEND_SUPABASE, '1/translations/candidate.pdf');
        $this->app->instance(StorageService::class, $storage);

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')->once()->andReturn([
            'body' => 'bytes', 'download_filename' => 'candidate.pdf', 'mime_type' => 'application/pdf',
        ]);
        $this->app->instance(TranslationManager::class, $manager);

        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/save-regenerate", [
                'expected_draft_revision' => 0,
                'expected_storage_path' => '1/translations/OLD.pdf', // stale pointer
            ])
            ->assertStatus(409);

        $fresh = $record->fresh();
        $this->assertSame('1/translations/v1.pdf', $fresh->storage_path, 'The previous published file stays authoritative.');
        $this->assertSame(0, (int) $fresh->published_revision);

        // The uncommitted candidate is not left referenced; it is queued durably.
        $this->assertFalse(
            StorageCleanupOutbox::where('path', '1/translations/candidate.pdf')->where('kind', 'candidate')->exists(),
            'A conflict must not leave a candidate row that could be mistaken for committed (cleanup already ran).'
        );
    }

    public function test_publish_with_stale_revision_returns_409_before_touching_storage(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $record->forceFill(['draft_revision' => 2])->save();

        // No storage/manager mocks: a stale revision must fail before any upload.
        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/save-regenerate", [
                'expected_draft_revision' => 0,
                'expected_storage_path' => '1/translations/v1.pdf',
            ])
            ->assertStatus(409);

        $this->assertSame(0, (int) $record->fresh()->published_revision);
        $this->assertSame('1/translations/v1.pdf', $record->fresh()->storage_path);
    }
}