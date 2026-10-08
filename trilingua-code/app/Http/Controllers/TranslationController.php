<?php

namespace App\Http\Controllers;

use App\Exceptions\TranslationException;
use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Notifications\TranslationCompleted;
use App\Services\DispatchOutcome;
use App\Services\DispatchOutcomeClassifier;
use App\Services\FileCleanup;
use App\Services\HistoryService;
use App\Services\MetricsService;
use App\Services\QuotaService;
use App\Services\StorageService;
use App\Services\Translation\CompletedDownloadResolver;
use App\Services\Translation\DTO\TranslationRequest;
use App\Services\Translation\TranslationManager;
use App\Support\AdminNotifier;
use App\Support\ReviewStatus;
use App\Support\SafeFileNames;
use Illuminate\Contracts\View\View;
use Illuminate\Database\QueryException;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
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
        private QuotaService $quota,
        private DispatchOutcomeClassifier $dispatchOutcome,
        private CompletedDownloadResolver $downloadResolver,
    ) {}

    /**
     * GET /translate — render the translation page.
     */
    public function show(): View
    {
        return view('translation', ['capabilities' => $this->capabilityContract()]);
    }

    /**
     * GET /translate/capabilities — authenticated clients can refresh the
     * server-owned translation contract without duplicating validation rules.
     */
    public function capabilities(): JsonResponse
    {
        return response()->json($this->capabilityContract());
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
        $requestId = (string) Str::uuid();
        $request->attributes->set('translation_stage', 'validation');
        $sourceLang = $request->input('source_lang');

        // Validate basic fields
        $validated = $request->validate([
            'source_lang' => ['required', Rule::in(config('translation.languages', []))],
            'target_lang' => [
                'required',
                Rule::in(config('translation.languages', [])),
                Rule::notIn([$sourceLang]),
            ],
            'text' => ['nullable', 'string', 'max:'.(int) config('translation.text_max_chars', 8000)],
            // Do not use Laravel's `mimes` rule here. On this Windows/PHP
            // installation fileinfo identifies valid OOXML files as
            // application/octet-stream, which rejects genuine DOCX/PPTX/XLSX
            // uploads before the content check below can run. Validate the
            // client extension here, then verify the file signature after it
            // has been persisted in handleDocument().
            'document' => ['nullable', 'file', 'extensions:'.implode(',', config('translation.supported_formats', [])), 'max:'.(int) config('translation.max_upload_kb', 51200)],
            'pdf_column_mode' => ['nullable', Rule::in(config('translation.pdf_column_modes', []))],
            'mode' => ['nullable', Rule::in(config('translation.modes', []))],
        ], [
            'target_lang.not_in' => 'The source language and target language must be different.',
        ]);

        $targetLang = $validated['target_lang'];
        $pdfColumnMode = $validated['pdf_column_mode'] ?? 'auto';

        // Manual validation: ensure either text or document is provided
        $hasText = ! empty($validated['text']);
        $hasDocument = $request->hasFile('document');

        if (! $hasText && ! $hasDocument) {
            return response()->json([
                'error' => 'Please enter text to translate or attach a document.',
                'errors' => [
                    'text' => ['The text field is required when document is not present.'],
                ],
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
                mode: $validated['mode'] ?? 'balanced',
            );
            $request->attributes->set('translation_stage', 'python_text');
            $result = $this->translationManager->translateText($translationRequest);
            $request->attributes->set('translation_stage', 'text_persistence');

            // History is non-blocking, but its outcome must be reported separately
            // from later notification and metrics failures.
            $record = null;
            try {
                $record = $this->history->insertRecord([
                    'user_id' => Auth::id(),
                    'translation_type' => 'text',
                    'source_text' => $request->input('text'),
                    'translated_text' => $result->translatedText,
                    'source_language' => $sourceLang,
                    'target_language' => $targetLang,
                    'created_at' => now()->toIso8601String(),
                    'status' => 'completed',
                    'review_status' => ReviewStatus::PENDING,
                ]);

            } catch (\Throwable $e) {
                Log::error('Failed to insert text translation history record', [
                    'exception' => $e->getMessage(),
                    'user_id' => Auth::id(),
                ]);
            }

            if ($record !== null) {
                try {
                    Auth::user()->notify(new TranslationCompleted($record));
                    AdminNotifier::awaitingReview($record, Auth::user()->name);
                } catch (\Throwable $e) {
                    Log::warning('Failed to notify about saved text translation', [
                        'exception' => $e->getMessage(),
                        'translation_history_id' => $record->id,
                    ]);
                }

                try {
                    $this->metricsService->persistTextMetrics($record, [
                        'provider' => $result->provider,
                        'model' => $result->model,
                        'token_usage' => $result->tokenUsage,
                        'execution_time_ms' => $result->executionTimeMs,
                        'mode' => $result->mode,
                        'quality_score' => $result->qualityScore,
                        'quality_issues' => $result->qualityIssues,
                        'warnings' => $result->warnings,
                    ]);
                } catch (\Throwable $e) {
                    Log::warning('Failed to save text translation metrics', [
                        'exception' => $e->getMessage(),
                        'translation_history_id' => $record->id,
                    ]);
                }
            }

            return response()->json([...$result->toArray(), 'saved' => $record !== null]);

        } catch (TranslationException $e) {
            $message = $e->getMessage();
            $code = $e->getCode() ?: 500;

            Log::error('Translation service error', [
                'request_id' => $requestId,
                'stage' => $request->attributes->get('translation_stage'),
                'exception_class' => $e::class,
                'exception' => $message,
                'code' => $code,
                'user_id' => Auth::id(),
            ]);

            // User-friendly error messages based on error type
            if (str_contains($message, 'timed out')) {
                return response()->json([
                    'request_id' => $requestId,
                    'error' => 'Translation timed out. The document may be too large or complex. Try a smaller file or simpler content, and we will try again.',
                    'retryable' => true,
                ], 504);
            }

            if (str_contains($message, 'Could not connect')) {
                return response()->json([
                    'request_id' => $requestId,
                    'error' => 'The translation service is temporarily unavailable. Please try again in a moment or contact support if the issue persists.',
                    'retryable' => true,
                ], 503);
            }

            if ($code === 400) {
                return response()->json(['error' => $message, 'request_id' => $requestId], 400);
            }

            return response()->json([
                'request_id' => $requestId,
                'error' => $message ?: 'Translation failed. Please try again or contact support if the problem persists.',
                'retryable' => true,
            ], $code);
        } catch (\Throwable $e) {
            Log::error('Unexpected error in translation controller', [
                'request_id' => $requestId,
                'stage' => $request->attributes->get('translation_stage'),
                'exception_class' => $e::class,
                'exception' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
                'user_id' => Auth::id(),
            ]);

            return response()->json([
                'request_id' => $requestId,
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
        $request->attributes->set('translation_stage', 'document_intake');
        $userId = Auth::id();

        $originalName = SafeFileNames::scrubDisplayName($uploadedFile->getClientOriginalName());
        $originalExt = '.'.strtolower((string) pathinfo($originalName, PATHINFO_EXTENSION));
        $fileSize = (int) $uploadedFile->getSize();
        $mode = $validated['mode'] ?? 'balanced';

        // 1. Persist the uploaded file so the queue worker can read it later
        //    (PHP deletes the temp file when this request ends). The on-disk
        //    leaf is server-generated and opaque.
        $persistDir = storage_path('app/uploads/'.Str::uuid());
        if (! is_dir($persistDir)) {
            mkdir($persistDir, 0755, true);
        }
        $persistentPath = $persistDir.DIRECTORY_SEPARATOR.'source'.$originalExt;
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
        if (! $this->contentsMatchExtension($originalExt, $persistentPath)) {
            FileCleanup::dir($persistDir);

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
            FileCleanup::dir($persistDir);
            $payload = $this->buildCompletedPayload($completed);

            if ($payload !== null) {
                $payload['reused'] = true;

                return response()->json($payload);
            }
        }

        // 3b. If an identical job is still active, hand its job_id back.
        $existingActive = $this->findActiveJob($userId, $payloadHash);
        if ($existingActive !== null) {
            FileCleanup::dir($persistDir);

            return response()->json([
                'status' => 'processing',
                'duplicate' => true,
                'job_id' => $existingActive->uuid,
                'message' => 'A translation for this exact file is already in progress.',
            ], 200);
        }

        // 3c. Reserve the daily quota at ACCEPTANCE — the atomic conditional
        //     increment serializes per-user intake, so concurrent uploads cannot
        //     jointly exceed the cap. This runs only after reuse/dedup short
        //     circuits, so deduplicated work is never charged twice.
        $quotaDay = now()->toDateString();
        $request->attributes->set('translation_stage', 'quota_reservation');
        try {
            $reserved = $this->quota->reserve($userId, $fileSize, $quotaDay);
        } catch (\Throwable $e) {
            FileCleanup::dir($persistDir);
            throw $e;
        }
        if (! $reserved) {
            FileCleanup::dir($persistDir);

            return response()->json([
                'error' => 'You have reached the daily document upload limit. Please try again tomorrow or contact support.',
            ], 429);
        }

        // 4. Upload the ORIGINAL file to durable storage (opaque key). If all
        //    backends fail, translation can still proceed — the job will backfill.
        $originalStoragePath = null;
        $request->attributes->set('translation_stage', 'original_storage');
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

        // Acceptance boundary. The queued-state write and the queue insert must
        // share ONE commit: with the database driver and after_commit=false the
        // `jobs` INSERT joins this transaction, so a rollback leaves no queue
        // row and a commit leaves both. (deployment:validate-timeouts asserts
        // those preconditions and fails deployment otherwise.) After the
        // boundary the outcome is never assumed — it is classified by read-back.
        // The acceptance boundary is the pair (queued-state write, queue insert):
        // with the database driver and after_commit=false the `jobs` INSERT joins
        // this transaction, so a rollback leaves no receivable queue row and a
        // commit leaves both. deployment:validate-timeouts asserts those
        // preconditions and fails deployment otherwise. After the boundary the
        // outcome is never assumed — it is classified by read-back.
        //
        // The initial create() stays OUTSIDE this transaction on purpose. It is
        // not part of the acceptance decision, and keeping it outside means a
        // concurrent winner of the dedup race has already committed and is not
        // collateral damage of this request's rollback.
        $jobId = null;
        $jobRow = null;
        $dispatchAttempted = false;
        $request->attributes->set('translation_stage', 'job_acceptance');

        try {
            // The partial unique index is the final guard against a race between
            // two identical submissions.
            $jobRow = TranslationJob::create([
                'user_id' => $userId,
                'payload_hash' => $payloadHash,
                'original_name' => $originalName,
                'original_ext' => $originalExt,
                'source_lang' => $sourceLang,
                'target_lang' => $targetLang,
                'pdf_column_mode' => $pdfColumnMode,
                'mode' => $mode,
                'file_size' => $fileSize,
                'original_storage_path' => $originalStoragePath,
                'original_storage_backend' => $originalStorageBackend,
                'parent_document_id' => null,
                'status' => TranslationJob::STATUS_CREATED,
            ]);

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

            // Record the reference while still `created`, so a row that never
            // reaches `queued` is traceable to its job and compensable by
            // identity rather than by guessing.
            $jobRow->uuid = $jobId;
            $jobRow->save();

            DB::transaction(function () use ($jobRow, $job, &$dispatchAttempted) {
                $jobRow->status = TranslationJob::STATUS_QUEUED;
                $jobRow->progress = 5;
                $jobRow->last_heartbeat_at = now();
                $jobRow->save();

                $dispatchAttempted = true;
                dispatch($job);
            });
        } catch (QueryException $e) {
            // Race window (or a DB failure) during acceptance. Classify the real
            // outcome before touching quota or input: a lost dedup race is not
            // the same as a dispatch failure.
            FileCleanup::dir($persistDir);

            $authoritative = $this->reReadJobRow($jobRow, $jobId);
            $outcome = $this->dispatchOutcome->classify($authoritative, (string) $jobId, TranslationJob::STATUS_CREATED, dispatchAttempted: $dispatchAttempted);

            if ($outcome->isRejected()) {
                $this->quota->refund($userId, $fileSize, $quotaDay);
                $this->discardUnacceptedRow($jobRow, $jobId);

                // When the race was actually lost, return the winner instead of
                // an error.
                $winner = $this->findActiveJob($userId, $payloadHash);
                if ($winner !== null) {
                    return response()->json([
                        'status' => 'processing',
                        'duplicate' => true,
                        'job_id' => $winner->uuid,
                        'message' => 'A translation for this exact file is already in progress.',
                    ], 200);
                }
            }

            if (! $outcome->safeToCompensate) {
                Log::error('Failed to persist the translation job; enqueue outcome unresolved', [
                    'exception' => $e->getMessage(),
                    'user_id' => $userId,
                    'job_id' => $jobId,
                    'outcome' => $outcome->status,
                    'reason' => $outcome->reason,
                ]);

                return $this->unresolvedDispatchResponse($jobId);
            }

            Log::error('Failed to persist the translation job', [
                'exception' => $e->getMessage(),
                'user_id' => $userId,
                'reason' => $outcome->reason,
            ]);
            throw $e;
        } catch (\Throwable $e) {
            FileCleanup::dir($persistDir);

            $authoritative = $this->reReadJobRow($jobRow, $jobId);
            $outcome = $this->dispatchOutcome->classify($authoritative, (string) $jobId, TranslationJob::STATUS_CREATED, dispatchAttempted: $dispatchAttempted);

            Log::error('Failed to dispatch translation job', [
                'exception' => $e->getMessage(),
                'user_id' => $userId,
                'job_id' => $jobId,
                'outcome' => $outcome->status,
                'reason' => $outcome->reason,
            ]);

            if ($outcome->isUnknown()) {
                // Do not refund, do not delete the input: a worker may hold
                // this job. The scratch bytes and the reservation are retained
                // deliberately, and the stable job reference lets the user come
                // back to a truthful status.
                return $this->unresolvedDispatchResponse($jobId);
            }

            if ($outcome->safeToCompensate) {
                $this->quota->refund($userId, $fileSize, $quotaDay);
                $this->discardUnacceptedRow($jobRow, $jobId);
            }

            throw $e;
        }

        // A cache marker keeps very short polling windows working without
        // hammering translation_jobs; the DB row is authoritative.
        cache()->put(
            'translation_job_'.$jobId,
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
    }

    /**
     * Re-read the authoritative state row after a failed dispatch. The
     * in-memory model may describe a state the rollback already undid.
     */
    private function reReadJobRow(?TranslationJob $jobRow, ?string $jobId): ?TranslationJob
    {
        try {
            if ($jobRow !== null && $jobRow->exists) {
                return TranslationJob::find($jobRow->getKey());
            }

            if (filled($jobId)) {
                return TranslationJob::where('uuid', $jobId)->first();
            }
        } catch (\Throwable $e) {
            Log::warning('Could not re-read the translation_jobs row after a failed dispatch', [
                'job_id' => $jobId,
                'exception' => $e->getMessage(),
            ]);
        }

        return null;
    }

    /**
     * Remove a row that never became receivable work.
     *
     * The create() is committed before the acceptance transaction opens, so a
     * rejected dispatch leaves a durable `created` row behind. It has no queue
     * entry and no worker, so it is a leak unless it is removed. The state is
     * re-read first: a row that has since been picked up or completed belongs to
     * a worker, and deleting it would destroy live work.
     */
    private function discardUnacceptedRow(?TranslationJob $jobRow, ?string $jobId): void
    {
        try {
            $current = $this->reReadJobRow($jobRow, $jobId);

            if ($current === null) {
                return;
            }

            if (in_array($current->status, [
                TranslationJob::STATUS_PROCESSING,
                TranslationJob::STATUS_COMPLETED,
            ], true)) {
                Log::warning('Refusing to discard a translation_jobs row that a worker owns', [
                    'job_id' => $jobId,
                    'status' => $current->status,
                ]);

                return;
            }

            $current->delete();
        } catch (\Throwable $e) {
            // Leaving an orphan `created` row is recoverable via reconciliation;
            // failing the request here would hide the real outcome.
            Log::error('Could not discard the unaccepted translation_jobs row', [
                'job_id' => $jobId,
                'exception' => $e->getMessage(),
            ]);
        }
    }

    /**
     * The enqueue outcome is genuinely unresolved. Say so, keep the job
     * reference so the user can check back, and claim nothing.
     */
    private function unresolvedDispatchResponse(?string $jobId): JsonResponse
    {
        return response()->json([
            'status' => 'unavailable',
            'dispatch' => DispatchOutcome::UNKNOWN,
            'job_id' => $jobId,
            'message' => 'We could not confirm that your document was queued. Your upload has been kept — check this job reference again in a moment.',
        ], 503);
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

                // Completed but unresolvable (no persisted history): this is a
                // TERMINAL completion-integrity failure, never "still in progress".
                return response()->json([
                    'status' => 'failed',
                    'error' => 'The translation finished but its result could not be retrieved. Please retry the document or contact support.',
                    'recoverable' => $job->recoverable !== false,
                ]);
            }

            if ($job->status === TranslationJob::STATUS_CANCELLED) {
                return response()->json([
                    'status' => 'failed',
                    'error' => 'Translation cancelled.',
                    'recoverable' => false,
                ]);
            }

            if ($job->status === TranslationJob::STATUS_FAILED) {
                return response()->json([
                    'status' => 'failed',
                    'error' => $job->error ?: 'Translation failed. Please try again.',
                    'recoverable' => $job->recoverable ?? false,
                ]);
            }

            // created / queued / processing
            return response()->json([
                'status' => 'processing',
                'progress' => $job->progress ?? 0,
                'message' => 'Translation is still in progress...',
            ]);
        }

        // 2. Completed job leaves a user-scoped history row keyed by job_id.
        $owned = TranslationHistory::where('job_id', $jobId)
            ->where('user_id', $userId)
            ->exists();

        if ($owned) {
            $result = Cache::get('translation_job_'.$jobId);

            if ($result && isset($result['status']) && $result['status'] !== 'processing') {
                return response()->json($result);
            }

            $history = TranslationHistory::where('job_id', $jobId)
                ->where('user_id', $userId)
                ->first();

            if ($history && $history->storage_path) {
                return response()->json($this->buildHistoryCompletedPayload($history));
            }

            return response()->json([
                'status' => 'failed',
                'error' => 'The translated file was completed but is unavailable. Please retry or contact support.',
            ]);
        }

        // 3. No DB row yet — in-flight legacy job or unknown.
        $result = Cache::get('translation_job_'.$jobId);

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

    /**
     * @return array{languages: array<int, string>, text_max_chars: int,
     *   max_upload_kb: int, max_upload_bytes: int, formats: array<int, string>,
     *   accept: string, modes: array<int, string>, pdf_column_modes: array<int, string>}
     */
    private function capabilityContract(): array
    {
        $formats = array_values(config('translation.supported_formats', []));
        $maxUploadKb = (int) config('translation.max_upload_kb', 51200);

        return [
            'languages' => array_values(config('translation.languages', [])),
            'text_max_chars' => (int) config('translation.text_max_chars', 8000),
            'max_upload_kb' => $maxUploadKb,
            'max_upload_bytes' => $maxUploadKb * 1024,
            'formats' => $formats,
            'accept' => implode(',', array_map(static fn (string $format): string => '.'.$format, $formats)),
            'modes' => array_values(config('translation.modes', [])),
            'pdf_column_modes' => array_values(config('translation.pdf_column_modes', [])),
        ];
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

    private function buildHistoryCompletedPayload(TranslationHistory $history): array
    {
        return $this->downloadResolver->resolve($history);
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
        return ! str_contains(substr($head, 0, 4096), "\x00");
    }
}
