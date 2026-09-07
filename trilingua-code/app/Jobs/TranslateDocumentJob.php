<?php

namespace App\Jobs;

use App\Exceptions\TranslationException;
use App\Models\TranslationJob;
use App\Models\User;
use App\Notifications\TranslationCompleted;
use App\Notifications\TranslationFailed;
use App\Services\BlockService;
use App\Services\HistoryService;
use App\Services\MetricsService;
use App\Services\StorageService;
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
     * Timeout must exceed the python service's 600s limit plus upload margins.
     */
    public int $timeout = 650;

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
    ) {}

    /**
     * Get the UUID for this job instance.
     */
    public function uuid(): string
    {
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
        $job?->markProcessing();
        $outputPath = null;

        $this->storeProgress(10, 'Document queued for translation. Processing will begin shortly.');

        try {
            if (!file_exists($this->tempPath)) {
                throw new \RuntimeException('Uploaded file not found at: ' . $this->tempPath);
            }

            // Ensure the ORIGINAL file is stored durably (used by re-translation
            // and the review workspace). If the initial upload failed but the
            // durable fallback exists, backfill it now from the worker's copy.
            if ($this->originalStoragePath === null) {
                $this->backfillOriginalStorage($storageService);
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
            $translationResult = $translationManager->translateDocument(
                $uploadedFile,
                $this->sourceLang,
                $this->targetLang,
                $this->pdfColumnMode,
                $this->mode
            );

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
            $translatedStoragePath = $this->userId . '/translations/' . (string) Str::uuid() . $this->normalizedOutputExt($downloadFilename);

            $job?->noteProgress(80);
            $this->storeProgress(80, 'Uploading translated file...');

            $upload = $storageService->uploadWithFallback($outputPath, $translatedStoragePath);

            $job?->noteProgress(95);

            // 4. Record the translation in history (source of truth for the UI).
            $history = null;
            try {
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

                // Persist per-block review data + roll up quality score.
                $this->persistDocumentBlocks($blockService, $metricsService, $history, $translationResult);
            } catch (\Throwable $e) {
                Log::error('Job: Failed to insert history record (non-fatal)', [
                    'exception' => $e->getMessage(),
                    'user_id'   => $this->userId,
                ]);
            }

            // 5. Finalize the state machine: mark complete + publish download URL.
            $downloadUrl = $this->downloadUrlFor($history, $upload);

            $job?->markCompleted($upload['backend'], $upload['storage_path'], $history?->id);

            $this->storeResult([
                'status' => 'completed',
                'download_url' => $downloadUrl,
                'download_filename' => $downloadFilename,
                'signed_url_expires_at' => $upload['signed_url_expires_at'],
            ]);

            $this->notifyCompleted($history);
            $this->notifyAdminsAwaitingReview($history);

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
            $job?->noteError($e);

            if ($this->isRetryable($e) && $this->attempts() + 1 < $this->tries) {
                // Return the job to the queue with its original upload intact;
                // deleting tempPath here would guarantee the retry fails.
                $this->cleanupFile($outputPath);
                $job?->markQueued();
                $this->storeResult([
                    'status' => 'processing',
                    'message' => 'A temporary error occurred. Retrying...',
                ]);
                $this->release(($this->backoff[$this->attempts()] ?? 120));
                return;
            }

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
     * If the original file was never durably stored at upload time, persist it
     * now from the worker's persisted copy using the fallback/primary storage.
     */
    private function backfillOriginalStorage(StorageService $storageService): void
    {
        if (!file_exists($this->tempPath)) {
            return;
        }
        try {
            $storagePath = $this->userId . '/originals/' . (string) Str::uuid() . $this->originalExt;
            $upload = $storageService->uploadWithFallback($this->tempPath, $storagePath);
            $this->originalStoragePath = $upload['storage_path'];
            $this->originalStorageBackend = $upload['backend'];
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
     * Persist per-block review data and the sidecar onto the history row.
     */
    private function persistDocumentBlocks(
        BlockService $blockService,
        MetricsService $metricsService,
        ?\App\Models\TranslationHistory $history,
        array $translationResult
    ): void {
        if ($history === null) {
            return;
        }
        try {
            $history->load('blocks')->blocks()->delete();
            $blockService->persistBlocks(
                $history,
                $translationResult['blocks'] ?? [],
                $translationResult['sidecar'] ?? null
            );

            // Persist the engine metrics returned by the Python service.
            $metricsService->persistDocumentMetrics(
                $history,
                $translationResult['metrics'] ?? []
            );
        } catch (\Throwable $e) {
            Log::warning('Job: Failed to persist document blocks (non-fatal)', [
                'exception' => $e->getMessage(),
                'translation_history_id' => $history->id ?? null,
            ]);
        }
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
