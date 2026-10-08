<?php

namespace Tests\Unit;

use App\Models\TranslationJob;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class TranslationJobStateTransitionTest extends TestCase
{
    use RefreshDatabase;

    private function makeJob(array $overrides = []): TranslationJob
    {
        return TranslationJob::create(array_merge([
            'user_id'      => 1,
            'payload_hash' => hash('sha256', 'payload'),
            'original_name'=> 'input.pdf',
            'original_ext' => '.pdf',
            'source_lang'  => 'English',
            'target_lang'  => 'Cebuano',
            'pdf_column_mode' => 'auto',
            'mode'         => 'balanced',
            'file_size'    => 10,
            'status'       => TranslationJob::STATUS_PROCESSING,
        ], $overrides));
    }

    public function test_a_completed_row_is_never_clobbered_by_a_late_worker(): void
    {
        $job = $this->makeJob(['status' => TranslationJob::STATUS_COMPLETED]);

        $job->markCompleted('supabase', 'late/overwrite.pdf', 999);

        $job->refresh();
        $this->assertSame(TranslationJob::STATUS_COMPLETED, $job->status);
        $this->assertNotSame('late/overwrite.pdf', $job->storage_path);
    }

    public function test_terminal_failure_cannot_overwrite_a_completed_row(): void
    {
        $job = $this->makeJob(['status' => TranslationJob::STATUS_COMPLETED]);

        $job->markTerminallyFailed(new \RuntimeException('late failure'), true);

        $job->refresh();
        $this->assertSame(TranslationJob::STATUS_COMPLETED, $job->status);
        $this->assertNull($job->terminal_failed_at);
        $this->assertNull($job->recoverable);
    }

    public function test_mark_queued_requires_an_explicit_recovery_for_failed_rows(): void
    {
        $job = $this->makeJob(['status' => TranslationJob::STATUS_FAILED]);

        $this->assertFalse($job->markQueued());
        $job->refresh();
        $this->assertSame(TranslationJob::STATUS_FAILED, $job->status);

        $this->assertTrue($job->markQueued(recovered: true));
        $job->refresh();
        $this->assertSame(TranslationJob::STATUS_QUEUED, $job->status);
        $this->assertNull($job->terminal_failed_at);
    }

    public function test_completed_rows_cannot_be_revived_by_recovery_mark_queued(): void
    {
        $job = $this->makeJob(['status' => TranslationJob::STATUS_COMPLETED]);

        $this->assertFalse($job->markQueued(recovered: true));
        $job->refresh();
        $this->assertSame(TranslationJob::STATUS_COMPLETED, $job->status);
    }

    public function test_mark_processing_ignores_terminal_rows(): void
    {
        $job = $this->makeJob(['status' => TranslationJob::STATUS_FAILED]);

        $this->assertFalse($job->markProcessing());
        $job->refresh();
        $this->assertSame(0, (int) $job->attempts);
    }

    public function test_reconcile_fail_respects_monotonicity(): void
    {
        $completed = $this->makeJob(['status' => TranslationJob::STATUS_COMPLETED]);
        $this->assertFalse($completed->reconcileMarkFailed('stale'));
        $completed->refresh();
        $this->assertSame(TranslationJob::STATUS_COMPLETED, $completed->status);

        $processing = $this->makeJob(['status' => TranslationJob::STATUS_PROCESSING]);
        $this->assertTrue($processing->reconcileMarkFailed('stale'));
        $processing->refresh();
        $this->assertSame(TranslationJob::STATUS_FAILED, $processing->status);
        $this->assertNotNull($processing->terminal_failed_at);
    }

    public function test_reconcile_fail_records_recoverability_from_durable_original(): void
    {
        $withOriginal = $this->makeJob([
            'status'                  => TranslationJob::STATUS_PROCESSING,
            'original_storage_path'   => '1/originals/x.pdf',
            'original_storage_backend'=> 'supabase',
        ]);
        $withOriginal->reconcileMarkFailed('stale');
        $withOriginal->refresh();
        $this->assertTrue($withOriginal->recoverable);

        $withoutOriginal = $this->makeJob(['status' => TranslationJob::STATUS_PROCESSING]);
        $withoutOriginal->reconcileMarkFailed('stale');
        $withoutOriginal->refresh();
        $this->assertFalse($withoutOriginal->recoverable);
    }
}