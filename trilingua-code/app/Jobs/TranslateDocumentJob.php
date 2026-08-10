<?php

namespace App\Jobs;

use App\Models\User;
use App\Notifications\TranslationCompleted;
use App\Notifications\TranslationFailed;
use App\Services\BlockService;
use App\Services\HistoryService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use App\Services\TranslationService;
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
     * The UUID for this job, set explicitly so the controller and cache key match.
     */
    private ?string $jobUuid = null;

    /**
     * Create a new job instance.
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
        public ?int $parentDocumentId = null
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
     * Execute the job.
     */
    public function handle(
        TranslationManager $translationManager,
        StorageService $storageService,
        HistoryService $historyService,
        BlockService $blockService
    ): void {
        // Store initial "processing" state in cache so frontend knows we're working
        $this->storeResult([
            'status' => 'processing',
            'message' => 'Document queued for translation. Processing will begin shortly.',
        ]);

        try {
            @set_time_limit(0);

            // Create a temporary UploadedFile from the temp path
            if (!file_exists($this->tempPath)) {
                throw new \RuntimeException('Uploaded file not found at: ' . $this->tempPath);
            }

            $uploadedFile = new UploadedFile(
                $this->tempPath,
                $this->originalName,
                null,
                null,
                true
            );

            // 1. Translate the document via TranslationManager
            $translationResult = $translationManager->translateDocument(
                $uploadedFile,
                $this->sourceLang,
                $this->targetLang,
                $this->pdfColumnMode,
                $this->mode
            );

            $downloadFilename = $translationResult['download_filename'];

            // Save the translated file to a temp path for storage/fallback
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

            // 2. Try Supabase upload first
            $translatedStoragePath = $this->userId . '/' . basename($outputPath);

            try {
                $storageResult = $storageService->uploadFile($outputPath, $translatedStoragePath);
                
                // Upload succeeded — clean up temp file
                $this->cleanupFile($outputPath);
                $this->cleanupFile($this->tempPath);

                // Store result with signed URL
                $this->storeResult([
                    'status' => 'completed',
                    'download_url' => $storageResult['signed_url'],
                    'download_filename' => $downloadFilename,
                    'signed_url_expires_at' => $storageResult['signed_url_expires_at'],
                ]);

                // Create history record (non-blocking)
                $history = null;
                try {
                    $history = $historyService->insertRecord([
                        'user_id'               => $this->userId,
                        'original_filename'     => $this->originalName,
                        'translated_filename'   => $downloadFilename,
                        'source_language'       => $this->sourceLang,
                        'target_language'       => $this->targetLang,
                        'created_at'            => now()->toIso8601String(),
                        'storage_path'          => $translatedStoragePath,
                        'original_storage_path' => $this->originalStoragePath,
                        'file_size'             => $this->fileSize,
                        'status'                => 'completed',
                        'review_status'         => ReviewStatus::PENDING,
                        'signed_url_expires_at' => $storageResult['signed_url_expires_at'],
                        'job_id'                => $this->jobUuid,
                        'parent_document_id'    => $this->parentDocumentId,
                    ]);

                    // Persist per-block review data + roll up quality score.
                    $this->persistDocumentBlocks($blockService, $history, $translationResult);
                } catch (\Throwable $e) {
                    Log::warning('Job: Failed to insert history record (non-fatal)', [
                        'exception' => $e->getMessage(),
                        'user_id' => $this->userId,
                    ]);
                }

                $this->notifyCompleted($history);
                $this->notifyAdminsAwaitingReview($history);

                return;
            } catch (\Throwable $storageError) {
                // Supabase upload failed — try inline download as fallback
                Log::warning('Job: Supabase upload failed, trying inline download fallback', [
                    'exception' => $storageError->getMessage(),
                    'user_id' => $this->userId,
                ]);

                $inlineDownload = $this->buildInlineDownloadPayload($outputPath, $downloadFilename);
                $this->cleanupFile($outputPath);
                $this->cleanupFile($this->tempPath);

                if (!empty($inlineDownload['download_data'])) {
                    $this->storeResult([
                        'status' => 'completed',
                        'download_mode' => 'inline',
                        'download_data' => $inlineDownload['download_data'],
                        'download_filename' => $downloadFilename,
                        'download_mime' => $inlineDownload['download_mime'],
                    ]);

                    // Create history record for inline download
                    $history = null;
                    try {
                        $history = $historyService->insertRecord([
                            'user_id'               => $this->userId,
                            'original_filename'     => $this->originalName,
                            'translated_filename'   => $downloadFilename,
                            'source_language'       => $this->sourceLang,
                            'target_language'       => $this->targetLang,
                            'created_at'            => now()->toIso8601String(),
                            'file_size'             => $this->fileSize,
                            'status'                => 'completed',
                            'review_status'         => ReviewStatus::PENDING,
                            'job_id'                => $this->jobUuid,
                            'parent_document_id'    => $this->parentDocumentId,
                        ]);

                        // Persist per-block review data + roll up quality score.
                        $this->persistDocumentBlocks($blockService, $history, $translationResult);
                    } catch (\Throwable $e) {
                        Log::warning('Job: Failed to insert history record for inline download (non-fatal)', [
                            'exception' => $e->getMessage(),
                        ]);
                    }

                    $this->notifyCompleted($history);
                    $this->notifyAdminsAwaitingReview($history);

                    return;
                }

                // Both upload and inline failed
                throw new \RuntimeException(
                    'Failed to deliver translated file: ' . $storageError->getMessage()
                );
            }

        } catch (\Throwable $e) {
            Log::error('Job: Translation failed', [
                'exception' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
                'user_id' => $this->userId,
                'file' => $this->originalName,
            ]);

            // Clean up temp files
            $this->cleanupFile($this->tempPath);

            // ALWAYS store the failure result so frontend polling can detect it
            $this->storeResult([
                'status' => 'failed',
                'error' => $e->getMessage(),
            ]);

            $this->notifyFailed($this->originalName, $e->getMessage());

            // Do NOT call $this->fail() — with sync queue, that would throw an
            // exception back to the controller causing a 500 error. Instead we
            // store the failure in cache for the frontend to poll.
        }
    }

    /**
     * Persist per-block review data and the sidecar onto the history row.
     *
     * Blocks only exist for document translations and are never persisted for
     * text translations. This is a best-effort post-processing step — a failure
     * here must not fail an otherwise-successful translation delivery.
     */
    private function persistDocumentBlocks(
        BlockService $blockService,
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
    private function cleanupFile(string $path): void
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
     * Store the job result for polling.
     */
    protected function storeResult(array $result): void
    {
        cache()->put(
            'translation_job_' . $this->jobUuid,
            $result,
            now()->addHours(1)
        );
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

    /**
     * Build inline download payload for fallback.
     */
    protected function buildInlineDownloadPayload(string $outputPath, string $downloadFilename): array
    {
        try {
            if (!file_exists($outputPath)) {
                return ['download_filename' => $downloadFilename, 'download_data' => '', 'download_mime' => 'application/octet-stream'];
            }

            $contents = file_get_contents($outputPath);
            $mimeType = mime_content_type($outputPath) ?: 'application/octet-stream';

            if ($contents === false || $contents === '') {
                return ['download_filename' => $downloadFilename, 'download_data' => '', 'download_mime' => $mimeType];
            }

            return [
                'download_filename' => $downloadFilename,
                'download_data'     => 'data:' . $mimeType . ';base64,' . base64_encode($contents),
                'download_mime'     => $mimeType,
            ];
        } catch (\Throwable $e) {
            Log::warning('Job: buildInlineDownloadPayload failed', ['exception' => $e->getMessage()]);
            return ['download_filename' => $downloadFilename, 'download_data' => '', 'download_mime' => 'application/octet-stream'];
        }
    }
}