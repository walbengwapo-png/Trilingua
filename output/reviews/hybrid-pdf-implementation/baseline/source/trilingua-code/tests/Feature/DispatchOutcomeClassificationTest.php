<?php

namespace Tests\Feature;

use App\Models\TranslationJob;
use App\Models\TranslationQuota;
use App\Models\User;
use App\Services\DispatchOutcome;
use App\Services\DispatchOutcomeClassifier;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Queue;
use Mockery;
use Tests\TestCase;

/**
 * F2: a failed intake dispatch must be resolved by evidence, not by assumption.
 *
 * The defect being pinned here: intake previously treated "dispatch threw" as
 * "the job never entered the queue", and on that assumption it deleted the
 * input and refunded the quota. Both are unrecoverable if a worker had in fact
 * received the job. These tests cover the three-outcome contract (ACCEPTED /
 * REJECTED / UNKNOWN), and the transaction mechanism the contract depends on.
 */
class DispatchOutcomeClassificationTest extends TestCase
{
    use RefreshDatabase;

    protected function tearDown(): void
    {
        Mockery::close();
        parent::tearDown();
    }

    private function subdirs(string $path): array
    {
        if (! is_dir($path)) {
            return [];
        }

        return array_values(array_diff(scandir($path) ?: [], ['.', '..']));
    }

    private function docUpload(): UploadedFile
    {
        return UploadedFile::fake()->createWithContent('q.docx', 'PK' . str_repeat('A', 256));
    }

    private function useDatabaseQueue(): void
    {
        config([
            'queue.default' => 'database',
            'queue.connections.database.driver' => 'database',
            'queue.connections.database.table' => 'jobs',
            'queue.connections.database.queue' => 'default',
            'queue.connections.database.after_commit' => false,
        ]);
    }

    private function quotaFor(User $user): ?TranslationQuota
    {
        return TranslationQuota::where('user_id', $user->id)
            ->where('quota_day', today()->toDateString())
            ->first();
    }

    // ---------------------------------------------------------------------
    // The mechanism: a queue insert joins the caller's transaction, so a
    // rollback cannot leave a receivable job behind.
    // ---------------------------------------------------------------------

    public function test_queue_insert_inside_a_transaction_rolls_back_with_it(): void
    {
        $this->useDatabaseQueue();

        $job = new \App\Jobs\TranslateDocumentJob(
            'q.docx', '.docx', 10, 'English', 'Cebuano', 'auto', '', 1, null, 'balanced',
        );

        DB::beginTransaction();
        Queue::connection('database')->push($job);
        $this->assertSame(1, DB::table('jobs')->count(), 'the insert is visible inside the transaction');
        DB::rollBack();

        $this->assertSame(0, DB::table('jobs')->count(), 'a rolled-back acceptance must leave no receivable job');
    }

    public function test_validation_fails_when_the_queue_connection_differs_from_the_state_connection(): void
    {
        // A separate connection means the jobs INSERT cannot join the
        // translation_jobs transaction, so acceptance is not atomic. The
        // deployment must be refused rather than silently degraded.
        $this->useDatabaseQueue();
        config(['queue.connections.database.connection' => 'some_other_connection']);

        $this->artisan('deployment:validate-timeouts')
            ->assertFailed();
    }

    public function test_validation_fails_when_after_commit_is_enabled(): void
    {
        $this->useDatabaseQueue();
        config(['queue.connections.database.after_commit' => true]);

        $this->artisan('deployment:validate-timeouts')
            ->assertFailed();
    }

    public function test_validation_passes_on_the_audited_configuration(): void
    {
        $this->useDatabaseQueue();

        $this->artisan('deployment:validate-timeouts')
            ->assertSuccessful();
    }

    // ---------------------------------------------------------------------
    // Controller behaviour per outcome
    // ---------------------------------------------------------------------

    public function test_rejected_dispatch_refunds_the_quota_and_removes_the_input(): void
    {
        config([
            'translation.upload.max_daily_files' => 25,
            'translation.upload.max_daily_bytes' => 262144000,
        ]);

        $user = User::factory()->create();

        // Dispatch fails outright: the enqueue call is reached and throws
        // before anything is written to the queue.
        $broker = Mockery::mock(\Illuminate\Contracts\Bus\Dispatcher::class);
        $broker->shouldReceive('dispatch')->andThrow(new \RuntimeException('queue unavailable'));
        $this->app->instance(\Illuminate\Contracts\Bus\Dispatcher::class, $broker);

        $response = $this->actingAs($user)->post('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => $this->docUpload(),
        ], ['Accept' => 'application/json']);

        $response->assertStatus(500);

        $this->assertSame(0, TranslationJob::count(), 'a rejected dispatch leaves no job row');
        $this->assertSame(0, DB::table('jobs')->count(), 'a rejected dispatch leaves no queue row');

        $row = $this->quotaFor($user);
        $this->assertNotNull($row);
        $this->assertSame(0, (int) $row->files, 'a provably rejected submission is refunded');
        $this->assertSame(0, (int) $row->bytes);
    }

    public function test_unresolved_dispatch_keeps_the_quota_and_the_input_and_returns_the_reference(): void
    {
        config([
            'translation.upload.max_daily_files' => 25,
            'translation.upload.max_daily_bytes' => 262144000,
        ]);

        $user = User::factory()->create();
        $before = $this->subdirs(storage_path('app/uploads'));

        // Simulate a genuinely unresolvable read-back: the enqueue was
        // attempted, but the outcome cannot be observed.
        $classifier = Mockery::mock(DispatchOutcomeClassifier::class);
        $classifier->shouldReceive('classify')->andReturn(new DispatchOutcome(
            DispatchOutcome::UNKNOWN,
            'simulated unreadable read-back',
            false,
        ));
        $this->app->instance(DispatchOutcomeClassifier::class, $classifier);

        $broker = Mockery::mock(\Illuminate\Contracts\Bus\Dispatcher::class);
        $broker->shouldReceive('dispatch')->andThrow(new \RuntimeException('connection lost during commit'));
        $this->app->instance(\Illuminate\Contracts\Bus\Dispatcher::class, $broker);

        $response = $this->actingAs($user)->post('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => $this->docUpload(),
        ], ['Accept' => 'application/json']);

        $response->assertStatus(503);
        $response->assertJsonPath('status', 'unavailable');
        $response->assertJsonPath('dispatch', DispatchOutcome::UNKNOWN);
        $this->assertNotNull($response->json('job_id'), 'the user needs a stable reference to check back on');

        $row = $this->quotaFor($user);
        $this->assertNotNull($row);
        $this->assertSame(1, (int) $row->files, 'an unresolved dispatch must NOT refund - a worker may hold the job');
        $this->assertGreaterThan(0, (int) $row->bytes);

        $this->assertNotSame(
            $before,
            $this->subdirs(storage_path('app/uploads')),
            'an unresolved dispatch must KEEP the input, because a worker may be reading it'
        );
    }

    // ---------------------------------------------------------------------
    // Classifier contract
    // ---------------------------------------------------------------------

    public function test_failure_before_the_enqueue_call_is_rejected_without_consulting_the_queue(): void
    {
        $outcome = app(DispatchOutcomeClassifier::class)->classify(
            null, '', TranslationJob::STATUS_CREATED, dispatchAttempted: false,
        );

        $this->assertTrue($outcome->isRejected());
        $this->assertTrue($outcome->safeToCompensate);
    }

    public function test_enqueue_attempted_without_a_reference_is_unresolved_not_rejected(): void
    {
        $outcome = app(DispatchOutcomeClassifier::class)->classify(
            null, '', TranslationJob::STATUS_CREATED, dispatchAttempted: true,
        );

        $this->assertTrue($outcome->isUnknown());
        $this->assertFalse($outcome->safeToCompensate);
    }

    public function test_a_rolled_back_state_row_is_rejected_and_compensable(): void
    {
        $user = User::factory()->create();
        $row = TranslationJob::create([
            'user_id' => $user->id,
            'payload_hash' => hash('sha256', 'x'),
            'original_name' => 'q.docx',
            'original_ext' => '.docx',
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'pdf_column_mode' => 'auto',
            'mode' => 'balanced',
            'file_size' => 10,
            'status' => TranslationJob::STATUS_CREATED,
        ]);

        $outcome = app(DispatchOutcomeClassifier::class)->classify($row, 'abc-123', TranslationJob::STATUS_CREATED);

        $this->assertTrue($outcome->isRejected());
        $this->assertTrue($outcome->safeToCompensate);
    }

    public function test_a_waiting_queue_row_proves_acceptance(): void
    {
        $this->useDatabaseQueue();

        $user = User::factory()->create();
        $row = TranslationJob::create([
            'user_id' => $user->id,
            'payload_hash' => hash('sha256', 'y'),
            'original_name' => 'q.docx',
            'original_ext' => '.docx',
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'pdf_column_mode' => 'auto',
            'mode' => 'balanced',
            'file_size' => 10,
            'status' => TranslationJob::STATUS_QUEUED,
        ]);

        $uuid = (string) \Illuminate\Support\Str::uuid();
        $row->uuid = $uuid;
        $row->save();

        $job = new \App\Jobs\TranslateDocumentJob(
            'q.docx', '.docx', 10, 'English', 'Cebuano', 'auto', '', (int) $user->id, null, 'balanced',
            null, 'supabase', (int) $row->id, $uuid,
        );
        Queue::connection('database')->push($job);

        $outcome = app(DispatchOutcomeClassifier::class)->classify($row->fresh(), $uuid, TranslationJob::STATUS_CREATED);

        $this->assertTrue($outcome->isAccepted());
        $this->assertFalse($outcome->safeToCompensate, 'accepted work must never be compensated');
    }

    public function test_a_failed_jobs_record_proves_a_worker_received_it_and_blocks_compensation(): void
    {
        $user = User::factory()->create();
        $uuid = (string) \Illuminate\Support\Str::uuid();

        $row = TranslationJob::create([
            'user_id' => $user->id,
            'payload_hash' => hash('sha256', 'z'),
            'original_name' => 'q.docx',
            'original_ext' => '.docx',
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'pdf_column_mode' => 'auto',
            'mode' => 'balanced',
            'file_size' => 10,
            'status' => TranslationJob::STATUS_FAILED,
            'uuid' => $uuid,
        ]);

        DB::table('failed_jobs')->insert([
            'uuid' => $uuid,
            'connection' => 'database',
            'queue' => 'default',
            'payload' => '{"uuid":"'.$uuid.'"}',
            'exception' => 'worker exhausted retries',
            'failed_at' => now(),
        ]);

        $outcome = app(DispatchOutcomeClassifier::class)->classify($row->fresh(), $uuid, TranslationJob::STATUS_CREATED);

        $this->assertTrue(
            $outcome->isAccepted(),
            'a worker received this job, so the failure path owns the outcome - intake must not compensate'
        );
        $this->assertFalse($outcome->safeToCompensate);
    }

    public function test_a_pre_existing_failure_record_is_excluded_when_classifying_an_admin_replay(): void
    {
        $user = User::factory()->create();
        $uuid = (string) \Illuminate\Support\Str::uuid();

        $row = TranslationJob::create([
            'user_id' => $user->id,
            'payload_hash' => hash('sha256', 'w'),
            'original_name' => 'q.docx',
            'original_ext' => '.docx',
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'pdf_column_mode' => 'auto',
            'mode' => 'balanced',
            'file_size' => 10,
            'status' => TranslationJob::STATUS_FAILED,
            'uuid' => $uuid,
        ]);

        $id = DB::table('failed_jobs')->insertGetId([
            'uuid' => $uuid,
            'connection' => 'database',
            'queue' => 'default',
            'payload' => '{"uuid":"'.$uuid.'"}',
            'exception' => 'worker exhausted retries',
            'failed_at' => now(),
        ]);

        $prior = (string) $row->status;

        // With the prior record visible, the replay looks accepted - which is
        // exactly the misreading that would make a failed replay look like a
        // successful one.
        $naive = app(DispatchOutcomeClassifier::class)->classify($row->fresh(), $uuid, $prior);
        $this->assertTrue($naive->isAccepted());

        // Excluding the record that predates this dispatch gives the truth: the
        // failed -> queued write rolled back and nothing was enqueued.
        $truthful = app(DispatchOutcomeClassifier::class)->classify(
            $row->fresh(), $uuid, $prior, (int) $id,
        );

        $this->assertTrue($truthful->isRejected());
        $this->assertTrue($truthful->safeToCompensate);
    }

    public function test_read_back_failure_is_unresolved(): void
    {
        $user = User::factory()->create();
        $uuid = (string) \Illuminate\Support\Str::uuid();

        $row = TranslationJob::create([
            'user_id' => $user->id,
            'payload_hash' => hash('sha256', 'v'),
            'original_name' => 'q.docx',
            'original_ext' => '.docx',
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'pdf_column_mode' => 'auto',
            'mode' => 'balanced',
            'file_size' => 10,
            'status' => TranslationJob::STATUS_CREATED,
            'uuid' => $uuid,
        ]);

        $classifier = Mockery::mock(DispatchOutcomeClassifier::class)->makePartial();
        $classifier->shouldReceive('queueRow')->andThrow(new \RuntimeException('read-back unavailable'));
        $classifier->shouldReceive('hasFailedJobEvidence')->andThrow(new \RuntimeException('read-back unavailable'));

        $outcome = $classifier->classify($row->fresh(), $uuid, TranslationJob::STATUS_CREATED);

        $this->assertTrue($outcome->isUnknown());
        $this->assertFalse($outcome->safeToCompensate);
    }

    protected function setUp(): void
    {
        parent::setUp();
        Cache::flush();
    }
}
