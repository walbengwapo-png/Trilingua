<?php

namespace Tests\Feature;

use App\Models\StorageCleanupOutbox;
use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Models\User;
use App\Services\StorageCleanupService;
use App\Services\StorageService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * Gate 1: a `translation_jobs` row is a live reference to storage objects that
 * NO history row points at.
 *
 * The job state row holds two objects a retry depends on:
 *  - `original_storage_path`    (resolveInputPath / Admin\JobController::retry)
 *  - `translated_storage_path` (durableTranslatedUpload reuses it, never re-uploads)
 *
 * Deleting either while the job is active or recoverable breaks the retry. These
 * tests pin the corrected predicate and pin that the worker's own refused
 * completion still releases the object IT created.
 */
class StorageCleanupJobReferenceTest extends TestCase
{
    use RefreshDatabase;

    private const ORIGINAL = '1/inputs/shared-source.pdf';
    private const TRANSLATED = '1/translations/shared-output.pdf';

    private function user(): User
    {
        return User::factory()->create();
    }

    private function makeJob(int $userId, array $overrides = []): TranslationJob
    {
        return TranslationJob::create(array_merge([
            'user_id'               => $userId,
            'payload_hash'          => hash('sha256', 'gate-1-'.uniqid('', true)),
            'original_name'         => 'contract.pdf',
            'original_ext'          => '.pdf',
            'source_lang'           => 'English',
            'target_lang'           => 'Cebuano',
            'mode'                  => 'balanced',
            'file_size'             => 1024,
            'original_storage_path' => self::ORIGINAL,
            'original_storage_backend' => StorageService::BACKEND_SUPABASE,
            'status'                => TranslationJob::STATUS_QUEUED,
        ], $overrides));
    }

    private function storage(?\Mockery\ExpectationInterface &$deleteCall = null): \Mockery\LegacyMockInterface
    {
        $mock = \Mockery::mock(StorageService::class);
        $deleteCall = $mock->shouldReceive('delete');
        $this->app->instance(StorageService::class, $mock);

        return $mock;
    }

    /**
     * @dataProvider liveJobStates
     */
    public function test_an_original_held_by_a_live_job_is_never_reclaimed(
        string $status,
        bool $recoverable
    ): void {
        $user = $this->user();
        $this->makeJob($user->id, [
            'status'      => $status,
            'recoverable' => $recoverable,
        ]);

        $this->storage($delete);
        $delete->never();

        $cleanup = app(StorageCleanupService::class);
        $this->assertTrue(
            $cleanup->hasLiveReference(StorageService::BACKEND_SUPABASE, self::ORIGINAL),
            "A {$status}/recoverable=".var_export($recoverable, true).' job must protect its original.'
        );

        // Scheduled pass: the intent must be cancelled, not executed.
        $cleanup->recordPending(StorageService::BACKEND_SUPABASE, self::ORIGINAL);
        $cleanup->processPending();

        $this->assertDatabaseHas('storage_cleanup_outbox', [
            'backend' => StorageService::BACKEND_SUPABASE,
            'path'    => self::ORIGINAL,
            'status'  => StorageCleanupOutbox::STATUS_DONE,
        ]);
    }

    /**
     * @dataProvider liveJobStates
     */
    public function test_a_translated_object_a_retry_would_reuse_is_never_reclaimed(
        string $status,
        bool $recoverable
    ): void {
        $user = $this->user();
        $this->makeJob($user->id, [
            'status'                     => $status,
            'recoverable'                => $recoverable,
            'translated_storage_path'    => self::TRANSLATED,
            'translated_storage_backend' => StorageService::BACKEND_SUPABASE,
        ]);

        $this->storage($delete);
        $delete->never();

        $cleanup = app(StorageCleanupService::class);
        $this->assertTrue(
            $cleanup->hasLiveReference(StorageService::BACKEND_SUPABASE, self::TRANSLATED),
            "A {$status}/recoverable=".var_export($recoverable, true).' job must protect its recorded output.'
        );

        $cleanup->recordPending(StorageService::BACKEND_SUPABASE, self::TRANSLATED);
        $cleanup->processPending();

        $this->assertDatabaseHas('storage_cleanup_outbox', [
            'backend' => StorageService::BACKEND_SUPABASE,
            'path'    => self::TRANSLATED,
            'status'  => StorageCleanupOutbox::STATUS_DONE,
        ]);
    }

    public static function liveJobStates(): array
    {
        return [
            'created'            => [TranslationJob::STATUS_CREATED, false],
            'queued'             => [TranslationJob::STATUS_QUEUED, false],
            'processing'         => [TranslationJob::STATUS_PROCESSING, false],
            'failed-recoverable' => [TranslationJob::STATUS_FAILED, true],
        ];
    }

    public function test_a_terminal_job_does_not_protect_its_objects(): void
    {
        $user = $this->user();
        $this->makeJob($user->id, [
            'status'                     => TranslationJob::STATUS_COMPLETED,
            'translated_storage_path'    => self::TRANSLATED,
            'translated_storage_backend' => StorageService::BACKEND_SUPABASE,
        ]);

        $this->storage($delete);
        $delete->once()->with(StorageService::BACKEND_SUPABASE, self::TRANSLATED);

        $cleanup = app(StorageCleanupService::class);
        $this->assertFalse(
            $cleanup->hasLiveReference(StorageService::BACKEND_SUPABASE, self::TRANSLATED),
            'A completed job owns nothing further; its objects belong to the history row.'
        );

        $cleanup->recordPending(StorageService::BACKEND_SUPABASE, self::TRANSLATED);
        $cleanup->processPending();
    }

    public function test_a_failed_but_unrecoverable_job_does_not_protect_its_objects(): void
    {
        $user = $this->user();
        $this->makeJob($user->id, [
            'status'      => TranslationJob::STATUS_FAILED,
            'recoverable' => false,
        ]);

        $this->storage($delete);
        $delete->once()->with(StorageService::BACKEND_SUPABASE, self::ORIGINAL);

        $cleanup = app(StorageCleanupService::class);
        $this->assertFalse($cleanup->hasLiveReference(StorageService::BACKEND_SUPABASE, self::ORIGINAL));

        $cleanup->recordPending(StorageService::BACKEND_SUPABASE, self::ORIGINAL);
        $cleanup->processPending();
    }

    public function test_a_genuine_orphan_is_still_reclaimed(): void
    {
        $this->storage($delete);
        $delete->once()->with(StorageService::BACKEND_SUPABASE, '1/translations/nobody.pdf');

        $cleanup = app(StorageCleanupService::class);
        $this->assertFalse($cleanup->hasLiveReference(StorageService::BACKEND_SUPABASE, '1/translations/nobody.pdf'));

        $cleanup->recordPending(StorageService::BACKEND_SUPABASE, '1/translations/nobody.pdf');
        $result = $cleanup->processPending();

        $this->assertSame(1, $result['processed']);
    }

    public function test_a_backend_mismatch_does_not_protect_the_object(): void
    {
        $user = $this->user();
        $this->makeJob($user->id, [
            'original_storage_backend' => StorageService::BACKEND_LOCAL,
        ]);

        $this->storage($delete);
        $delete->once()->with(StorageService::BACKEND_SUPABASE, self::ORIGINAL);

        $cleanup = app(StorageCleanupService::class);
        $this->assertFalse($cleanup->hasLiveReference(StorageService::BACKEND_SUPABASE, self::ORIGINAL));

        $cleanup->recordPending(StorageService::BACKEND_SUPABASE, self::ORIGINAL);
        $cleanup->processPending();
    }

    /**
     * The inverse guarantee: the worker's own state row must never vouch for the
     * object its refused completion is required to release. This is what
     * $excludeJobIds exists for - without it the corrected predicate would make
     * every refused completion leak its object permanently.
     */
    public function test_the_jobs_own_row_is_excluded_so_a_refused_attempt_can_still_release(): void
    {
        $user = $this->user();
        $job = $this->makeJob($user->id, [
            'status'                     => TranslationJob::STATUS_PROCESSING,
            'translated_storage_path'    => self::TRANSLATED,
            'translated_storage_backend' => StorageService::BACKEND_SUPABASE,
        ]);

        $this->storage($delete);
        $delete->never();

        $cleanup = app(StorageCleanupService::class);

        // From outside - the scheduled cleanup pass: the row protects the path,
        // because from outside this job may still be retried.
        $this->assertTrue($cleanup->hasLiveReference(StorageService::BACKEND_SUPABASE, self::TRANSLATED));

        $cleanup->recordPending(StorageService::BACKEND_SUPABASE, self::TRANSLATED);
        $cleanup->processPending();

        // From the job's own release path: it does not, so the object is reclaimed.
        $this->assertFalse(
            $cleanup->hasLiveReference(StorageService::BACKEND_SUPABASE, self::TRANSLATED, [], [$job->id]),
            'A job must be able to release the object it just uploaded.'
        );
    }

    public function test_another_jobs_reference_still_blocks_a_refused_release(): void
    {
        $user = $this->user();
        $other = $this->makeJob($user->id, [
            'translated_storage_path'    => self::TRANSLATED,
            'translated_storage_backend' => StorageService::BACKEND_SUPABASE,
        ]);
        $mine = $this->makeJob($user->id, [
            'translated_storage_path'    => self::TRANSLATED,
            'translated_storage_backend' => StorageService::BACKEND_SUPABASE,
        ]);

        $this->storage($delete);
        $delete->never();

        $cleanup = app(StorageCleanupService::class);
        $this->assertTrue(
            $cleanup->hasLiveReference(StorageService::BACKEND_SUPABASE, self::TRANSLATED, [], [$mine->id]),
            'Excluding my own row must not exclude a sibling job that still needs the object.'
        );
    }

    public function test_history_deletion_does_not_queue_an_intent_for_a_job_held_original(): void
    {
        $user = $this->user();
        $job = $this->makeJob($user->id, ['status' => TranslationJob::STATUS_QUEUED]);

        $record = TranslationHistory::create([
            'user_id'                => $user->id,
            'translation_type'       => 'document',
            'original_filename'      => 'contract.pdf',
            'translated_filename'    => 'contract_ceb.pdf',
            'source_language'        => 'English',
            'target_language'        => 'Cebuano',
            'storage_path'           => '1/translations/first.pdf',
            'storage_backend'        => StorageService::BACKEND_SUPABASE,
            'original_storage_path'  => self::ORIGINAL,
            'original_storage_backend' => StorageService::BACKEND_SUPABASE,
            'status'                 => 'completed',
            'review_status'          => 'pending',
            'job_id'                 => (string) $job->uuid,
        ]);

        $this->storage($delete);
        // Only the genuinely orphaned output is deleted. The original is held by
        // the live job, so cleanup must never call delete() for it.
        $delete->once()->with(StorageService::BACKEND_SUPABASE, '1/translations/first.pdf');

        $history = app(\App\Services\HistoryService::class);
        $history->deleteRecord((int) $record->id, (int) $user->id);

        // The translated output is genuinely orphaned and queued for removal...
        $this->assertDatabaseHas('storage_cleanup_outbox', [
            'path'   => '1/translations/first.pdf',
            'status' => StorageCleanupOutbox::STATUS_PENDING,
        ]);

        // ...but the ORIGINAL is still held by the live job, so no intent exists
        // for it. This is the exact data loss Gate 1 closed.
        $this->assertDatabaseMissing('storage_cleanup_outbox', [
            'path' => self::ORIGINAL,
        ]);

        // Immediate pass, as HistoryController::destroy performs it.
        app(StorageCleanupService::class)->processPending();
    }

    public function test_scheduled_cleanup_leaves_a_job_held_original_untouched(): void
    {
        $user = $this->user();
        $this->makeJob($user->id, ['status' => TranslationJob::STATUS_PROCESSING]);

        $this->storage($delete);
        $delete->never();

        // Simulate a pre-existing orphan intent for the job-held original.
        StorageCleanupOutbox::create([
            'backend'     => StorageService::BACKEND_SUPABASE,
            'path'        => self::ORIGINAL,
            'kind'        => StorageCleanupService::KIND_ORPHAN,
            'status'      => StorageCleanupOutbox::STATUS_PENDING,
            'attempts'    => 0,
        ]);

        $result = app(StorageCleanupService::class)->processPending();

        $this->assertSame(1, $result['processed']);
        $this->assertDatabaseHas('storage_cleanup_outbox', [
            'path'       => self::ORIGINAL,
            'status'     => StorageCleanupOutbox::STATUS_DONE,
            'last_error' => 'skipped: path has a live reference',
        ]);
    }
}
