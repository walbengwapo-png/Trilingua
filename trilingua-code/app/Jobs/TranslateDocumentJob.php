<?php

namespace App\Jobs;

use App\Exceptions\TranslationException;
use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Models\User;
use App\Notifications\TranslationCompleted;
use App\Notifications\TranslationFailed;
use App\Services\BlockService;
use App\Services\HistoryService;
use App\Services\MetricsService;
use App\Services\StorageService;
use App\Services\StorageCleanupService;
use App\Services\Translation\TranslationManager;
use App\Support\AdminNotifier;
use App\Support\ReviewStatus;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Http\UploadedFile;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class TranslateDocumentJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    /**
     * Maximum attempts per job. Queued jobs that keep faulting before upload
     * will retry with exponential backoff, then land in the failed_jobs table
     * where an admin can inspect and replay them.
     */
    public int $tries = 3;

    /**
     * Backoff (seconds) per eventual attempt: 30s then 120s.
     */
    public array $backoff = [30, 120];

    /**
     * Payload upper bound for one attempt, sourced from the timeout ladder in
     * config/timeouts.php (default 1300). Must stay below the worker window.
     */
    public int $timeout = 1300;

    /**
     * The UUID for this job; surfaced as job_id to the frontend and used as the
     * shared key between translation_jobs and translation_history.job_id.
     */
    private ?string $jobUuid = null;

    /**
     * Create a new job instance.
     *
     * @param  int|null  $translationJobId  Primary key of the translation_jobs
     *                                      row created by the controller. Always
     *                                      set for jobs produced by the app.
     */
    public function __construct(
        public string $originalName,
        public string $originalExt,
        public int $fileSize,
        public string $sourceLang,
        public string $targetLang,
        public string $pdfColumnMode = 'auto',
        public string $tempPath,
        public int $userId,
        public ?string $originalStoragePath = null,
        public string $mode = 'balanced',
        public ?int $parentDocumentId = null,
        public ?string $originalStorageBackend = 'supabase',
        public ?int $translationJobId = null,
        public ?string $presetUuid = null,
    ) {
        $this->timeout = (int) config('timeouts.job', 1300);
    }

    /**
     * Get the UUID for this job instance. A preset UUID (used when an operator
     * replays a failed job) wins so polling, dedup and history stay coherent.
     */
    public function uuid(): string
    {
        if ($this->presetUuid !== null && $this->presetUuid !== '') {
            return $this->presetUuid;
        }
        if ($this->jobUuid === null) {
            $this->jobUuid = (string) Str::uuid();
        }
        return $this->jobUuid;
    }

    /**
     * Execute the job. The translation_jobs row is the durable state machine;
     * the cache entry is only a fast path for the polling endpoint.
     */
    public function handle(
        TranslationManager $translationManager,
        StorageService $storageService,
        HistoryService $historyService,
        BlockService $blockService,
        MetricsService $metricsService
    ): void {
        @set_time_limit(0);

        $job = $this->resolveJob();
        if ($job !== null && ! $job->markProcessing()) {
            return;
        }
        $outputPath = null;

        $this->storeProgress(10, 'Document queued for translation. Processing will begin shortly.');

        try {
            // Ensure a worker-local input exists. A replayed job's original
            // scratch file was cleaned at terminal failure, so reconstruct it
            // from the durable original when present. A job with NO durable
            // original is unrecoverable and must fail honestly.
            $job?->noteProgress(5);
            $this->resolveInputPath($storageService, $job);

            // Ensure the ORIGINAL file is stored durably (used by re-translation
            // and the review workspace). If the initial upload failed but the
            // durable fallback exists, backfill it now from the worker's copy.
            if ($this->originalStoragePath === null) {
                $this->backfillOriginalStorage($storageService, $job);
            }

            $uploadedFile = new UploadedFile(
                $this->tempPath,
                $this->originalName,
                null,
                null,
                true
            );

            $job?->noteProgress(15);
            $this->storeProgress(15, 'Translating document...');

            // 1. Translate the document via TranslationManager
            $arguments = [$uploadedFile, $this->sourceLang, $this->targetLang, $this->pdfColumnMode, $this->mode];
            if (config('translation.python_service.document_jobs')) {
                if ($job !== null && empty($job->engine_job_uuid)) {
                    TranslationJob::whereKey($job->getKey())->whereNull('engine_job_uuid')
                        ->update(['engine_job_uuid' => (string) Str::uuid()]);
                    $job->refresh();
                }
                $arguments[] = $job?->engine_job_uuid ?? $this->uuid();
                $arguments[] = fn () => $job?->noteProgress(15);
            }
            $translationResult = $translationManager->translateDocument(...$arguments);

            $downloadFilename = $translationResult['download_filename'];

            $job?->noteProgress(70);
            $this->storeProgress(70, 'Saving translated file...');

            // 2. Write the translated file to worker-local scratch.
            $outputPath = storage_path('app/temp/' . Str::uuid() . '_' . $downloadFilename);
            if (!is_dir(dirname($outputPath))) {
                mkdir(dirname($outputPath), 0755, true);
            }
            file_put_contents($outputPath, $translationResult['body']);

            if (!file_exists($outputPath) || !is_readable($outputPath)) {
                throw new \RuntimeException('Translation output file not found at: ' . $outputPath);
            }

            $outputSize = @filesize($outputPath);
            if ($outputSize === false || $outputSize <= 0) {
                throw new \RuntimeException('Translation output file was empty or unreadable: ' . $outputPath);
            }

            // 3. Store the translated file durably (primary with retries, then
            //    the encrypted persistent fallback backend). There is NO inline
            //    base64 fallback: output is never parked on the worker alone.
            //    A retried job after a partial failure reuses the object it
            //    already recorded instead of creating a duplicate.
            $translatedStoragePath = $this->userId . '/translations/' . (string) Str::uuid() . $this->normalizedOutputExt($downloadFilename);

            $job?->noteProgress(80);
            $this->storeProgress(80, 'Uploading translated file...');

            $upload = $this->durableTranslatedUpload($storageService, $job, $outputPath, $translatedStoragePath);

            // Object storage cannot join the DB transaction below, so the
            // durable paths are recorded on the state row NOW — a later retry
            // reuses them (idempotence) and a cleanup job could remove a
            // stranded object if the history write can never complete.
            if ($job !== null) {
                TranslationJob::whereKey($job->getKey())->update([
                    'translated_storage_path'    => $upload['storage_path'],
                    'translated_storage_backend' => $upload['backend'],
                    'last_heartbeat_at'          => now(),
                ]);
            }

            $job?->noteProgress(95);

            // 4. Record the translation in history (source of truth for the UI).
            //    The history row + review blocks are REQUIRED before the job may
            //    be completed. A block-persistence failure removes the freshly
            //    inserted row (compensating write, already in the job's DB
            //    transaction on Postgres via BlockService) and fails terminally
            //    instead of reporting a completed state the user could never
            //    review. Metrics stay non-fatal (documented boundary).
            $existingHistory = TranslationHistory::where('job_id', $this->uuid())
                ->where('user_id', $this->userId)
                ->orderByDesc('id')
                ->first();

            if ($existingHistory !== null) {
                // Idempotent resume: a prior partial attempt already linked
                // this job to a history row; never create a second one. The row
                // is NOT this attempt's, so it is never this attempt's to
                // compensate away.
                $history = $existingHistory;
                $historyCreatedThisAttempt = false;
            } else {
                $historyCreatedThisAttempt = true;
                $history = $historyService->insertRecord([
                    'user_id'                  => $this->userId,
                    'original_filename'        => $this->originalName,
                    'translated_filename'      => $downloadFilename,
                    'source_language'          => $this->sourceLang,
                    'target_language'          => $this->targetLang,
                    'created_at'               => now()->toIso8601String(),
                    'storage_path'             => $upload['storage_path'],
                    'storage_backend'          => $upload['backend'],
                    'original_storage_path'    => $this->originalStoragePath,
                    'original_storage_backend' => $this->originalStorageBackend,
                    'parent_document_id'       => $this->parentDocumentId,
                    'file_size'                => $this->fileSize,
                    'status'                   => 'completed',
                    'review_status'            => ReviewStatus::PENDING,
                    'signed_url_expires_at'    => $upload['signed_url_expires_at'],
                    'job_id'                   => $this->uuid(),
                ]);

                if ($history === null) {
                    throw new \RuntimeException('The translation history record could not be created.');
                }

                try {
                    // Persist required review blocks/sidecar (throws on failure).
                    $this->persistRequiredBlocks($blockService, $history, $translationResult);
                } catch (\Throwable $e) {
                    // Compensate so a row never claims "completed with review
                    // data" while listing nothing. Lasts until the durable
                    // cleanup job drops the stranded translated object.
                    try {
                        $history->delete();
                        $history = null;
                    } catch (\Throwable $deleteError) {
                        Log::warning('Job: could not delete history row after block failure (non-fatal)', [
                            'translation_history_id' => $history->id ?? null,
                            'exception' => $deleteError->getMessage(),
                        ]);
                    }

                    throw $e;
                }
            }

            // Metrics persistence is explicitly non-fatal: the user can still
            // retrieve the file, and dashboards tolerate missing metrics rows.
            $metricsService->persistDocumentMetrics($history, $translationResult['metrics'] ?? []);

            // 5. Finalize the state machine: mark complete + publish download URL.
            //    Completion is the LAST step and it is CONDITIONAL: another actor
            //    (a reconciler, a competing worker) may already have made the row
            //    terminal, in which case markCompleted() refuses. Announcing
            //    success after a refusal would tell the user and the admin queue
            //    that work completed while the authoritative row says otherwise.
            $downloadUrl = $this->downloadUrlFor($history, $upload);

            $completed = $job === null || $job->markCompleted(
                $upload['backend'],
                $upload['storage_path'],
                (int) $history->id
            );

            if (! $completed) {
                $this->compensateRefusedCompletion(
                    $job,
                    $history,
                    $historyCreatedThisAttempt,
                    $storageService,
                    $upload
                );

                $this->cleanupFile($outputPath);
                $this->cleanupFile($this->tempPath);

                return;
            }

            $this->storeResult([
                'status' => 'completed',
                'download_url' => $downloadUrl,
                'download_filename' => $downloadFilename,
                'signed_url_expires_at' => $upload['signed_url_expires_at'],
            ]);

            $this->notifyCompleted($history);
            $this->notifyAdminsAwaitingReview($history);

            if (config('translation.python_service.document_jobs')) {
                $translationManager->acknowledgeDocumentJob($job?->engine_job_uuid ?? $this->uuid());
            }

            // StorageService deliberately never removes caller-owned files.
            // These are worker-local scratch copies and are safe to release
            // only after the durable history/storage write has completed.
            $this->cleanupFile($outputPath);
            $this->cleanupFile($this->tempPath);

            return;
        } catch (\Throwable $e) {
            Log::error('Job: Translation failed', [
                'exception' => $e->getMessage(),
                'trace'     => $e->getTraceAsString(),
                'user_id'   => $this->userId,
                'file'      => $this->originalName,
                'job_id'    => $this->uuid(),
            ]);

            $job?->noteProgress(max(0, (int) ($job->progress ?? 0)));

            if ($this->isRetryable($e) && $this->attempts() + 1 < $this->tries) {
                // Return the job to the queue with its original upload intact;
                // deleting tempPath here would guarantee the retry fails.
                //
                // This attempt is NOT terminal: it is being released back onto
                // the queue. Driving the row to `failed` first (the previous
                // order) left the API reporting a failure for work that was
                // still legitimately scheduled to run, for the whole backoff
                // window, and also made the markQueued() below impossible —
                // markTerminallyFailed() refreshes the instance to a terminal
                // state, and markQueued() then refuses a non-active row.
                $this->cleanupFile($outputPath);

                $requeued = $job?->markQueued();
                if ($job !== null && ! $requeued) {
                    Log::warning('Job: retry could not return the row to queued; the authoritative state is unchanged', [
                        'job_id' => $this->uuid(),
                        'translation_job_id' => $job->getKey(),
                        'status' => $job->status,
                    ]);
                }

                $this->storeResult([
                    'status' => 'processing',
                    'message' => 'A temporary error occurred. Retrying...',
                ]);
                $this->release(($this->backoff[$this->attempts()] ?? 120));
                return;
            }

            // Terminal failure. Only now is the row driven terminal, because no
            // further attempt will be made.
            $job?->markTerminallyFailed($e, $this->isRecoverable());

            // Terminal failure: surface it to the frontend AND to failed_jobs
            // so operators can inspect and replay. This is the fix for the
            // finding that failures were being swallowed by cache-only results.
            $this->cleanupFile($this->tempPath);
            $this->cleanupFile($outputPath);
            $this->storeResult([
                'status' => 'failed',
                'error'  => $e->getMessage(),
            ]);

            $this->notifyFailed($this->originalName, $e->getMessage());

            // Restore Laravel failed_jobs visibility (the audit finding). Only
            // tolerate callers that invoke handle() without a bound queue job
            // (e.g. unit tests); the worker always has one.
            try {
                $this->fail($e);
            } catch (\Throwable $failError) {
                Log::warning('Job: could not record failed_jobs entry (no bound job)', [
                    'exception' => $failError->getMessage(),
                    'job_id'    => $this->uuid(),
                ]);
            }
        }
    }

    /**
     * Ensure $this->tempPath points at a real, readable worker-local input file.
     *
     * A first attempt always carries the persisted upload. A replayed job's
     * scratch file was cleaned at terminal failure, so the durable original is
     * fetched from its recorded backend and reconstructed locally. When neither
     * exists the job is unrecoverable and fails honestly.
     */
    private function resolveInputPath(StorageService $storageService, ?TranslationJob $job): void
    {
        if (file_exists($this->tempPath) && is_readable($this->tempPath)) {
            return;
        }

        if (!$this->isRecoverable()) {
            throw new \RuntimeException(
                'The original input file is unavailable and no durable copy exists; this job cannot be replayed.'
            );
        }

        Log::info('Job: reconstructing worker-local input from durable original', [
            'backend'      => $this->originalStorageBackend,
            'storage_path' => $this->originalStoragePath,
            'user_id'      => $this->userId,
            'job_id'       => $this->uuid(),
        ]);

        $contents = $storageService->read($this->originalStorageBackend, $this->originalStoragePath);

        if ($contents === '' || $contents === null) {
            throw new \RuntimeException('Durable original was empty; this job cannot be replayed.');
        }

        $dir = storage_path('app/uploads/recovered');
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }

        $recovered = $dir . DIRECTORY_SEPARATOR . (string) Str::uuid() . $this->originalExt;
        if (file_put_contents($recovered, $contents) === false) {
            throw new \RuntimeException('Failed to reconstruct the worker-local input file.');
        }

        $this->tempPath = $recovered;

        if ($job !== null) {
            $job->noteProgress(5);
        }
    }

    /**
     * A job is recoverable only when a durable original exists on a recorded
     * backend; without it there is nothing for a retry to reconstruct from.
     */
    private function isRecoverable(): bool
    {
        return filled($this->originalStoragePath) && filled($this->originalStorageBackend);
    }

    /**
     * If the original file was never durably stored at upload time, persist it
     * now from the worker's persisted copy using the fallback/primary storage.
     * A successful durable backfill is written back onto the state-machine row
     * so a later operator retry can reconstruct the input.
     */
    private function backfillOriginalStorage(StorageService $storageService, ?TranslationJob $job): void
    {
        if (!file_exists($this->tempPath)) {
            return;
        }
        try {
            $storagePath = $this->userId . '/originals/' . (string) Str::uuid() . $this->originalExt;
            $upload = $storageService->uploadWithFallback($this->tempPath, $storagePath);
            $this->originalStoragePath = $upload['storage_path'];
            $this->originalStorageBackend = $upload['backend'];

            if ($job !== null) {
                TranslationJob::whereKey($job->getKey())
                    ->update([
                        'original_storage_path'   => $this->originalStoragePath,
                        'original_storage_backend' => $this->originalStorageBackend,
                    ]);
            }
        } catch (\Throwable $e) {
            Log::warning('Job: failed to backfill original storage (non-fatal)', [
                'exception' => $e->getMessage(),
                'user_id'   => $this->userId,
            ]);
        }
    }

    private function downloadUrlFor(?\App\Models\TranslationHistory $history, array $upload): ?string
    {
        // Durable-fallback files are served by the app's auth-protected route.
        if ($upload['backend'] === StorageService::BACKEND_LOCAL && $history !== null) {
            return route('history.file', ['id' => $history->id]);
        }

        return $upload['signed_url'] ?? null;
    }

    private function normalizedOutputExt(string $filename): string
    {
        $ext = strtolower((string) pathinfo($filename, PATHINFO_EXTENSION));
        return $ext === '' || strlen($ext) > 10 ? '.bin' : '.' . $ext;
    }

    private function isRetryable(\Throwable $e): bool
    {
        if ($e instanceof TranslationException) {
            $code = $e->getCode();
            if (in_array($code, [503, 504], true)) {
                return true;
            }
            return str_contains((string) $e->getMessage(), 'Could not connect');
        }
        return str_contains((string) $e->getMessage(), 'timed out');
    }

    /**
     * Load the durable state-machine row for this job, tolerating a missing
     * row (jobs dispatched before the migration ran, or a dropped DB).
     */
    private function resolveJob(): ?TranslationJob
    {
        if ($this->translationJobId === null) {
            return null;
        }
        try {
            return TranslationJob::find($this->translationJobId);
        } catch (\Throwable $e) {
            Log::warning('Job: translation_jobs row unavailable (continuing anyway)', [
                'job_id' => $this->translationJobId,
                'exception' => $e->getMessage(),
            ]);
            return null;
        }
    }

    /**
     * Persist a per-milestone result entry for the polling endpoint.
     */
    protected function storeResult(array $result): void
    {
        $result['user_id'] = $this->userId;
        cache()->put(
            'translation_job_' . $this->uuid(),
            $result,
            now()->addHours(1)
        );
    }

    protected function storeProgress(int $progress, string $message): void
    {
        $this->storeResult([
            'status' => 'processing',
            'progress' => $progress,
            'message' => $message,
        ]);
    }

    /**
     * Compensate a completion transition that another actor refused.
     *
     * Two very different situations share a refused transition, and they must
     * not be treated alike:
     *
     *  - The authoritative row is ALREADY completed. This attempt simply lost a
     *    race with the winning worker. That is an idempotency case: the winning
     *    history row and object stay exactly as they are, and this attempt sends
     *    no second completion notification.
     *  - The authoritative row is failed/cancelled. The history row this
     *    attempt created claims `completed` under a transition that was refused,
     *    so it is removed and the object it points at is released. A history row
     *    inherited from a prior attempt is NEVER removed, and no object is
     *    deleted while a surviving history row still references it.
     */
    private function compensateRefusedCompletion(
        ?TranslationJob $job,
        ?TranslationHistory $history,
        bool $historyCreatedThisAttempt,
        StorageService $storageService,
        array $upload
    ): void {
        $authoritative = $job === null
            ? null
            : TranslationJob::find($job->getKey());

        $authoritativeStatus = $authoritative?->status;

        Log::warning('Job: completion transition refused; compensating this attempt only', [
            'job_id' => $this->uuid(),
            'translation_job_id' => $job?->getKey(),
            'authoritative_status' => $authoritativeStatus,
            'history_created_this_attempt' => $historyCreatedThisAttempt,
        ]);

        if ($authoritativeStatus === TranslationJob::STATUS_COMPLETED) {
            // Idempotent: another worker owns the result. Nothing to compensate,
            // and nothing may be deleted — the winner's object is the referenced
            // one now. Report completion once, from the durable row.
            $this->storeResult([
                'status' => 'completed',
                'message' => 'Translation completed.',
            ]);

            return;
        }

        if ($historyCreatedThisAttempt && $history !== null) {
            try {
                $history->delete();
            } catch (\Throwable $e) {
                Log::warning('Job: could not remove the history row created by a refused attempt', [
                    'translation_history_id' => $history->id,
                    'exception' => $e->getMessage(),
                ]);
            }
        }

        $this->releaseUnreferencedObject($storageService, $upload);

        $this->storeResult([
            'status' => 'failed',
            'error' => $authoritative?->error
                ?: 'The translation was stopped before it could be completed.',
        ]);
    }

    /**
     * Delete an object this attempt uploaded, but only when no surviving row
     * still points at it.
     *
     * This asks the SAME question as StorageCleanupService::hasLiveReference -
     * "does any row that can still be executed or replayed need this object?" -
     * but excludes THIS job's own state row. That exclusion is what keeps the
     * two paths from cancelling each other out: this job recorded
     * `translated_storage_path` before the history write, so without the
     * exclusion its own row would vouch for the very object a refused
     * completion must release and the object would never be reclaimed.
     *
     * Every OTHER job still counts, including one that legitimately holds the
     * same object for its own retry.
     */
    private function releaseUnreferencedObject(StorageService $storageService, array $upload): void
    {
        $path = $upload['storage_path'] ?? null;
        $backend = $upload['backend'] ?? null;

        if (blank($path) || blank($backend)) {
            return;
        }

        try {
            $excludeJobIds = ($this->translationJobId !== null) ? [$this->translationJobId] : [];

            // Resolved here rather than injected into handle(): this is the rare
            // refused-completion path, and keeping it out of handle()'s signature
            // avoids churning every direct caller of that method.
            $cleanup = app(StorageCleanupService::class);

            $stillReferenced = $cleanup->hasLiveReference(
                $backend,
                $path,
                [],
                $excludeJobIds
            );

            if ($stillReferenced) {
                return;
            }

            $storageService->delete($backend, $path);
        } catch (\Throwable $e) {
            Log::warning('Job: could not release an object from a refused attempt', [
                'backend' => $backend,
                'exception' => $e->getMessage(),
            ]);
        }
    }

    /**
     * Store the translated output durably. A retry of a partially persisted
     * attempt (history write failed after a successful object upload) reuses
     * the recorded object instead of uploading a second one.
     */
    private function durableTranslatedUpload(StorageService $storageService, ?TranslationJob $job, string $outputPath, string $translatedStoragePath): array
    {
        if ($job !== null && filled($job->translated_storage_path) && filled($job->translated_storage_backend)) {
            return [
                'backend'               => $job->translated_storage_backend,
                'storage_path'          => $job->translated_storage_path,
                'signed_url'            => null,
                'signed_url_expires_at' => now()->addSeconds(StorageService::SIGNED_URL_EXPIRY_SECONDS)->toIso8601String(),
            ];
        }

        return $storageService->uploadWithFallback($outputPath, $translatedStoragePath);
    }

    /**
     * Persist per-block review data and the sidecar onto the history row.
     *
     * Runs inside the completion transaction. Block persistence is REQUIRED for
     * the review workspace, so a failure here must throw (rolling the history
     * insert back) rather than silently completing a document no admin can
     * review. A genuinely block-less envelope is accepted and documented.
     */
    private function persistRequiredBlocks(
        BlockService $blockService,
        TranslationHistory $history,
        array $translationResult
    ): void {
        $history->load('blocks')->blocks()->delete();

        $blockService->persistBlocks(
            $history,
            $translationResult['blocks'] ?? [],
            $translationResult['sidecar'] ?? null
        );
    }

    /**
     * Safely delete a file if it exists.
     */
    private function cleanupFile(?string $path): void
    {
        try {
            if ($path && file_exists($path)) {
                @unlink($path);
            }
        } catch (\Throwable $e) {
            // Ignore cleanup errors
        }
    }

    /**
     * Push a "translation completed" database notification to the owner.
     */
    private function notifyCompleted(?\App\Models\TranslationHistory $history): void
    {
        if ($history === null) {
            return;
        }
        try {
            User::find($this->userId)?->notify(new TranslationCompleted($history));
        } catch (\Throwable $e) {
            Log::warning('Job: Failed to send completion notification (non-fatal)', [
                'exception' => $e->getMessage(),
                'user_id' => $this->userId,
            ]);
        }
    }

    /**
     * Push a "translation failed" database notification to the owner.
     */
    private function notifyFailed(string $filename, string $message): void
    {
        try {
            User::find($this->userId)?->notify(new TranslationFailed($filename, $message));
        } catch (\Throwable $e) {
            Log::warning('Job: Failed to send failure notification (non-fatal)', [
                'exception' => $e->getMessage(),
                'user_id' => $this->userId,
            ]);
        }
    }

    /**
     * Fan out a "new translation awaiting review" notification to every admin.
     */
    private function notifyAdminsAwaitingReview(?\App\Models\TranslationHistory $history): void
    {
        if ($history === null) {
            return;
        }
        AdminNotifier::awaitingReview($history, User::find($this->userId)?->name);
    }
}
