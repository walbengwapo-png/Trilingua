<?php

namespace App\Http\Controllers;

use App\Exceptions\TranslationException;
use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Notifications\TranslationCompleted;
use App\Services\HistoryService;
use App\Services\MetricsService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use App\Services\Translation\DTO\TranslationRequest;
use App\Services\Translation\DTO\TranslationResponse;
use App\Support\ReviewStatus;
use App\Support\SafeFileNames;
use Illuminate\Contracts\View\View;
use Illuminate\Database\QueryException;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Illuminate\Validation\Rule;

class TranslationController extends Controller
{
    public function __construct(
        private TranslationManager $translationManager,
        private StorageService $storage,
        private HistoryService $history,
        private MetricsService $metricsService,
    ) {}

    /**
     * GET /translate — render the translation page.
     */
    public function show(): View
    {
        return view('translation');
    }

    /**
     * POST /translate — handle text or document translation.
     * Documents are dispatched to queue for async processing. The durable
     * dedup key is the sha256 of (user, original file bytes, language pair,
     * engine mode, pdf mode, parent) — enforced by a partial unique index on
     * translation_jobs so double-clicks can never enqueue a second copy while
     * the first is still running or waiting.
     */
    public function translate(Request $request): JsonResponse
    {
        $sourceLang = $request->input('source_lang');

        // Validate basic fields
        $validated = $request->validate([
            'source_lang' => ['required', Rule::in(['English', 'Cebuano', 'Filipino'])],
            'target_lang' => [
                'required',
                Rule::in(['English', 'Cebuano', 'Filipino']),
                Rule::notIn([$sourceLang]),
            ],
            'text'     => ['nullable', 'string', 'max:8000'],
            'document' => ['nullable', 'file', 'mimes:docx,pdf,txt,md,rtf,odt,csv,pptx,xlsx', 'max:51200'],
            'pdf_column_mode' => ['nullable', Rule::in(['auto', 'single', 'left', 'right'])],
            'mode' => ['nullable', Rule::in(['fast', 'balanced', 'thorough', 'auto'])],
        ], [
            'target_lang.not_in' => 'The source language and target language must be different.',
        ]);

        $targetLang = $validated['target_lang'];
        $pdfColumnMode = $validated['pdf_column_mode'] ?? 'auto';

        // Manual validation: ensure either text or document is provided
        $hasText = !empty($validated['text']);
        $hasDocument = $request->hasFile('document');

        if (!$hasText && !$hasDocument) {
            return response()->json([
                'error' => 'Please enter text to translate or attach a document.',
                'errors' => [
                    'text' => ['The text field is required when document is not present.'],
                ]
            ], 422);
        }

        try {
            // Document mode — dispatch to queue for async processing
            if ($request->hasFile('document')) {
                return $this->handleDocument($request, $validated, $sourceLang, $targetLang, $pdfColumnMode);
            }

            // Text mode — process synchronously (fast enough)
            $translationRequest = new TranslationRequest(
                text: $request->input('text'),
                sourceLang: $sourceLang,
                targetLang: $targetLang,
            );
            $result = $this->translationManager->translateText($translationRequest);

            // Log text translation to history (non-blocking)
            try {
                $record = $this->history->insertRecord([
                    'user_id'          => Auth::id(),
                    'translation_type' => 'text',
                    'source_text'      => $request->input('text'),
                    'translated_text'  => $result->translatedText,
                    'source_language'  => $sourceLang,
                    'target_language'  => $targetLang,
                    'created_at'       => now()->toIso8601String(),
                    'status'           => 'completed',
                    'review_status'    => ReviewStatus::PENDING,
                ]);

                if ($record !== null) {
                    Auth::user()->notify(new TranslationCompleted($record));
                    \App\Support\AdminNotifier::awaitingReview($record, Auth::user()->name);

                    $this->metricsService->persistTextMetrics($record, [
                        'provider' => $result->provider,
                        'model' => $result->model,
                        'token_usage' => $result->tokenUsage,
                        'execution_time_ms' => $result->executionTimeMs,
                    ]);
                }
            } catch (\Throwable $e) {
                Log::error('Failed to insert text translation history record', [
                    'exception'  => $e->getMessage(),
                    'user_id'    => Auth::id(),
                ]);
            }

            return response()->json(['translated' => $result->translatedText]);

        } catch (TranslationException $e) {
            $message = $e->getMessage();
            $code = $e->getCode() ?: 500;

            Log::error('Translation service error', [
                'exception' => $message,
                'code' => $code,
                'user_id' => Auth::id(),
            ]);

            // User-friendly error messages based on error type
            if (str_contains($message, 'timed out')) {
                return response()->json([
                    'error' => 'Translation timed out. The document may be too large or complex. Try a smaller file or simpler content, and we will try again.',
                    'retryable' => true,
                ], 504);
            }

            if (str_contains($message, 'Could not connect')) {
                return response()->json([
                    'error' => 'The translation service is temporarily unavailable. Please try again in a moment or contact support if the issue persists.',
                    'retryable' => true,
                ], 503);
            }

            if ($code === 400) {
                return response()->json(['error' => $message], 400);
            }

            return response()->json([
                'error' => $message ?: 'Translation failed. Please try again or contact support if the problem persists.',
                'retryable' => true,
            ], $code);
        } catch (\Throwable $e) {
            Log::error('Unexpected error in translation controller', [
                'exception' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
                'user_id' => Auth::id(),
            ]);

            return response()->json([
                'error' => 'An unexpected error occurred during translation. Please try again. If the problem continues, contact support.',
                'retryable' => true,
            ], 500);
        }
    }

    /**
     * Handle a document translation submission end-to-end.
     */
    private function handleDocument(
        Request $request,
        array $validated,
        string $sourceLang,
        string $targetLang,
        string $pdfColumnMode
    ): JsonResponse {
        $uploadedFile = $request->file('document');
        $userId = Auth::id();

        $originalName = SafeFileNames::scrubDisplayName($uploadedFile->getClientOriginalName());
        $originalExt = '.' . strtolower((string) pathinfo($originalName, PATHINFO_EXTENSION));
        $fileSize = (int) $uploadedFile->getSize();
        $mode = $validated['mode'] ?? 'balanced';

        if ($quota = $this->exceedsUploadQuota($userId, $fileSize)) {
            return response()->json($quota, 429);
        }

        // 1. Persist the uploaded file so the queue worker can read it later
        //    (PHP deletes the temp file when this request ends). The on-disk
        //    leaf is server-generated and opaque.
        $persistDir = storage_path('app/uploads/' . Str::uuid());
        if (!is_dir($persistDir)) {
            mkdir($persistDir, 0755, true);
        }
        $persistentPath = $persistDir . DIRECTORY_SEPARATOR . 'source' . $originalExt;
        try {
            $uploadedFile->move($persistDir, basename($persistentPath));
        } catch (\Throwable $e) {
            Log::error('Failed to persist uploaded file for translation job', [
                'exception' => $e->getMessage(),
                'user_id' => $userId,
            ]);
            throw new TranslationException(
                'The uploaded file could not be stored for processing. Please try again.'
            );
        }

        // 2. Sniff content so a spoofed extension cannot smuggle executable/binary
        //    uploads through the mime filter.
        if (!$this->contentsMatchExtension($originalExt, $persistentPath)) {
            $this->cleanupUploadDir($persistDir);
            return response()->json([
                'error' => 'The uploaded file does not match its file type. Please re-export it from your app and try again.',
            ], 422);
        }

        // 3. Durable dedup key — hash the actual bytes, then dedup.
        $contentHash = hash_file('sha256', $persistentPath);
        $payloadHash = TranslationJob::payloadHash(
            $userId,
            $contentHash,
            $sourceLang,
            $targetLang,
            $mode,
            $pdfColumnMode,
            null,
        );

        // 3a. Reuse an identical COMPLETED translation instead of doing the work again.
        $completed = TranslationJob::where('user_id', $userId)
            ->where('payload_hash', $payloadHash)
            ->where('status', TranslationJob::STATUS_COMPLETED)
            ->orderByDesc('id')
            ->first();

        if ($completed !== null) {
            $this->cleanupUploadDir($persistDir);
            $payload = $this->buildCompletedPayload($completed);

            if ($payload !== null) {
                $payload['reused'] = true;
                return response()->json($payload);
            }
        }

        // 3b. If an identical job is still active, hand its job_id back.
        $existingActive = $this->findActiveJob($userId, $payloadHash);
        if ($existingActive !== null) {
            $this->cleanupUploadDir($persistDir);
            return response()->json([
                'status' => 'processing',
                'duplicate' => true,
                'job_id' => $existingActive->uuid,
                'message' => 'A translation for this exact file is already in progress.',
            ], 200);
        }

        // 4. Upload the ORIGINAL file to durable storage (opaque key). If all
        //    backends fail, translation can still proceed — the job will backfill.
        $originalStoragePath = null;
        $originalStorageBackend = 'supabase';
        try {
            $originalKey = StorageService::makeStorageKey($userId, 'originals', $originalName);
            $originalUpload = $this->storage->uploadWithFallback($persistentPath, $originalKey);
            $originalStoragePath = $originalUpload['storage_path'];
            $originalStorageBackend = $originalUpload['backend'];
        } catch (\Throwable $e) {
            Log::warning('Original file storage failed (translation will still proceed)', [
                'exception' => $e->getMessage(),
                'user_id' => $userId,
            ]);
        }

        // 5. Create the durable state-machine row; the partial unique index is
        //    the final guard against a race between two identical submissions.
        $jobRow = TranslationJob::create([
            'user_id'          => $userId,
            'payload_hash'     => $payloadHash,
            'original_name'    => $originalName,
            'original_ext'     => $originalExt,
            'source_lang'      => $sourceLang,
            'target_lang'      => $targetLang,
            'pdf_column_mode'  => $pdfColumnMode,
            'mode'             => $mode,
            'file_size'        => $fileSize,
            'original_storage_path' => $originalStoragePath,
            'original_storage_backend' => $originalStorageBackend,
            'parent_document_id' => null,
            'status'           => TranslationJob::STATUS_CREATED,
        ]);

        try {
            $job = new TranslateDocumentJob(
                $originalName,
                $originalExt,
                $fileSize,
                $sourceLang,
                $targetLang,
                $pdfColumnMode,
                $persistentPath,
                $userId,
                $originalStoragePath,
                $mode,
                null,
                $originalStorageBackend,
                (int) $jobRow->id,
            );
            $jobId = $job->uuid();

            $jobRow->uuid = $jobId;
            $jobRow->status = TranslationJob::STATUS_QUEUED;
            $jobRow->progress = 5;
            $jobRow->last_heartbeat_at = now();
            $jobRow->save();

            dispatch($job);

            // A cache marker keeps very short polling windows working without
            // hammering translation_jobs; the DB row is authoritative.
            cache()->put(
                'translation_job_' . $jobId,
                [
                    'status' => 'queued',
                    'progress' => 5,
                    'message' => 'Document queued for translation. Processing will begin shortly.',
                    'user_id' => $userId,
                ],
                now()->addMinutes(30)
            );

            return response()->json([
                'job_id' => $jobId,
                'status' => 'processing',
                'message' => 'Document queued for translation. Processing will begin shortly.',
                'original_filename' => $originalName,
            ]);
        } catch (QueryException $e) {
            // Lost the race against an identical active job — return it instead.
            $this->cleanupUploadDir($persistDir);
            $jobRow->delete();

            $winner = $this->findActiveJob($userId, $payloadHash);
            if ($winner !== null) {
                return response()->json([
                    'status' => 'processing',
                    'duplicate' => true,
                    'job_id' => $winner->uuid,
                    'message' => 'A translation for this exact file is already in progress.',
                ], 200);
            }

            throw $e;
        } catch (\Throwable $e) {
            Log::error('Failed to dispatch translation job', [
                'exception' => $e->getMessage(),
                'user_id' => $userId,
            ]);
            throw $e;
        }
    }

    /**
     * GET /translate/status/{job_id} — poll for document translation status.
     *
     * Auth-protected. Ownership is resolved three ways, in order:
     *   1. A `translation_jobs` row keyed by uuid (source of truth) — user-scoped.
     *   2. A completed `translation_history` row keyed by job_id — user-scoped.
     *   3. A cache entry stamped with the owner's user_id.
     * Anyone else gets a 404 (existence not leaked).
     */
    public function status(string $jobId): JsonResponse
    {
        $userId = Auth::id();

        // 1. Durable state-machine row.
        $job = TranslationJob::where('uuid', $jobId)->where('user_id', $userId)->first();

        if ($job !== null) {
            if ($job->status === TranslationJob::STATUS_COMPLETED) {
                $payload = $this->buildCompletedPayload($job);
                if ($payload !== null) {
                    return response()->json($payload);
                }
                return response()->json([
                    'status' => 'processing',
                    'message' => 'Translation is still in progress...',
                ]);
            }

            if ($job->status === TranslationJob::STATUS_FAILED) {
                return response()->json([
                    'status' => 'failed',
                    'error'  => $job->error ?: 'Translation failed. Please try again.',
                ]);
            }

            // created / queued / processing
            return response()->json([
                'status'   => 'processing',
                'progress' => $job->progress ?? 0,
                'message'  => 'Translation is still in progress...',
            ]);
        }

        // 2. Completed job leaves a user-scoped history row keyed by job_id.
        $owned = TranslationHistory::where('job_id', $jobId)
            ->where('user_id', $userId)
            ->exists();

        if ($owned) {
            $result = Cache::get('translation_job_' . $jobId);

            if ($result && isset($result['status']) && $result['status'] !== 'processing') {
                return response()->json($result);
            }

            $history = TranslationHistory::where('job_id', $jobId)
                ->where('user_id', $userId)
                ->first();

            if ($history && $history->storage_path) {
                $payload = $this->buildHistoryCompletedPayload($history);
                if ($payload !== null) {
                    return response()->json($payload);
                }
            }

            if ($history) {
                return response()->json([
                    'status' => 'completed',
                    'download_url' => '/history/' . $history->id . '/file',
                    'download_filename' => $history->translated_filename,
                ]);
            }

            return response()->json([
                'status' => 'processing',
                'message' => 'Translation is still in progress...',
            ]);
        }

        // 3. No DB row yet — in-flight legacy job or unknown.
        $result = Cache::get('translation_job_' . $jobId);

        if (is_array($result) && isset($result['user_id']) && (int) $result['user_id'] === $userId) {
            return response()->json($result);
        }

        return response()->json([
            'error' => 'Translation job not found or you do not have access to it.',
        ], 404);
    }

    private function findActiveJob(int $userId, string $payloadHash): ?TranslationJob
    {
        return TranslationJob::where('user_id', $userId)
            ->where('payload_hash', $payloadHash)
            ->whereIn('status', TranslationJob::ACTIVE_STATUSES)
            ->orderByDesc('id')
            ->first();
    }

    private function buildCompletedPayload(TranslationJob $job): ?array
    {
        if (blank($job->translation_history_id)) {
            return null;
        }

        $history = TranslationHistory::where('id', $job->translation_history_id)
            ->where('user_id', $job->user_id)
            ->first();

        return $history !== null ? $this->buildHistoryCompletedPayload($history) : null;
    }

    private function buildHistoryCompletedPayload(TranslationHistory $history): ?array
    {
        $backend = $history->storage_backend ?: StorageService::BACKEND_SUPABASE;

        if ($backend === StorageService::BACKEND_LOCAL) {
            return [
                'status' => 'completed',
                'download_url' => route('history.file', ['id' => $history->id]),
                'download_filename' => $history->translated_filename,
            ];
        }

        try {
            $signedResult = $this->storage->generateSignedUrl($history->storage_path);

            return [
                'status' => 'completed',
                'download_url' => $signedResult['signed_url'],
                'download_filename' => $history->translated_filename,
                'signed_url_expires_at' => $signedResult['signed_url_expires_at'],
            ];
        } catch (\Throwable $e) {
            Log::warning('Failed to generate signed URL for completed translation', [
                'exception' => $e->getMessage(),
                'translation_history_id' => $history->id,
            ]);
        }

        return null;
    }

    /**
     * @return array{error: string}|null  Response body if the quota is exceeded.
     */
    private function exceedsUploadQuota(int $userId, int $newFileSize): ?array
    {
        $maxFiles = (int) config('translation.upload.max_daily_files', 25);
        $maxBytes = (int) config('translation.upload.max_daily_bytes', 262144000);

        $start = now()->startOfDay();

        $stats = TranslationHistory::where('user_id', $userId)
            ->where('translation_type', 'document')
            ->where('created_at', '>=', $start)
            ->selectRaw('count(*) as files, coalesce(sum(file_size), 0) as bytes')
            ->first();

        $files = (int) $stats?->files;
        $bytes = (int) $stats?->bytes;

        if (($files + 1) > $maxFiles || ($bytes + $newFileSize) > $maxBytes) {
            Log::warning('Document upload quota exceeded', [
                'user_id' => $userId,
                'count' => $files,
                'bytes' => $bytes,
            ]);

            return [
                'error' => 'You have reached the daily document upload limit. Please try again tomorrow or contact support.',
            ];
        }

        return null;
    }

    /**
     * Verify that file contents are plausible for the claimed extension, so an
     * extension spoof cannot carry an actual executable past the mime whitelist.
     */
    private function contentsMatchExtension(string $ext, string $path): bool
    {
        $ext = ltrim(strtolower($ext), '.');
        $head = @file_get_contents($path, false, null, 0, 8192);
        if ($head === false) {
            return false;
        }

        if (in_array($ext, ['docx', 'pptx', 'xlsx', 'odt'], true)) {
            return str_starts_with($head, 'PK');
        }

        if ($ext === 'pdf') {
            return str_starts_with($head, '%PDF-');
        }

        // text-like formats must not contain NUL bytes (executable/binary check)
        return !str_contains(substr($head, 0, 4096), "\x00");
    }

    private function cleanupUploadDir(string $dir): void
    {
        try {
            if (is_dir($dir)) {
                foreach (scandir($dir) ?: [] as $entry) {
                    if ($entry === '.' || $entry === '..') {
                        continue;
                    }
                    @unlink($dir . DIRECTORY_SEPARATOR . $entry);
                }
                @rmdir($dir);
            }
        } catch (\Throwable $e) {
            Log::warning('Failed to clean upload directory', ['dir' => $dir, 'exception' => $e->getMessage()]);
        }
    }
}