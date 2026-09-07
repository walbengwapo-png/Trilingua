<?php

namespace App\Console\Commands;

use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use Illuminate\Console\Command;

class ReconcileTranslations extends Command
{
    protected $signature = 'translations:reconcile
                            {--fail : Actually mark stale in-flight jobs as failed (default: report only)}
                            {--processing-timeout=900 : Seconds a processing job may run without a heartbeat}
                            {--waiting-timeout=7200 : Seconds a created/queued job may wait before being flagged stale}';

    protected $description = 'Reconcile translation_jobs against translation_history: backfill terminal rows and flag stuck in-flight jobs.';

    public function handle(): int
    {
        $fail = (bool) $this->option('fail');
        $processingTimeout = (int) $this->option('processing-timeout');
        $waitingTimeout = (int) $this->option('waiting-timeout');

        $failedCount = 0;

        // Stuck processing jobs: running without a heartbeat for too long are
        // assumed dead (worker crash / lease expiry). Only flagged, not deleted,
        // so an admin can replay them.
        $staleProcessing = TranslationJob::where('status', TranslationJob::STATUS_PROCESSING)
            ->where(function ($q) use ($processingTimeout) {
                $q->whereNull('last_heartbeat_at')
                    ->where('started_at', '<', now()->subSeconds($processingTimeout))
                    ->orWhere('last_heartbeat_at', '<', now()->subSeconds($processingTimeout));
            })
            ->get();

        foreach ($staleProcessing as $job) {
            $this->warn("Processing job #{$job->id} (uuid {$job->uuid}) has no heartbeat for > {$processingTimeout}s.");
            if ($fail) {
                $job->error = 'Timed out awaiting worker heartbeat (reconciled by translations:reconcile).';
                $job->status = TranslationJob::STATUS_FAILED;
                $job->completed_at = now();
                $job->save();
                $this->info("  -> marked failed.");
                $failedCount++;
            }
        }

        // Never-started jobs: waiting longer than the wait window.
        $staleWaiting = TranslationJob::whereIn('status', [TranslationJob::STATUS_CREATED, TranslationJob::STATUS_QUEUED])
            ->where('created_at', '<', now()->subSeconds($waitingTimeout))
            ->get();

        foreach ($staleWaiting as $job) {
            $this->warn("Waiting job #{$job->id} (uuid {$job->uuid}) has not started for > {$waitingTimeout}s.");
            if ($fail) {
                $job->error = 'Stale: job never started (reconciled by translations:reconcile).';
                $job->status = TranslationJob::STATUS_FAILED;
                $job->completed_at = now();
                $job->save();
                $this->info("  -> marked failed.");
                $failedCount++;
            }
        }

        // Backfill: completed history rows that predate the state-machine
        // migration get terminal translation_jobs rows so the admin view has a
        // complete picture. Idempotent via the matching row on job_id.
        $backfilled = 0;
        $historyRows = TranslationHistory::where('status', 'completed')
            ->whereNotNull('job_id')
            ->where('translation_type', 'document')
            ->get();

        foreach ($historyRows as $history) {
            $exists = TranslationJob::where('uuid', $history->job_id)->exists();
            if ($exists) {
                continue;
            }

            TranslationJob::create([
                'uuid'                   => $history->job_id,
                'user_id'                => $history->user_id,
                'payload_hash'           => hash('sha256', 'legacy:' . $history->id),
                'original_name'          => $history->original_filename ?? 'document',
                'original_ext'           => '.' . strtolower((string) pathinfo((string) $history->original_filename, PATHINFO_EXTENSION)),
                'source_lang'            => $history->source_language ?? '',
                'target_lang'            => $history->target_language ?? '',
                'pdf_column_mode'        => 'auto',
                'mode'                   => 'balanced',
                'file_size'              => $history->file_size,
                'original_storage_path'  => $history->original_storage_path,
                'original_storage_backend' => $history->original_storage_backend ?: 'supabase',
                'storage_path'           => $history->storage_path,
                'storage_backend'        => $history->storage_backend ?: 'supabase',
                'translation_history_id' => $history->id,
                'status'                 => TranslationJob::STATUS_COMPLETED,
                'progress'               => 100,
                'last_heartbeat_at'      => $history->created_at,
                'completed_at'           => $history->created_at,
            ]);
            $backfilled++;
        }

        $this->info(sprintf(
            'Reconcile complete: %d stuck job(s) flagged, %d history row(s) backfilled.',
            $staleProcessing->count() + $staleWaiting->count(),
            $backfilled
        ));

        return self::SUCCESS;
    }
}