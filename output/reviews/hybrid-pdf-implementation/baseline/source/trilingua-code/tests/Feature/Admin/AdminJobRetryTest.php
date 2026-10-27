<?php

namespace Tests\Feature\Admin;

use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationJob;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Queue;
use Illuminate\Support\Str;
use Tests\TestCase;

/**
 * The admin Retry flow must never replay the serialized failed_jobs payload.
 * It reconstructs the worker input from the durable original at handle() time,
 * keyed purely on the shared uuid, and never offers Retry for a job without a
 * durable original.
 */
class AdminJobRetryTest extends TestCase
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

    private function makeFailures(string $uuid, bool $recoverable, bool $withState = true): int
    {
        if ($withState) {
            TranslationJob::create([
                'uuid'                    => $uuid,
                'user_id'                 => 3,
                'payload_hash'            => hash('sha256', 'payload'),
                'original_name'           => 'input.pdf',
                'original_ext'            => '.pdf',
                'source_lang'             => 'English',
                'target_lang'             => 'Cebuano',
                'pdf_column_mode'         => 'auto',
                'mode'                    => 'balanced',
                'file_size'               => 10,
                'status'                  => TranslationJob::STATUS_FAILED,
                'recoverable'             => $recoverable,
                'original_storage_path'   => $recoverable ? '3/originals/x.pdf' : null,
                'original_storage_backend'=> $recoverable ? 'supabase' : null,
                'error'                   => 'original failure',
                'terminal_failed_at'      => now()->subMinutes(5),
            ]);
        }

        return DB::table('failed_jobs')->insertGetId([
            'uuid'       => $uuid,
            'connection' => 'database',
            'queue'      => 'default',
            'payload'    => json_encode(['displayName' => 'App\\Jobs\\TranslateDocumentJob']),
            'exception'  => 'original failure: input file not found',
            'failed_at'  => now(),
        ]);
    }

    public function test_admin_replays_a_recoverable_failed_job_from_its_durable_original(): void
    {
        Queue::fake();
        $uuid = (string) Str::uuid();
        $failedJobId = $this->makeFailures($uuid, true);

        $response = $this->actingAs($this->makeAdmin())
            ->post(route('admin.jobs.retry', $failedJobId));

        $response->assertRedirect(route('admin.jobs.index'));
        $this->assertEquals('queue-job-retried', session('status'));

        Queue::assertPushed(TranslateDocumentJob::class, function (TranslateDocumentJob $job) use ($uuid) {
            return $job->uuid() === $uuid
                && $job->presetUuid === $uuid
                && $job->originalStoragePath === '3/originals/x.pdf'
                && $job->originalStorageBackend === 'supabase'
                && $job->translationJobId !== null;
        });

        $this->assertSame(0, DB::table('failed_jobs')->where('id', $failedJobId)->count(), 'A successful replay must clear the historical failure entry.');

        $state = TranslationJob::where('uuid', $uuid)->first();
        $this->assertSame(TranslationJob::STATUS_QUEUED, $state->status);
        $this->assertNull($state->terminal_failed_at);
    }

    public function test_unrecoverable_failed_job_is_not_replayed(): void
    {
        Queue::fake();
        $uuid = (string) Str::uuid();
        $failedJobId = $this->makeFailures($uuid, false);

        $this->actingAs($this->makeAdmin())
            ->post(route('admin.jobs.retry', $failedJobId))
            ->assertRedirect(route('admin.jobs.index'));

        $this->assertEquals('queue-job-not-recoverable', session('status'));
        Queue::assertNothingPushed();
        $this->assertSame(1, DB::table('failed_jobs')->where('id', $failedJobId)->count());

        $state = TranslationJob::where('uuid', $uuid)->first();
        $this->assertSame(TranslationJob::STATUS_FAILED, $state->status);
    }

    public function test_failed_job_without_a_matching_state_row_is_not_replayed(): void
    {
        Queue::fake();
        $uuid = (string) Str::uuid();
        $failedJobId = $this->makeFailures($uuid, true, withState: false);

        $this->actingAs($this->makeAdmin())
            ->post(route('admin.jobs.retry', $failedJobId))
            ->assertRedirect(route('admin.jobs.index'));

        $this->assertEquals('queue-job-not-recoverable', session('status'));
        Queue::assertNothingPushed();
        $this->assertSame(1, DB::table('failed_jobs')->where('id', $failedJobId)->count());
    }

    public function test_non_admin_cannot_trigger_a_retry(): void
    {
        Queue::fake();
        $uuid = (string) Str::uuid();
        $failedJobId = $this->makeFailures($uuid, true);

        $this->actingAs($this->makeUser())
            ->post(route('admin.jobs.retry', $failedJobId))
            ->assertForbidden();

        Queue::assertNothingPushed();
        $this->assertSame(1, DB::table('failed_jobs')->where('id', $failedJobId)->count());
    }

    public function test_jobs_index_flags_recoverability_for_the_retry_control(): void
    {
        $recoverableUuid = (string) Str::uuid();
        $unrecoverableUuid = (string) Str::uuid();
        $this->makeFailures($recoverableUuid, true);
        $this->makeFailures($unrecoverableUuid, false);

        $response = $this->actingAs($this->makeAdmin())
            ->get(route('admin.jobs.index'))
            ->assertOk();

        $content = $response->getContent();

        // The controller enriches failed_jobs rows in-memory; both badges render.
        $this->assertStringContainsString('Recoverable', $content);
        $this->assertStringContainsString('Unavailable', $content);
    }
}