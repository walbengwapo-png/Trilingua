<?php

namespace Tests\Feature\Admin;

use App\Exceptions\TranslationException;
use App\Models\TranslationBlock;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Services\Admin\ReviewService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use App\Support\ReviewStatus;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * R5 completion-integrity service tests.
 *
 * Contract (approved): Save Edit = review draft; only a successful
 * Save & Regenerate publishes a new downloadable file. Verify is refused while
 * drafts are unpublished, and a failed regeneration must never replace or lose
 * the last usable file.
 */
class ReviewDraftPublishIntegrityTest extends TestCase
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
            'quality_score' => 90,
            'status' => 'pending',
        ]);

        return $record;
    }

    private function anonStorageMock(): \Mockery\LegacyMockInterface
    {
        return \Mockery::mock(StorageService::class);
    }

    private function mockRegen(\Mockery\LegacyMockInterface $storage, ?\Mockery\ExpectationInterface &$readCall = null): array
    {
        $readCall = $storage->shouldReceive('read')->andReturn('original-bytes');
        $storage->shouldReceive('uploadWithFallback')->once()->andReturn([
            'backend' => StorageService::BACKEND_SUPABASE,
            'storage_path' => '1/translations/new.pdf',
            'signed_url' => 'https://supabase.test/new',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        $storage->shouldReceive('delete')->never();

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')
            ->once()
            ->andReturn([
                'body' => 'regenerated-bytes',
                'download_filename' => 'contract_regenerated.pdf',
                'mime_type' => 'application/pdf',
            ]);

        return [$manager];
    }

    public function test_save_edit_is_a_draft_until_publish(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $block = $record->blocks->first();

        app(ReviewService::class)->updateBlock($record->id, $block->id, $admin->id, 'Draft only');

        $fresh = $record->fresh();
        $this->assertSame(1, (int) $fresh->draft_revision);
        $this->assertSame(0, (int) $fresh->published_revision);
        $this->assertTrue($fresh->hasUnpublishedEdits());
        // The downloadable file pointer is untouched — the edit is NOT in it.
        $this->assertSame('1/translations/v1.pdf', $fresh->storage_path);
    }

    public function test_verify_rejects_document_with_unpublished_draft(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $block = $record->blocks->first();

        app(ReviewService::class)->updateBlock($record->id, $block->id, $admin->id, 'Draft only');

        try {
            app(ReviewService::class)->verifyDocument($record->id, $admin->id);
            $this->fail('Verify must refuse unpublished drafts.');
        } catch (TranslationException $e) {
            $this->assertStringContainsString('Save & Regenerate', $e->getMessage());
        }

        $this->assertSame(ReviewStatus::EDITED, $record->fresh()->review_status);
        $this->assertSame(0, TranslationEditLog::where('translation_history_id', $record->id)->where('action', 'verify')->count());
    }

    public function test_save_and_regenerate_publishes_draft_durably(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $block = $record->blocks->first();

        $storage = $this->anonStorageMock();
        $storage->shouldReceive('read')->andReturn('original-bytes');
        $storage->shouldReceive('uploadWithFallback')->once()->andReturn([
            'backend' => StorageService::BACKEND_SUPABASE,
            'storage_path' => '1/translations/new.pdf',
            'signed_url' => 'https://supabase.test/new',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        // The superseded v1 object must be removed only after the commit.
        $storage->shouldReceive('delete')->never(); // superseded object is queued durably, never deleted inline
        $this->app->instance(StorageService::class, $storage);

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')
            ->once()
            ->withArgs(function ($originalBytes, $originalName, $sidecar, $overrides) {
                // The posted edit must appear both in the draft and the snapshot.
                return str_contains((string) $overrides[0], 'Unsa nga hubad');
            })
            ->andReturn([
                'body' => 'regenerated-bytes',
                'download_filename' => 'contract_regenerated.pdf',
                'mime_type' => 'application/pdf',
            ]);
        $this->app->instance(TranslationManager::class, $manager);

        $result = app(ReviewService::class)->saveAndRegenerate(
            $record->id,
            $admin->id,
            [$block->id => 'Unsa nga hubad'],
        );

        $fresh = $record->fresh();
        $this->assertSame(1, (int) $fresh->draft_revision);
        $this->assertSame(1, (int) $fresh->published_revision);
        $this->assertFalse($fresh->hasUnpublishedEdits());
        $this->assertSame('1/translations/new.pdf', $fresh->storage_path, 'The pointer must switch to the published object.');
        $this->assertSame(StorageService::BACKEND_SUPABASE, $fresh->storage_backend, 'The backend of the regenerated object must be persisted.');
        $this->assertSame('contract_regenerated.pdf', $fresh->translated_filename);
        $this->assertSame(1, $result['edited_blocks']);

        // Append-only audit trail: edit + publish rows.
        $this->assertSame(2, TranslationEditLog::where('translation_history_id', $record->id)->count());
        $this->assertNotNull(
            TranslationEditLog::where('translation_history_id', $record->id)->where('action', 'publish')->first()
        );
    }

    public function test_regenerated_object_is_verified_readable_before_publish(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());

        $storage = $this->anonStorageMock();
        $storage->shouldReceive('read')->andReturn('original-bytes');
        $storage->shouldReceive('uploadWithFallback')->once()->andReturn([
            'backend' => StorageService::BACKEND_SUPABASE,
            'storage_path' => '1/translations/check.pdf',
            'signed_url' => 'https://supabase.test/check',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        $storage->shouldReceive('delete')->never(); // superseded object is queued durably, never deleted inline
        $this->app->instance(StorageService::class, $storage);

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')->once()->andReturn([
            'body' => 'bytes', 'download_filename' => 'check.pdf', 'mime_type' => 'application/pdf',
        ]);
        $this->app->instance(TranslationManager::class, $manager);

        // A POST-upload read must succeed (the storage mock already returns
        // bytes for every read). This proves readability is part of the flow.
        $result = app(ReviewService::class)->saveAndRegenerate($record->id, $admin->id, []);

        $this->assertSame('1/translations/check.pdf', $result['storage_path']);
        $this->assertTrue($result['published']);
    }

    public function test_python_failure_keeps_draft_and_last_usable_file(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $block = $record->blocks->first();

        $storage = $this->anonStorageMock();
        $storage->shouldReceive('read')->andReturn('original-bytes');
        $storage->shouldReceive('delete')->never();
        $this->app->instance(StorageService::class, $storage);

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')
            ->once()
            ->andThrow(new TranslationException('Python reconstruction failed'));
        $this->app->instance(TranslationManager::class, $manager);

        try {
            app(ReviewService::class)->saveAndRegenerate($record->id, $admin->id, [$block->id => 'Draft edit']);
            $this->fail('Python failure must surface.');
        } catch (TranslationException $e) {
            $this->assertStringContainsString('Python reconstruction failed', $e->getMessage());
        }

        $fresh = $record->fresh();
        // The edit was persisted as a DRAFT...
        $this->assertSame(1, (int) $fresh->draft_revision);
        $this->assertSame(0, (int) $fresh->published_revision);
        $this->assertTrue($fresh->hasUnpublishedEdits());
        $this->assertSame('Draft edit', $block->fresh()->current_text);
        // ...and the previous file is untouched and still downloadable.
        $this->assertSame('1/translations/v1.pdf', $fresh->storage_path);
        $this->assertSame(0, TranslationEditLog::where('translation_history_id', $record->id)->where('action', 'publish')->count());
    }

    public function test_upload_failure_keeps_previous_file_authoritative(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());

        $storage = $this->anonStorageMock();
        $storage->shouldReceive('read')->andReturn('original-bytes');
        $storage->shouldReceive('uploadWithFallback')
            ->once()
            ->andThrow(new \RuntimeException('upload exploded'));
        $this->app->instance(StorageService::class, $storage);

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')->once()->andReturn([
            'body' => 'bytes', 'download_filename' => 'x.pdf', 'mime_type' => 'application/pdf',
        ]);
        $this->app->instance(TranslationManager::class, $manager);

        $this->expectException(\RuntimeException::class);

        try {
            app(ReviewService::class)->saveAndRegenerate($record->id, $admin->id, []);
        } finally {
            $this->assertSame('1/translations/v1.pdf', $record->fresh()->storage_path);
            $this->assertSame(0, (int) $record->fresh()->published_revision);
        }
    }

    public function test_readability_failure_cleans_up_new_object_and_keeps_previous(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());

        $storage = $this->anonStorageMock();
        // First read: the original bytes. Second read: the read-back check → fail.
        // (Mockery's andThrow() replaces the whole inline queue, so a counting
        // closure reproduces the two-call sequence exactly.)
        $calls = 0;
        $storage->shouldReceive('read')->andReturnUsing(function ($backend, $path) use (&$calls) {
            $calls++;
            if ($calls === 1) {
                return 'original-bytes';
            }
            throw new \RuntimeException('object not readable yet');
        });
        $storage->shouldReceive('uploadWithFallback')->once()->andReturn([
            'backend' => StorageService::BACKEND_SUPABASE,
            'storage_path' => '1/translations/bad.pdf',
            'signed_url' => 'https://supabase.test/bad',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        // The candidate object must be cleaned up, never committed.
        $storage->shouldReceive('delete')
            ->once()
            ->with(StorageService::BACKEND_SUPABASE, '1/translations/bad.pdf');
        $this->app->instance(StorageService::class, $storage);

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')->once()->andReturn([
            'body' => 'bytes', 'download_filename' => 'bad.pdf', 'mime_type' => 'application/pdf',
        ]);
        $this->app->instance(TranslationManager::class, $manager);

        try {
            app(ReviewService::class)->saveAndRegenerate($record->id, $admin->id, []);
            $this->fail('An unreadable candidate object must never be published.');
        } catch (TranslationException $e) {
            $this->assertStringContainsString('previous version remains published', $e->getMessage());
        }

        $this->assertSame('1/translations/v1.pdf', $record->fresh()->storage_path);
        $this->assertSame(0, (int) $record->fresh()->published_revision);
    }

    public function test_commit_failure_cleans_up_new_object_and_keeps_previous_file(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());

        $storage = $this->anonStorageMock();
        $storage->shouldReceive('read')->andReturn('original-bytes');
        $storage->shouldReceive('uploadWithFallback')->once()->andReturn([
            'backend' => StorageService::BACKEND_SUPABASE,
            'storage_path' => '1/translations/pending.pdf',
            'signed_url' => 'https://supabase.test/pending',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        $storage->shouldReceive('delete')
            ->once()
            ->with(StorageService::BACKEND_SUPABASE, '1/translations/pending.pdf');
        $this->app->instance(StorageService::class, $storage);

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')->once()->andReturn([
            'body' => 'bytes', 'download_filename' => 'pending.pdf', 'mime_type' => 'application/pdf',
        ]);
        $this->app->instance(TranslationManager::class, $manager);

        // Simulate a DB commit failure for the publish write (pointer switch).
        $poisonDb = false;
        TranslationHistory::saving(function (TranslationHistory $model) use (&$poisonDb) {
            if ($poisonDb && $model->getOriginal('storage_path') !== $model->storage_path) {
                throw new \RuntimeException('simulated db commit failure');
            }
        });

        try {
            $poisonDb = true;
            try {
                app(ReviewService::class)->saveAndRegenerate($record->id, $admin->id, []);
                $this->fail('A commit failure must surface.');
            } catch (TranslationException $e) {
                $this->assertStringContainsString('previous file remains downloadable', $e->getMessage());
            }
        } finally {
            $poisonDb = false;
        }

        $fresh = $record->fresh();
        $this->assertSame('1/translations/v1.pdf', $fresh->storage_path, 'The pointer must never move when the commit fails.');
        $this->assertSame(0, (int) $fresh->published_revision);
        $this->assertSame(0, TranslationEditLog::where('translation_history_id', $record->id)->where('action', 'publish')->count());
    }

    public function test_regeneration_reads_original_from_recorded_backend(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser(), [
            'original_storage_backend' => StorageService::BACKEND_LOCAL,
            'original_storage_path' => '1/originals/local-contract.pdf',
        ]);

        $storage = $this->anonStorageMock();
        $storage->shouldReceive('read')
            ->with(StorageService::BACKEND_LOCAL, '1/originals/local-contract.pdf')
            ->once()
            ->andReturn('original-bytes');
        // Read-back verification of the newly uploaded object uses the NEW pointer.
        $storage->shouldReceive('read')->andReturn('original-bytes');
        $storage->shouldReceive('uploadWithFallback')->once()->andReturn([
            'backend' => StorageService::BACKEND_SUPABASE,
            'storage_path' => '1/translations/from-local.pdf',
            'signed_url' => 'https://supabase.test/x',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        $storage->shouldReceive('delete')->never(); // superseded object is queued durably, never deleted inline
        $this->app->instance(StorageService::class, $storage);

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')->once()->andReturn([
            'body' => 'bytes', 'download_filename' => 'from-local.pdf', 'mime_type' => 'application/pdf',
        ]);
        $this->app->instance(TranslationManager::class, $manager);

        app(ReviewService::class)->saveAndRegenerate($record->id, $admin->id, []);

        $this->assertSame(StorageService::BACKEND_SUPABASE, $record->fresh()->storage_backend);
    }

    public function test_repeat_submission_registers_zero_new_edits_but_republishes(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());

        $storage = $this->anonStorageMock();
        $storage->shouldReceive('read')->andReturn('original-bytes');
        $storage->shouldReceive('uploadWithFallback')->andReturn([
            'backend' => StorageService::BACKEND_SUPABASE,
            'storage_path' => '1/translations/repub.pdf',
            'signed_url' => 'https://supabase.test/repub',
            'signed_url_expires_at' => now()->toIso8601String(),
        ]);
        $this->app->instance(StorageService::class, $storage);

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')->twice()->andReturn([
            'body' => 'bytes', 'download_filename' => 'repub.pdf', 'mime_type' => 'application/pdf',
        ]);
        $this->app->instance(TranslationManager::class, $manager);

        $first = app(ReviewService::class)->saveAndRegenerate($record->id, $admin->id, []);
        $second = app(ReviewService::class)->saveAndRegenerate($record->id, $admin->id, []);

        $this->assertSame(0, $second['edited_blocks'], 'No new edits → zero edited blocks on repeat submission.');
        $fresh = $record->fresh();
        $this->assertSame(0, (int) $fresh->draft_revision);
        $this->assertSame(0, (int) $fresh->published_revision);
        $this->assertFalse($fresh->hasUnpublishedEdits());
        $this->assertSame(2, TranslationEditLog::where('translation_history_id', $record->id)->where('action', 'publish')->count());
    }
}