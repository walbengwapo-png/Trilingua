<?php

namespace Tests\Feature;

use App\Models\StorageCleanupOutbox;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Services\StorageCleanupService;
use App\Services\StorageService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * Package C: durable, idempotent cleanup that never deletes live data.
 */
class StorageCleanupServiceTest extends TestCase
{
    use RefreshDatabase;

    private function makeHistory(int $userId, string $storagePath): TranslationHistory
    {
        return TranslationHistory::create([
            'user_id' => $userId,
            'translation_type' => 'document',
            'original_filename' => 'contract.pdf',
            'translated_filename' => 'contract_ceb.pdf',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'storage_path' => $storagePath,
            'storage_backend' => StorageService::BACKEND_SUPABASE,
            'status' => 'completed',
            'review_status' => 'pending',
        ]);
    }

    private function storage(?\Mockery\ExpectationInterface &$deleteCall = null): \Mockery\LegacyMockInterface
    {
        $mock = \Mockery::mock(StorageService::class);
        $deleteCall = $mock->shouldReceive('delete');
        $this->app->instance(StorageService::class, $mock);

        return $mock;
    }

    public function test_process_pending_cancels_intent_for_a_live_referenced_path(): void
    {
        $user = User::factory()->create();
        $this->makeHistory($user->id, '1/translations/live.pdf');

        $storage = $this->storage($delete);
        $delete->never();

        $cleanup = app(StorageCleanupService::class);
        $cleanup->recordPending(StorageService::BACKEND_SUPABASE, '1/translations/live.pdf');
        $result = $cleanup->processPending();

        // The intent is cancelled (done) rather than deleting a live object.
        $this->assertDatabaseHas('storage_cleanup_outbox', [
            'backend' => 'supabase',
            'path' => '1/translations/live.pdf',
            'status' => 'done',
        ]);
        $this->assertSame(1, $result['processed']);
    }

    public function test_process_pending_deletes_an_orphan_path(): void
    {
        $storage = $this->storage($delete);
        $delete->once()->with(StorageService::BACKEND_SUPABASE, '1/translations/orphan.pdf');

        $cleanup = app(StorageCleanupService::class);
        $cleanup->recordPending(StorageService::BACKEND_SUPABASE, '1/translations/orphan.pdf');
        $result = $cleanup->processPending();

        $this->assertDatabaseHas('storage_cleanup_outbox', [
            'path' => '1/translations/orphan.pdf',
            'status' => 'done',
            'kind' => 'orphan',
        ]);
        $this->assertSame(0, $result['remaining']);
    }

    public function test_record_pending_rearms_a_done_row(): void
    {
        $cleanup = app(StorageCleanupService::class);

        StorageCleanupOutbox::create([
            'backend' => 'supabase',
            'path' => '1/translations/reused.pdf',
            'kind' => StorageCleanupService::KIND_ORPHAN,
            'status' => StorageCleanupOutbox::STATUS_DONE,
            'attempts' => 5,
        ]);

        $cleanup->recordPending('supabase', '1/translations/reused.pdf');

        $row = StorageCleanupOutbox::where('path', '1/translations/reused.pdf')->first();
        $this->assertSame(StorageCleanupOutbox::STATUS_PENDING, $row->status, 'A repeated intent must re-arm a done row.');
        $this->assertSame(0, (int) $row->attempts);
    }

    public function test_reclaim_stale_candidates_deletes_uncommitted_and_keeps_live(): void
    {
        $user = User::factory()->create();
        $this->makeHistory($user->id, '1/translations/committed.pdf');

        $stale = StorageCleanupOutbox::create([
            'backend' => 'supabase',
            'path' => '1/translations/candidate.pdf',
            'kind' => StorageCleanupService::KIND_CANDIDATE,
            'status' => StorageCleanupOutbox::STATUS_PENDING,
        ]);
        $stale->forceFill(['created_at' => now()->subHours(2)])->save();

        $liveCandidate = StorageCleanupOutbox::create([
            'backend' => 'supabase',
            'path' => '1/translations/committed.pdf',
            'kind' => StorageCleanupService::KIND_CANDIDATE,
            'status' => StorageCleanupOutbox::STATUS_PENDING,
        ]);
        $liveCandidate->forceFill(['created_at' => now()->subHours(2)])->save();

        $storage = $this->storage($delete);
        $delete->once()->with(StorageService::BACKEND_SUPABASE, '1/translations/candidate.pdf');

        $result = app(StorageCleanupService::class)->reclaimStalePublishCandidates(3600);

        $this->assertSame(1, $result['reclaimed']);
        $this->assertDatabaseHas('storage_cleanup_outbox', ['path' => '1/translations/candidate.pdf', 'status' => 'done']);
        $this->assertDatabaseHas('storage_cleanup_outbox', ['path' => '1/translations/committed.pdf', 'status' => 'pending']);
    }

    public function test_stale_candidate_is_not_reclaimed_before_the_grace_period(): void
    {
        $fresh = StorageCleanupOutbox::create([
            'backend' => 'supabase',
            'path' => '1/translations/fresh.pdf',
            'kind' => StorageCleanupService::KIND_CANDIDATE,
            'status' => StorageCleanupOutbox::STATUS_PENDING,
        ]);

        $storage = $this->storage($delete);
        $delete->never();

        $result = app(StorageCleanupService::class)->reclaimStalePublishCandidates(3600);

        $this->assertSame(0, $result['reclaimed']);
        $this->assertDatabaseHas('storage_cleanup_outbox', ['id' => $fresh->id, 'status' => 'pending']);
    }

    public function test_mark_candidates_committed_removes_candidate_rows(): void
    {
        StorageCleanupOutbox::create([
            'backend' => 'supabase',
            'path' => '1/translations/published.pdf',
            'kind' => StorageCleanupService::KIND_CANDIDATE,
            'status' => StorageCleanupOutbox::STATUS_PENDING,
        ]);

        app(StorageCleanupService::class)->markCandidatesCommitted([['supabase', '1/translations/published.pdf']]);

        $this->assertDatabaseMissing('storage_cleanup_outbox', ['path' => '1/translations/published.pdf']);
    }
}