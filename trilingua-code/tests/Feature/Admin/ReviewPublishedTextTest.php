<?php

namespace Tests\Feature\Admin;

use App\Models\TranslationBlock;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Services\Admin\ReviewService;
use App\Services\BlockService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use App\Support\LegacyPublishedTextBackfill;
use App\Support\ReviewStatus;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * Package B: publication + audit integrity.
 *
 * - published_text captures what the downloadable file actually contains and is
 *   updated only on a successful publish; current_text stays the draft and
 *   ai_translated_text stays immutable.
 * - the owner Final/Saved endpoint exposes published content only.
 * - legacy backfill is evidence based (ambiguous rows stay unknown).
 * - a review change + its audit row commit atomically.
 */
class ReviewPublishedTextTest extends TestCase
{
    use RefreshDatabase;

    protected function tearDown(): void
    {
        // Atomicity tests register TranslationEditLog creating listeners; clear
        // them so a forced failure never leaks into later tests.
        TranslationEditLog::flushEventListeners();
        parent::tearDown();
    }

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

    private function publishStorageMock(): void
    {
        $storage = \Mockery::mock(StorageService::class);
        $storage->shouldReceive('read')->andReturn('original-bytes');
        $storage->shouldReceive('uploadWithFallback')->andReturn([
            'backend' => StorageService::BACKEND_SUPABASE,
            'storage_path' => '1/translations/v2.pdf',
            'signed_url' => 'https://supabase.test/v2',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        $storage->shouldReceive('delete')->never();
        $this->app->instance(StorageService::class, $storage);

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')->andReturn([
            'body' => 'bytes', 'download_filename' => 'contract_v2.pdf', 'mime_type' => 'application/pdf',
        ]);
        $this->app->instance(TranslationManager::class, $manager);
    }

    public function test_publish_persists_published_text_snapshot_and_leaves_draft_and_ai_text(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $block = $record->blocks->first();

        // Draft edit: current_text changes, published_text must NOT yet.
        app(ReviewService::class)->updateBlock($record->id, $block->id, $admin->id, 'Bag-ong hubad');
        $this->assertSame('Bag-ong hubad', $block->fresh()->current_text);
        $this->assertSame('Kumusta kalibutan', $block->fresh()->published_text, 'Draft edit must not change published_text.');

        $this->publishStorageMock();
        app(ReviewService::class)->saveAndRegenerate($record->id, $admin->id, []);

        $fresh = $block->fresh();
        $this->assertSame('Bag-ong hubad', $fresh->current_text);
        $this->assertSame('Bag-ong hubad', $fresh->published_text, 'Publish must snapshot current_text into published_text.');
        $this->assertSame('Kumusta kalibutan', $fresh->ai_translated_text, 'ai_translated_text is immutable.');
        $this->assertSame(1, (int) $record->fresh()->published_revision);
        $this->assertSame(1, TranslationEditLog::where('translation_history_id', $record->id)->where('action', 'publish')->count());
    }

    public function test_owner_blocks_endpoint_exposes_published_only(): void
    {
        $owner = $this->makeUser();
        $record = $this->makeDocRecord($owner);
        $block = $record->blocks->first();

        // Move the draft away from the published snapshot.
        $block->current_text = 'DRAFT-SECRET';
        $block->save();

        $response = $this->actingAs($owner)->getJson("/history/{$record->id}/blocks");

        $response->assertOk();
        $json = $response->json('blocks.0');
        $this->assertSame('Kumusta kalibutan', $json['published_text']);
        $this->assertTrue($json['has_published']);
        $this->assertArrayNotHasKey('current_text', $json, 'Owner Final endpoint must not expose draft text.');
        $this->assertStringNotContainsString('DRAFT-SECRET', $response->getContent());
    }

    public function test_initial_translation_persists_published_text_equal_to_ai_text(): void
    {
        $record = $this->makeDocRecord($this->makeUser());
        $record->blocks()->delete();

        app(BlockService::class)->persistBlocks($record, [
            ['block_index' => 0, 'block_type' => 'paragraph', 'source_text' => 'Hi', 'ai_translated_text' => 'Kumusta'],
        ]);

        $block = $record->fresh()->blocks->first();
        $this->assertSame('Kumusta', $block->current_text);
        $this->assertSame('Kumusta', $block->published_text);
    }

    public function test_legacy_backfill_populates_only_unambiguous_rows(): void
    {
        // Ambiguous: has an edit audit row + moved revisions.
        $ambiguous = $this->makeDocRecord($this->makeUser(), [
            'draft_revision' => 1,
            'published_revision' => 0,
        ]);
        TranslationEditLog::create([
            'translation_history_id' => $ambiguous->id,
            'admin_id' => $this->makeAdmin()->id,
            'action' => 'edit',
            'previous_text' => 'a',
            'new_text' => 'b',
            'created_at' => now(),
        ]);
        $ambiguous->blocks()->update(['published_text' => null, 'current_text' => 'Draft text']);

        // Unambiguous: no edits, revisions 0, all blocks pending.
        $clean = $this->makeDocRecord($this->makeUser());
        $clean->blocks()->update(['published_text' => null]);

        $populated = LegacyPublishedTextBackfill::apply();

        $this->assertGreaterThanOrEqual(1, $populated);
        $this->assertNull($ambiguous->fresh()->blocks->first()->published_text, 'Ambiguous rows stay unknown.');
        $this->assertSame('Kumusta kalibutan', $clean->fresh()->blocks->first()->published_text);
    }

    public function test_batch_edit_rolls_back_entirely_when_an_audit_write_fails(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $blockA = $record->blocks->first();
        $blockB = TranslationBlock::create([
            'translation_history_id' => $record->id,
            'block_index' => 1,
            'block_type' => 'paragraph',
            'source_text' => 'Two',
            'ai_translated_text' => 'Duha',
            'current_text' => 'Duha',
            'published_text' => 'Duha',
            'status' => 'pending',
        ]);

        // Force the SECOND block's audit insert to fail.
        TranslationEditLog::creating(function ($log) {
            if ($log->action === 'edit' && $log->new_text === 'BOOM') {
                throw new \RuntimeException('simulated audit failure');
            }
        });

        try {
            app(ReviewService::class)->applyBlockEdits($record->id, $admin->id, [
                $blockA->id => 'Bag-ong A',
                $blockB->id => 'BOOM',
            ]);
            $this->fail('The audit failure must surface.');
        } catch (\RuntimeException $e) {
            $this->assertStringContainsString('simulated audit failure', $e->getMessage());
        }

        // The whole batch rolled back: no partial text, no revision bump, no audit.
        $this->assertSame('Kumusta kalibutan', $blockA->fresh()->current_text);
        $this->assertSame('Duha', $blockB->fresh()->current_text);
        $this->assertSame(0, (int) $record->fresh()->draft_revision);
        $this->assertSame(ReviewStatus::PENDING, $record->fresh()->review_status);
        $this->assertSame(0, TranslationEditLog::where('translation_history_id', $record->id)->count());
    }

    public function test_verify_status_and_audit_commit_atomically(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());

        TranslationEditLog::creating(function ($log) {
            if ($log->action === 'verify') {
                throw new \RuntimeException('simulated verify audit failure');
            }
        });

        try {
            app(ReviewService::class)->verifyDocument($record->id, $admin->id);
            $this->fail('The audit failure must surface.');
        } catch (\RuntimeException $e) {
            $this->assertStringContainsString('simulated verify audit failure', $e->getMessage());
        }

        $this->assertSame(ReviewStatus::PENDING, $record->fresh()->review_status, 'Status change rolled back with the audit failure.');
    }
}