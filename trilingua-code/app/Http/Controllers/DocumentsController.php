<?php

namespace App\Http\Controllers;

use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationHistory;
use App\Services\HistoryService;
use App\Services\StorageService;
use Illuminate\Contracts\View\View;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Illuminate\Validation\Rule;

class DocumentsController extends Controller
{
    public function __construct(
        private HistoryService $history,
        private StorageService $storage,
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
            // Get originals with their translations
            $originalsWithTranslations = $this->history->getOriginalsWithTranslations(Auth::id());

            // Also get all document records for backward compatibility (includes translations without parent)
            $all = $this->history->getHistory(Auth::id());
            $documents = array_values(array_filter(
                $all,
                fn($r) => ($r['translation_type'] ?? 'document') === 'document'
            ));

            // Distinct language pairs present in the user's records, for the filter dropdown.
            $langPairs = collect($documents)
                ->filter(fn($r) => !empty($r['source_language']) && !empty($r['target_language']))
                ->map(fn($r) => $r['source_language'] . ' → ' . $r['target_language'])
                ->unique()
                ->sort()
                ->values();

            return view('my-documents', [
                'documents' => $documents,
                'originals' => $originalsWithTranslations,
                'langPairs' => $langPairs,
                'error'     => false,
            ]);
        } catch (\Throwable $e) {
            Log::error('DocumentsController::index failed', [
                'user_id'   => Auth::id(),
                'exception'  => $e->getMessage(),
            ]);

            return view('my-documents', [
                'documents' => [],
                'originals' => [],
                'langPairs' => collect(),
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

        try {
            // Download the original file so the job can process it from disk.
            $originalBytes = $this->storage->downloadFile($record->original_storage_path);

            $persistDir = storage_path('app/uploads/' . Str::uuid());
            if (!is_dir($persistDir)) {
                mkdir($persistDir, 0755, true);
            }
            $originalName = $record->original_filename ?? 'document.' . pathinfo($record->original_storage_path, PATHINFO_EXTENSION);
            $persistentPath = $persistDir . DIRECTORY_SEPARATOR . $originalName;
            file_put_contents($persistentPath, $originalBytes);

            $originalExt = strtolower('.' . pathinfo($originalName, PATHINFO_EXTENSION));

            $job = new TranslateDocumentJob(
                $originalName,
                $originalExt,
                (int) $record->file_size ?? strlen((string) $originalBytes),
                $record->source_language ?? '',
                $validated['target_lang'],
                $record->sidecar['pdf_column_mode'] ?? 'auto',
                $persistentPath,
                Auth::id(),
                $record->original_storage_path,
                'balanced',
                $record->id,
            );
            $jobId = $job->uuid();

            dispatch($job);

            return response()->json([
                'job_id' => $jobId,
                'status' => 'processing',
                'message' => 'Re-translation queued. Processing will begin shortly.',
                'original_filename' => $originalName,
            ]);
        } catch (\Throwable $e) {
            Log::error('DocumentsController::retranslate failed', [
                'id' => $id,
                'exception' => $e->getMessage(),
            ]);
            return response()->json([
                'error' => 'Unable to re-translate the document. Please try again later.',
            ], 500);
        }
    }
}
