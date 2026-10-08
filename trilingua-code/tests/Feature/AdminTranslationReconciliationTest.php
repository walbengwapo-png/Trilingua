<?php

namespace Tests\Feature;

use App\Models\TranslationJob;
use App\Models\TranslationHistory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;
use Tests\TestCase;

/**
 * The scheduled reconciler must never fail a job that still holds a fresh
 * queue lease (a slow but healthy Python call), and must fail one whose lease
 * lapsed and whose heartbeat is stale.
 */
class AdminTranslationReconciliationTest extends TestCase
{
    use RefreshDatabase;

    private function makeStaleProcessingJob(string $uuid): TranslationJob
    {
        return TranslationJob::create([
            'uuid'              => $uuid,
            'user_id'           => 7,
            'payload_hash'      => hash('sha256', 'payload'),
            'original_name'     => 'input.pdf',
            'original_ext'      => '.pdf',
            'source_lang'       => 'English',
            'target_lang'       => 'Cebuano',
            'pdf_column_mode'   => 'auto',
            'mode'              => 'balanced',
            'file_size'         => 10,
            'status'            => TranslationJob::STATUS_PROCESSING,
            'started_at'        => now()->subSeconds(4000),
            'last_heartbeat_at' => now()->subSeconds(4000),
        ]);
    }

    private function makeStaleWaitingJob(string $uuid): TranslationJob
    {
        $job = $this->makeStaleProcessingJob($uuid);
        $job->status = TranslationJob::STATUS_QUEUED;
        $job->started_at = null;
        $job->last_heartbeat_at = null;
        $job->created_at = now()->subSeconds(8000);
        $job->save();

        return $job;
    }

    private function insertQueueRow(string $uuid, ?int $reservedAt): void
    {
        DB::table('jobs')->insert([
            'queue'        => 'default',
            'payload'      => json_encode([
                'uuid'        => $uuid,
                'displayName' => TranslateDocumentJobPayload::NAME,
                'job'         => 'Illuminate\\Queue\\CallQueuedHandler',
                'data'        => ['commandName' => 'App\\Jobs\\TranslateDocumentJob', 'command' => 'O:0:"stdClass":0:{}'],
            ]),
            'attempts'     => 1,
            'reserved_at'  => $reservedAt,
            'available_at' => time(),
            'created_at'   => time() - 100,
        ]);
    }

    public function test_fresh_queue_reservation_keeps_a_slow_but_alive_job_processing(): void
    {
        $uuid = (string) Str::uuid();
        $this->makeStaleProcessingJob($uuid);
        $this->insertQueueRow($uuid, time());

        Artisan::call('translations:reconcile', ['--fail' => true]);

        $job = TranslationJob::where('uuid', $uuid)->first();
        $this->assertSame(TranslationJob::STATUS_PROCESSING, $job->status);
    }

    public function test_lapsed_reservation_and_stale_heartbeat_marks_the_job_failed(): void
    {
        $uuid = (string) Str::uuid();
        $this->makeStaleProcessingJob($uuid);
        $this->insertQueueRow($uuid, time() - 4000);

        Artisan::call('translations:reconcile', ['--fail' => true]);

        $job = TranslationJob::where('uuid', $uuid)->first();
        $this->assertSame(TranslationJob::STATUS_FAILED, $job->status);
        $this->assertNotNull($job->terminal_failed_at);
    }

    public function test_no_queue_row_means_no_live_worker_evidence(): void
    {
        $uuid = (string) Str::uuid();
        $this->makeStaleProcessingJob($uuid);

        Artisan::call('translations:reconcile', ['--fail' => true]);

        $job = TranslationJob::where('uuid', $uuid)->first();
        $this->assertSame(TranslationJob::STATUS_FAILED, $job->status);
        $this->assertStringContainsString('heartbeat', (string) $job->error);
    }

    public function test_stale_waiting_job_with_a_fresh_worker_reservation_is_not_failed(): void
    {
        $uuid = (string) Str::uuid();
        $this->makeStaleWaitingJob($uuid);
        $this->insertQueueRow($uuid, time());

        Artisan::call('translations:reconcile', ['--fail' => true]);

        $this->assertSame(TranslationJob::STATUS_QUEUED, TranslationJob::where('uuid', $uuid)->value('status'));
    }

    public function test_stale_waiting_job_without_a_live_worker_is_failed(): void
    {
        $uuid = (string) Str::uuid();
        $this->makeStaleWaitingJob($uuid);

        Artisan::call('translations:reconcile', ['--fail' => true]);

        $this->assertSame(TranslationJob::STATUS_FAILED, TranslationJob::where('uuid', $uuid)->value('status'));
    }

    public function test_legacy_completed_history_is_backfilled_once_with_its_owner_and_file_paths(): void
    {
        $user = User::factory()->create();
        $uuid = (string) Str::uuid();
        $history = TranslationHistory::create([
            'user_id' => $user->id,
            'job_id' => $uuid,
            'translation_type' => 'document',
            'status' => 'completed',
            'original_filename' => 'source.docx',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'original_storage_path' => 'originals/source.docx',
            'original_storage_backend' => 'supabase',
            'storage_path' => 'translations/output.docx',
            'storage_backend' => 'supabase',
        ]);

        Artisan::call('translations:reconcile');
        Artisan::call('translations:reconcile');

        $this->assertSame(1, TranslationJob::where('uuid', $uuid)->count());
        $job = TranslationJob::where('uuid', $uuid)->firstOrFail();
        $this->assertSame($user->id, $job->user_id);
        $this->assertSame($history->id, $job->translation_history_id);
        $this->assertSame('originals/source.docx', $job->original_storage_path);
        $this->assertSame('translations/output.docx', $job->storage_path);
        $this->assertSame(TranslationJob::STATUS_COMPLETED, $job->status);
    }
}

class TranslateDocumentJobPayload
{
    public const NAME = 'App\\Jobs\\TranslateDocumentJob';
}
