<?php

namespace App\Http\Controllers;

use App\Exceptions\TranslationException;
use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationHistory;
use App\Notifications\TranslationCompleted;
use App\Services\HistoryService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use App\Support\ReviewStatus;
use App\Support\ApiError;
use App\Services\Translation\DTO\TranslationRequest;
use App\Services\Translation\DTO\TranslationResponse;
use App\Services\TranslationService;
use Illuminate\Contracts\View\View;
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
    ) {}

    /**
     * GET /translate — render the translation page.
     */
    public function show(): View
    {
        return view('translation', ['preferences' => Auth::user()->resolvedPreferences()]);
    }

    /**
     * POST /translate — handle text or document translation.
     * Documents are dispatched to queue for async processing.
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
                'error' => ['code' => 'translation_input_required', 'message' => 'Please enter text to translate or attach a document.', 'retryable' => false],
                'errors' => [
                    'text' => ['The text field is required when document is not present.'],
                ]
            ], 422);
        }

        try {
            // Document mode — dispatch to queue for async processing
            if ($request->hasFile('document')) {
                $uploadedFile = $request->file('document');
                $originalName = $uploadedFile->getClientOriginalName();
                $originalExt  = strtolower('.' . $uploadedFile->getClientOriginalExtension());
                $fileSize     = $uploadedFile->getSize();

                // 1. Upload the ORIGINAL file to Supabase Storage
                $originalStoragePath = Auth::id() . '/originals/' . Str::uuid() . '_' . $originalName;

                try {
                    $this->storage->uploadFile(
                        $uploadedFile->getRealPath(),
                        $originalStoragePath
                    );
                } catch (\Throwable $e) {
                    Log::warning('Supabase Storage upload failed for original file (translation will still proceed)', [
                        'exception' => $e->getMessage(),
                        'storage_path' => $originalStoragePath,
                    ]);
                    // Mark the original as not stored — translation can still proceed
                    $originalStoragePath = null;
                }

                // 2. Persist the uploaded file so the queue worker can read it later.
                //    PHP deletes the temp file as soon as this request ends.
                $persistDir = storage_path('app/uploads/' . Str::uuid());
                if (!is_dir($persistDir)) {
                    mkdir($persistDir, 0755, true);
                }
                $persistentPath = $persistDir . DIRECTORY_SEPARATOR . $originalName;
                try {
                    $uploadedFile->move($persistDir, $originalName);
                } catch (\Throwable $e) {
                    Log::error('Failed to persist uploaded file for translation job', [
                        'exception' => $e->getMessage(),
                        'user_id' => Auth::id(),
                    ]);
                    throw new TranslationException(
                        'The uploaded file could not be stored for processing. Please try again.'
                    );
                }

                // 3. Dispatch job to queue
                // Get the UUID generated by the Dispatchable trait for cache key consistency
                $mode = $request->input('mode', 'balanced');

                // Dedup: identical in-flight submissions (double-click / retry)
                // are answered immediately instead of silently dropping a
                // second job that would leave its job_id polling into a void.
                $inflightKey = TranslateDocumentJob::inflightKey(
                    Auth::id(), $originalName, $fileSize,
                    $sourceLang, $targetLang,
                );
                if (($inflightJobId = Cache::get($inflightKey))) {
                    return response()->json([
                        'status' => 'processing',
                        'duplicate' => true,
                        'job_id' => $inflightJobId,
                        'message' => 'A translation for this file is already in progress.',
                    ], 200);
                }

                $job = new TranslateDocumentJob(
                    $originalName,
                    $originalExt,
                    $fileSize,
                    $sourceLang,
                    $targetLang,
                    $pdfColumnMode,
                    $persistentPath,
                    Auth::id(),
                    $originalStoragePath,
                    $mode
                );
                $jobId = $job->uuid();

                Cache::put($inflightKey, $jobId, now()->addMinutes(20));

                dispatch($job);

                // 4. Return job ID for polling
                return response()->json([
                    'job_id' => $jobId,
                    'status' => 'processing',
                    'message' => 'Document queued for translation. Processing will begin shortly.',
                    'original_filename' => $originalName,
                ]);
            }

            // Text mode — process synchronously (fast enough)
            $translationRequest = new TranslationRequest(
                text: $request->input('text'),
                sourceLang: $sourceLang,
                targetLang: $targetLang,
                mode: $validated['mode'] ?? 'balanced',
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
                    'quality_score'    => $result->qualityScore,
                ]);

                if ($record !== null) {
                    Auth::user()->notify(new TranslationCompleted($record));
                    \App\Support\AdminNotifier::awaitingReview($record, Auth::user()->name);
                }
            } catch (\Throwable $e) {
                Log::error('Failed to insert text translation history record', [
                    'exception'  => $e->getMessage(),
                    'user_id'    => Auth::id(),
                ]);
            }

            return response()->json($result->toArray());

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
                return ApiError::response('translation_timed_out', 'Translation timed out. Try a smaller file or simpler content.', 504, true);
            }

            if (str_contains($message, 'Could not connect')) {
                return ApiError::response('translation_service_unavailable', 'The translation service is temporarily unavailable. Please try again in a moment.', 503, true);
            }

            if ($code === 400) {
                return ApiError::response('translation_request_invalid', 'The translation request could not be processed. Check the selected languages and input, then try again.', 400, false);
            }

            return ApiError::response('translation_failed', 'Translation failed. Please try again.', max(400, min(599, (int) $code ?: 500)), true);
        } catch (\Throwable $e) {
            Log::error('Unexpected error in translation controller', [
                'exception' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
                'user_id' => Auth::id(),
            ]);

            return ApiError::response('translation_unexpected_error', 'An unexpected error occurred during translation. Please try again.', 500, true);
        }
    }

    /**
     * GET /translate/status/{job_id} — poll for document translation status.
     *
     * Auth-protected. Ownership is resolved in two ways:
     *   1. A completed job has a `translation_history` row (job_id column) —
     *      the row is user-scoped, so presence proves ownership.
     *   2. An in-flight job has no row yet, so the cache entry (stamped with
     *      the owner's user_id by the job) is only served to that same user.
     *
     * Anyone else gets a 404 (existence not leaked).
     */
    public function status(string $jobId): JsonResponse
    {
        $userId = Auth::id();

        // A completed document job leaves a user-scoped history row keyed by job_id.
        $owned = TranslationHistory::where('job_id', $jobId)
            ->where('user_id', $userId)
            ->exists();

        if ($owned) {
            $result = Cache::get('translation_job_' . $jobId);

            return response()->json($result ?: [
                'status' => 'processing',
                'message' => 'Translation is still in progress...',
            ]);
        }

        // No history row yet — job is in-flight or unknown. Only serve the
        // cache if it was stamped with the requesting user's id.
        $result = Cache::get('translation_job_' . $jobId);

        if (is_array($result) && isset($result['user_id']) && (int) $result['user_id'] === $userId) {
            return response()->json($result);
        }

        return ApiError::response('translation_job_not_found', 'Translation job not found or you do not have access to it.', 404, false);
    }

    private function buildInlineDownloadPayload(string $outputPath, string $downloadFilename): array
    {
        $contents = @file_get_contents($outputPath);
        $mimeType = mime_content_type($outputPath) ?: 'application/octet-stream';

        if ($contents === false || $contents === '') {
            return [
                'download_filename' => $downloadFilename,
                'download_data'     => '',
                'download_mime'     => $mimeType,
            ];
        }

        return [
            'download_filename' => $downloadFilename,
            'download_data'     => 'data:' . $mimeType . ';base64,' . base64_encode($contents),
            'download_mime'     => $mimeType,
        ];
    }

}
