<?php

namespace App\Http\Controllers;

use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Services\DispatchOutcome;
use App\Services\DispatchOutcomeClassifier;
use App\Services\FileCleanup;
use App\Services\HistoryService;
use App\Services\QuotaService;
use App\Services\StorageService;
use App\Services\Translation\CompletedDownloadResolver;
use Illuminate\Contracts\View\View;
use Illuminate\Database\QueryException;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Illuminate\Validation\Rule;

class DocumentsController extends Controller
{
    public function __construct(
        private HistoryService $history,
        private StorageService $storage,
        private QuotaService $quota,
        private DispatchOutcomeClassifier $dispatchOutcome,
        private CompletedDownloadResolver $downloadResolver,
    ) {}

    /**
     * GET /documents — render the My Documents page.
     *
     * Shows original documents with their translations grouped together.
     * Also includes standalone translations (those without a parent) for backward compatibility.
     */
    public function index(Request $request): View
    {
        try {
            // Paginated rather than capped: the old version read the newest
            // 200 rows and offered no way to reach anything older.
            $documents = $this->history->getDocumentsPaginated(
                (int) Auth::id(),
                (int) $request->integer('per_page', 24)
            );

            return view('my-documents', [
                'documents' => $documents,
                'langPairs' => $this->history->getDocumentLanguagePairs((int) Auth::id()),
                'error'     => false,
            ]);
        } catch (\Throwable $e) {
            Log::error('DocumentsController::index failed', [
                'user_id'   => Auth::id(),
                'exception'  => $e->getMessage(),
            ]);

            return view('my-documents', [
                'documents' => collect(),
                'langPairs' => [],
                'error'     => true,
            ]);
        }
    }

    /**
     * POST /documents/{id}/re-translate — translate an existing original to a
     * different target language.
     *
     * Reuses the stored original file (original_storage_path) and dispatches the
     * same async document job as a fresh upload, linking the new result to the
     * source record via parent_document_id. Returns a job_id for polling.
     */
    public function retranslate(Request $request, int $id): JsonResponse
    {
        $validated = $request->validate([
            'target_lang' => [
                'required',
                Rule::in(config('translation.languages', ['English', 'Cebuano', 'Filipino'])),
            ],
        ]);

        $record = TranslationHistory::find($id);

        if ($record === null) {
            return response()->json(['error' => 'Document not found.'], 404);
        }

        if ((int) $record->user_id !== Auth::id()) {
            return response()->json(['error' => 'Forbidden.'], 403);
        }

        if ($record->translation_type !== 'document') {
            return response()->json(['error' => 'Only document translations can be re-translated.'], 422);
        }

        if ((string) $record->source_language === (string) $validated['target_lang']) {
            return response()->json([
                'error' => 'The source language and target language must be different.',
            ], 422);
        }

        if (blank($record->original_storage_path)) {
            return response()->json([
                'error' => 'The original file is not available in storage, so this document cannot be re-translated. Please re-upload it instead.',
            ], 422);
        }

        $originalBackend = (string) ($record->original_storage_backend ?: StorageService::BACKEND_SUPABASE);

        // A stored path is not evidence that the object still exists. Without
        // this check a deleted original surfaced as an opaque 500 from read(),
        // inviting retries that can never succeed, instead of the re-upload
        // message the user actually needs. Storage uncertainty stays a 503:
        // an outage must not be reported as permanent data loss.
        $originalPresence = $this->originalAvailability($originalBackend, (string) $record->original_storage_path);

        if ($originalPresence === StorageService::PRESENCE_MISSING) {
            Log::error('DocumentsController::retranslate found the original is gone', [
                'id'              => $id,
                'storage_backend' => $originalBackend,
                'storage_path'    => $record->original_storage_path,
            ]);

            return response()->json([
                'error' => 'The original file is no longer available in storage, so this document cannot be re-translated. Please re-upload it instead.',
            ], 422);
        }

        if ($originalPresence === StorageService::PRESENCE_UNKNOWN) {
            Log::warning('DocumentsController::retranslate could not verify the original', [
                'id'              => $id,
                'storage_backend' => $originalBackend,
                'storage_path'    => $record->original_storage_path,
            ]);

            return response()->json([
                'error' => 'We could not verify that the original file is available right now. Please try again in a moment.',
            ], 503);
        }

        try {
            // Download the original file so the job can process it from disk.
            $originalBytes = $this->storage->read(
                $originalBackend,
                $record->original_storage_path,
            );

            $persistDir = storage_path('app/uploads/' . Str::uuid());
            if (!is_dir($persistDir)) {
                mkdir($persistDir, 0755, true);
            }
            $originalName = $record->original_filename ?? 'document.' . pathinfo($record->original_storage_path, PATHINFO_EXTENSION);
            $persistentPath = $persistDir . DIRECTORY_SEPARATOR . 'source.' . strtolower((string) pathinfo($originalName, PATHINFO_EXTENSION));
            file_put_contents($persistentPath, $originalBytes);

            $originalExt = strtolower('.' . pathinfo($originalName, PATHINFO_EXTENSION));
            $fileSize = (int) ((int) $record->file_size ?: strlen((string) $originalBytes));

            // Durable dedup: identical re-translation attempts collapse to the
            // existing active or completed result.
            $contentHash = hash_file('sha256', $persistentPath);
            $payloadHash = \App\Models\TranslationJob::payloadHash(
                (int) Auth::id(),
                $contentHash,
                (string) ($record->source_language ?? ''),
                (string) $validated['target_lang'],
                'balanced',
                $record->sidecar['pdf_column_mode'] ?? 'auto',
                (int) $record->id,
            );

            $completed = \App\Models\TranslationJob::where('user_id', Auth::id())
                ->where('payload_hash', $payloadHash)
                ->where('status', \App\Models\TranslationJob::STATUS_COMPLETED)
                ->orderByDesc('id')
                ->first();

            if ($completed !== null) {
                $history = \App\Models\TranslationHistory::find($completed->translation_history_id);
                if ($history !== null) {
                    FileCleanup::dir($persistDir);

                    return response()->json(array_merge([
                        'job_id' => $completed->uuid,
                        'reused' => true,
                    ], $this->downloadResolver->resolve($history)));
                }
            }

            $existingActive = \App\Models\TranslationJob::where('user_id', Auth::id())
                ->where('payload_hash', $payloadHash)
                ->whereIn('status', \App\Models\TranslationJob::ACTIVE_STATUSES)
                ->orderByDesc('id')
                ->first();

            if ($existingActive !== null) {
                FileCleanup::dir($persistDir);

                return response()->json([
                    'job_id' => $existingActive->uuid,
                    'status' => 'processing',
                    'duplicate' => true,
                    'message' => 'This re-translation is already in progress.',
                ]);
            }

            // Same daily quota as a fresh upload: re-translation consumes
            // provider/queue capacity too. Deduplicated work above is never
            // charged. A refused re-translation leaves nothing behind.
            $quotaDay = now()->toDateString();
            if (! $this->quota->reserve((int) Auth::id(), $fileSize, $quotaDay)) {
                FileCleanup::dir($persistDir);

                return response()->json([
                    'error' => 'You have reached the daily document upload limit. Please try again tomorrow or contact support.',
                ], 429);
            }

            // Same acceptance boundary as a fresh upload: the queued-state write
            // and the queue insert share ONE commit, and the outcome is then
            // classified by read-back rather than assumed. See
            // TranslationController::store for the full rationale.
            $jobRow = null;
            $jobId = null;
            $dispatchAttempted = false;

            try {
                $jobRow = TranslationJob::create([
                    'user_id'                => Auth::id(),
                    'payload_hash'           => $payloadHash,
                    'original_name'          => $originalName,
                    'original_ext'           => $originalExt,
                    'source_lang'            => (string) ($record->source_language ?? ''),
                    'target_lang'            => (string) $validated['target_lang'],
                    'pdf_column_mode'        => $record->sidecar['pdf_column_mode'] ?? 'auto',
                    'mode'                   => 'balanced',
                    'file_size'              => $fileSize,
                    'original_storage_path'  => $record->original_storage_path,
                    'original_storage_backend' => $record->original_storage_backend ?: 'supabase',
                    'parent_document_id'     => (int) $record->id,
                    'status'                 => TranslationJob::STATUS_CREATED,
                ]);

                $job = new TranslateDocumentJob(
                    $originalName,
                    $originalExt,
                    $fileSize,
                    (string) ($record->source_language ?? ''),
                    (string) $validated['target_lang'],
                    $record->sidecar['pdf_column_mode'] ?? 'auto',
                    $persistentPath,
                    Auth::id(),
                    $record->original_storage_path,
                    'balanced',
                    (int) $record->id,
                    $record->original_storage_backend ?: 'supabase',
                    (int) $jobRow->id,
                );
                $jobId = $job->uuid();

                // Record the reference while still `created`, so a row that
                // never reaches `queued` stays traceable to its job.
                $jobRow->uuid = $jobId;
                $jobRow->save();

                // Acceptance boundary: queued-state write + queue insert commit
                // together. The create() above stays outside so a concurrent
                // dedup winner is not rolled back by this request.
                DB::transaction(function () use ($jobRow, $job, &$dispatchAttempted) {
                    $jobRow->status = TranslationJob::STATUS_QUEUED;
                    $jobRow->progress = 5;
                    $jobRow->last_heartbeat_at = now();
                    $jobRow->save();

                    $dispatchAttempted = true;
                    dispatch($job);
                });
            } catch (\Throwable $e) {
                $outcome = $this->classifyRetranslateOutcome($jobRow, $jobId, $dispatchAttempted);

                Log::error('DocumentsController::retranslate failed', [
                    'id' => $id,
                    'exception' => $e->getMessage(),
                    'job_id' => $jobId,
                    'outcome' => $outcome->status,
                    'reason' => $outcome->reason,
                ]);

                // Unresolved: a worker may hold this job. Keep the scratch
                // bytes and the reservation, and hand back the reference.
                if ($outcome->isUnknown()) {
                    return response()->json([
                        'status' => 'unavailable',
                        'dispatch' => DispatchOutcome::UNKNOWN,
                        'job_id' => $jobId,
                        'message' => 'We could not confirm that the re-translation was queued. It has been kept — check this job reference again in a moment.',
                    ], 503);
                }

                FileCleanup::dir($persistDir);

                if ($outcome->safeToCompensate) {
                    $this->quota->refund((int) Auth::id(), $fileSize, $quotaDay);
                    $this->discardUnacceptedRow($jobRow, $jobId);
                }

                // Lost the race against an identical active re-translation —
                // return the winner instead of an error.
                $winner = \App\Models\TranslationJob::where('user_id', Auth::id())
                    ->where('payload_hash', $payloadHash)
                    ->whereIn('status', \App\Models\TranslationJob::ACTIVE_STATUSES)
                    ->orderByDesc('id')
                    ->first();

                if ($winner !== null) {
                    return response()->json([
                        'job_id' => $winner->uuid,
                        'status' => 'processing',
                        'duplicate' => true,
                        'message' => 'This re-translation is already in progress.',
                    ], 200);
                }

                return response()->json([
                    'error' => 'Unable to re-translate the document. Please try again later.',
                ], 500);
            }

            return response()->json([
                'job_id' => $jobId,
                'status' => 'processing',
                'message' => 'Re-translation queued. Processing will begin shortly.',
                'original_filename' => $originalName,
            ]);
        } catch (QueryException $e) {
            if (isset($persistDir)) {
                FileCleanup::dir($persistDir);
            }

            Log::error('DocumentsController::retranslate failed', [
                'id' => $id,
                'exception' => $e->getMessage(),
            ]);

            return response()->json([
                'error' => 'Unable to re-translate the document. Please try again later.',
            ], 500);
        } catch (\Throwable $e) {
            if (isset($persistDir)) {
                FileCleanup::dir($persistDir);
            }

            Log::error('DocumentsController::retranslate failed', [
                'id' => $id,
                'exception' => $e->getMessage(),
            ]);
            return response()->json([
                'error' => 'Unable to re-translate the document. Please try again later.',
            ], 500);
        }
    }

    /**
     * Backend-authoritative presence evidence for the record's original.
     *
     * Anything that prevents a verdict — including the probe itself throwing —
     * is PRESENCE_UNKNOWN, which the caller reports as a retryable outage and
     * never as a lost file.
     */
    private function originalAvailability(string $backend, string $storagePath): string
    {
        try {
            return $this->storage->exists($backend, $storagePath);
        } catch (\Throwable $e) {
            Log::warning('DocumentsController::retranslate could not establish storage presence', [
                'storage_backend' => $backend,
                'storage_path'    => $storagePath,
                'exception'       => $e->getMessage(),
            ]);

            return StorageService::PRESENCE_UNKNOWN;
        }
    }

    /**
     * Remove a row that never became receivable work. The create() commits
     * before the acceptance transaction opens, so a rejected dispatch leaves a
     * durable `created` row with no queue entry and no worker. The state is
     * re-read first: a row a worker now owns is live work, not a leak.
     */
    private function discardUnacceptedRow(?TranslationJob $jobRow, ?string $jobId): void
    {
        try {
            $current = null;

            if ($jobRow !== null && $jobRow->exists) {
                $current = TranslationJob::find($jobRow->getKey());
            } elseif (filled($jobId)) {
                $current = TranslationJob::where('uuid', $jobId)->first();
            }

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
            Log::error('Could not discard the unaccepted translation_jobs row', [
                'job_id' => $jobId,
                'exception' => $e->getMessage(),
            ]);
        }
    }

    /**
     * Classify what actually happened to a failed re-translation dispatch.
     * The in-memory row may describe a state the rollback already undid, so it
     * is re-read before the decision.
     */
    private function classifyRetranslateOutcome(?TranslationJob $jobRow, ?string $jobId, bool $dispatchAttempted = true): DispatchOutcome
    {
        $authoritative = null;

        try {
            if ($jobRow !== null && $jobRow->exists) {
                $authoritative = TranslationJob::find($jobRow->getKey());
            } elseif (filled($jobId)) {
                $authoritative = TranslationJob::where('uuid', $jobId)->first();
            }
        } catch (\Throwable $e) {
            return new DispatchOutcome(
                DispatchOutcome::UNKNOWN,
                'The re-translation enqueue outcome could not be read back: '.$e->getMessage(),
                false,
            );
        }

        return $this->dispatchOutcome->classify($authoritative, (string) $jobId, TranslationJob::STATUS_CREATED, dispatchAttempted: $dispatchAttempted);
    }

}
