<?php

namespace App\Http\Controllers;

use App\Models\TranslationHistory;
use App\Services\HistoryService;
use App\Services\StorageCleanupService;
use App\Services\StorageService;
use App\Support\SafeFileNames;
use Illuminate\Contracts\View\View;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Symfony\Component\HttpFoundation\StreamedResponse;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class HistoryController extends Controller
{
    public function __construct(
        private HistoryService $history,
        private StorageService $storage,
        private StorageCleanupService $cleanup,
    ) {}

    /**
     * GET /history — render the translation history page.
     *
     * Fetches all history records for the current user and renders the
     * history view. On database error, logs the exception and renders the
     * error view with an empty records array.
     */
    public function index(Request $request): View
    {
        try {
            $records = $this->history->getHistoryPaginated(Auth::id(), 50);
            $records->withPath(route('history'));

            return view('history', [
                'records'    => $records,
                'error'      => false,
                'openId'     => $request->integer('open') ?: null,
            ]);
        } catch (\Throwable $e) {
            Log::error('HistoryController::index failed to load history', [
                'user_id'   => Auth::id(),
                'exception' => $e->getMessage(),
            ]);

            return view('history', [
                'records' => collect(),
                'error'   => true,
            ]);
        }
    }

    /**
     * GET /history/{id}/view — render the dedicated translation detail page.
     *
     * Two-pane layout: document viewer (right) + metadata/actions (left).
     * Ownership is enforced before rendering.
     */
    public function view(Request $request, int $id): View
    {
        try {
            $record = $this->history->getRecordWithTranslations($id);
        } catch (\Throwable $e) {
            Log::error('HistoryController::view failed', [
                'id' => $id,
                'exception' => $e->getMessage(),
            ]);
            abort(500, 'Unable to load translation details.');
        }

        if ($record === null) {
            abort(404, 'Record not found.');
        }

        if ((int) $record['user_id'] !== (int) Auth::id()) {
            abort(403, 'Forbidden.');
        }

        return view('history-detail', [
            'record' => $record,
        ]);
    }

    /**
     * GET /history/{id}/file — stream the translated file inline (ownership-checked).
     */
    public function showFile(int $id): StreamedResponse
    {
        $record = $this->history->getRecord($id);

        if ($record === null) {
            abort(404, 'Record not found.');
        }

        if ((int) $record['user_id'] !== (int) Auth::id()) {
            abort(403, 'Forbidden.');
        }

        if (($record['translation_type'] ?? 'document') !== 'document' || blank($record['storage_path'])) {
            abort(404, 'Translated file not found.');
        }

        $filename = $record['translated_filename'] ?: 'translation.pdf';
        $ext      = strtolower((string) pathinfo((string) $filename, PATHINFO_EXTENSION));
        $backend  = $record['storage_backend'] ?? StorageService::BACKEND_SUPABASE;

        try {
            $bytes = $this->storage->read($backend, $record['storage_path']);
        } catch (\Throwable $e) {
            Log::error('HistoryController::showFile failed', [
                'storage_path' => $record['storage_path'],
                'backend'      => $backend,
                'exception'    => $e->getMessage(),
            ]);
            abort(404, 'Translated file not found.');
        }

        return $this->streamFile($bytes, $filename, $ext);
    }

    /**
     * GET /history/{id}/original-file — stream the original file inline (ownership-checked).
     */
    public function showOriginalFile(int $id): StreamedResponse
    {
        $record = $this->history->getRecord($id);

        if ($record === null) {
            abort(404, 'Record not found.');
        }

        if ((int) $record['user_id'] !== (int) Auth::id()) {
            abort(403, 'Forbidden.');
        }

        if (($record['translation_type'] ?? 'document') !== 'document' || blank($record['original_storage_path'])) {
            abort(404, 'Original file not found.');
        }

        $filename = $record['original_filename'] ?: 'original.pdf';
        $ext      = strtolower((string) pathinfo((string) $filename, PATHINFO_EXTENSION));
        $backend  = $record['original_storage_backend'] ?? StorageService::BACKEND_SUPABASE;

        try {
            $bytes = $this->storage->read($backend, $record['original_storage_path']);
        } catch (\Throwable $e) {
            Log::error('HistoryController::showOriginalFile failed', [
                'storage_path' => $record['original_storage_path'],
                'backend'      => $backend,
                'exception'    => $e->getMessage(),
            ]);
            abort(404, 'Original file not found.');
        }

        return $this->streamFile($bytes, $filename, $ext);
    }

    /**
     * GET /history/{id}/blocks — return the ordered block content for a
     * document translation (ownership-checked).
     *
     * Used as the lazy source for the "render from blocks" preview fallback,
     * so the history detail page never has to embed every block on load.
     */
            public function blocks(int $id): JsonResponse
    {
        try {
            $record = $this->history->getRecord($id);
        } catch (\Throwable $e) {
            Log::error('HistoryController::blocks failed', [
                'id' => $id,
                'exception' => $e->getMessage(),
            ]);
            return response()->json(['error' => 'Unable to load block content.'], 500);
        }

        if ($record === null) {
            return response()->json(['error' => 'Record not found.'], 404);
        }

        if ((int) $record['user_id'] !== Auth::id()) {
            return response()->json(['error' => 'Forbidden.'], 403);
        }

        // Owner-facing "Final/Saved" block endpoint: expose PUBLISHED content only.
        // Unpublished draft current_text is never disclosed here, so a preview can
        // never be labelled Final/Saved while it actually shows draft wording.
        $rows = \App\Models\TranslationBlock::where('translation_history_id', $id)
            ->orderBy('block_index')
            ->get(['id', 'block_index', 'block_type', 'source_text', 'published_text', 'ai_translated_text']);

        $blocks = $rows->map(fn ($b) => [
            'id' => $b->id,
            'block_index' => $b->block_index,
            'block_type' => $b->block_type,
            'source_text' => $b->source_text,
            'published_text' => $b->published_text,
            'has_published' => $b->published_text !== null,
            'ai_translated_text' => $b->ai_translated_text,
        ]);

        return response()->json(['blocks' => $blocks]);
    }
private function streamFile(string $bytes, string $filename, string $ext): StreamedResponse
    {
        $mime = $this->mimeForExtension($ext);
        if ($mime === 'application/octet-stream' && function_exists('finfo_open')) {
            $finfo = new \finfo(FILEINFO_MIME_TYPE);
            $sniffed = $finfo->buffer($bytes);
            if (is_string($sniffed) && $sniffed !== '' && $sniffed !== 'application/octet-stream') {
                $mime = $sniffed;
            }
        }

        return new StreamedResponse(function () use ($bytes) {
            echo $bytes;
        }, 200, [
            'Content-Type'        => $mime,
            'Content-Disposition' => SafeFileNames::contentDisposition($filename),
            'Cache-Control'       => 'private, max-age=60',
        ]);
    }

    /**
     * Best-effort MIME lookup.
     */
    private function mimeForExtension(string $ext): string
    {
        return match ($ext) {
            'pdf'    => 'application/pdf',
            'docx'   => 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xlsx'   => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'pptx'   => 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'txt', 'md' => 'text/plain',
            'csv'    => 'text/csv',
            'rtf'    => 'application/rtf',
            'odt'    => 'application/vnd.oasis.opendocument.text',
            default  => 'application/octet-stream',
        };
    }

    /**
     * GET /history/{id} — return full metadata for a translation record (for the details modal).
     */
    public function detail(Request $request, int $id): JsonResponse
    {
        try {
            $record = $this->history->getRecordWithTranslations($id);
        } catch (\Throwable $e) {
            Log::error('HistoryController::detail failed', [
                'id' => $id,
                'exception' => $e->getMessage(),
            ]);
            return response()->json(['error' => 'Unable to load translation details.'], 500);
        }

        if ($record === null) {
            return response()->json(['error' => 'Record not found.'], 404);
        }

        if ((int) $record['user_id'] !== Auth::id()) {
            return response()->json(['error' => 'Forbidden.'], 403);
        }

        return response()->json($record);
    }

    /**
     * POST /history/redownload/{id} — generate a new signed URL for a past translation.
     *
     * Validates user ownership, generates a fresh signed URL via StorageService,
     * updates the expiry in the database, and returns the new download URL as JSON.
     */
    public function redownload(Request $request, int $id): JsonResponse
    {
        // 1. Fetch the record; return 404 if not found
        try {
            $record = $this->history->getRecord($id);
        } catch (\Throwable $e) {
            Log::error('HistoryController::redownload failed to fetch record', [
                'id'        => $id,
                'exception' => $e->getMessage(),
            ]);

            return response()->json(
                ['error' => 'Unable to generate download link. Please try again later.'],
                500
            );
        }

        if ($record === null) {
            return response()->json(
                ['error' => 'This file is no longer available.'],
                404
            );
        }

        // 2. Enforce user ownership — return 403 without revealing record existence
        if ((int) $record['user_id'] !== Auth::id()) {
            return response()->json(
                ['error' => 'Forbidden.'],
                403
            );
        }

        // 3. Durable-fallback files are served by the app's streaming route.
        $backend = $record['storage_backend'] ?? StorageService::BACKEND_SUPABASE;
        if ($backend === StorageService::BACKEND_LOCAL) {
            return response()->json([
                'download_url'      => route('history.file', ['id' => $id]),
                'download_filename' => $record['translated_filename'],
            ], 200);
        }

        // 4. Ask the backend whether the object is really gone before
        //    promising a permanent 404. See availabilityEvidence().
        if ($this->availabilityEvidence($backend, (string) $record['storage_path'])
            === StorageService::PRESENCE_MISSING) {
            Log::error('HistoryController::redownload confirmed the object is gone', [
                'id'              => $id,
                'storage_backend' => $backend,
                'storage_path'    => $record['storage_path'],
            ]);

            return response()->json(
                ['error' => 'This file is no longer available.'],
                404
            );
        }

        // 5. Generate a new signed URL via StorageService. A failure here is
        //    never treated as proof of loss: the object is either present or
        //    unverified, and in both cases the user can simply retry.
        try {
            $storageResult = $this->storage->generateSignedUrl($record['storage_path']);
        } catch (\Throwable $e) {
            Log::error('HistoryController::redownload failed to generate signed URL', [
                'id'              => $id,
                'exception'       => $e->getMessage(),
                'storage_backend' => $backend,
            ]);

            return response()->json(
                ['error' => 'Unable to generate download link. Please try again later.'],
                500
            );
        }

        // 6. Update the expiry timestamp in the database
        try {
            $this->history->updateExpiry($id, $storageResult['signed_url_expires_at']);
        } catch (\Throwable $e) {
            // Log but do not block the response — the user still gets their download URL
            Log::error('HistoryController::redownload failed to update expiry', [
                'id'        => $id,
                'exception' => $e->getMessage(),
            ]);
        }

        // 7. Return the new download URL
        return response()->json([
            'download_url' => $storageResult['signed_url'],
        ], 200);
    }

    /**
     * POST /history/redownload-original/{id} — generate a new signed URL for the ORIGINAL document.
     */
    public function redownloadOriginal(Request $request, int $id): JsonResponse
    {
        try {
            $record = $this->history->getRecord($id);
        } catch (\Throwable $e) {
            Log::error('HistoryController::redownloadOriginal failed to fetch record', [
                'id' => $id,
                'exception' => $e->getMessage(),
            ]);
            return response()->json(
                ['error' => 'Unable to generate download link. Please try again later.'],
                500
            );
        }

        if ($record === null) {
            return response()->json(['error' => 'This file is no longer available.'], 404);
        }

        if ((int) $record['user_id'] !== Auth::id()) {
            return response()->json(['error' => 'Forbidden.'], 403);
        }

        if (empty($record['original_storage_path'])) {
            return response()->json(['error' => 'Original document is not available.'], 404);
        }

        $backend = $record['original_storage_backend'] ?? StorageService::BACKEND_SUPABASE;
        if ($backend === StorageService::BACKEND_LOCAL) {
            return response()->json([
                'download_url'      => route('history.original-file', ['id' => $id]),
                'download_filename' => $record['original_filename'],
            ], 200);
        }

        if ($this->availabilityEvidence($backend, (string) $record['original_storage_path'])
            === StorageService::PRESENCE_MISSING) {
            Log::error('HistoryController::redownloadOriginal confirmed the object is gone', [
                'id'              => $id,
                'storage_backend' => $backend,
                'storage_path'    => $record['original_storage_path'],
            ]);

            return response()->json(
                ['error' => 'Original document is no longer available.'],
                404
            );
        }

        try {
            $storageResult = $this->storage->generateSignedUrl($record['original_storage_path']);
        } catch (\Throwable $e) {
            Log::error('HistoryController::redownloadOriginal failed to generate signed URL', [
                'id'              => $id,
                'exception'       => $e->getMessage(),
                'storage_backend' => $backend,
            ]);
            return response()->json(
                ['error' => 'Unable to generate download link. Please try again later.'],
                500
            );
        }

        return response()->json([
            'download_url' => $storageResult['signed_url'],
        ], 200);
    }

    /**
     * Backend-authoritative evidence that a stored object is still there.
     *
     * The two redownload routes previously decided between "this file is gone"
     * (404) and "try again later" (500) by searching the thrown exception's
     * message for the substring "not found". Exception text is not an API, and
     * the substring matched both real and false cases:
     *
     *   - A DNS, TLS or gateway outage whose message contains "not found"
     *     (for example "Host not found") was reported as permanent loss, and
     *     the user was told a file that still existed could never be recovered.
     *   - A genuinely deleted object reported as "NoSuchKey", or hidden behind
     *     a 403 on the private bucket, was reported as transient, so the user
     *     retried a deleted file forever and was never offered a re-upload.
     *
     * Only the backend can answer this question, so the verdict comes from
     * StorageService::exists(), which distinguishes a proven 404 from a network
     * or authorisation outage. A failure to obtain evidence is itself
     * PRESENCE_UNKNOWN, which callers must never read as loss.
     */
    private function availabilityEvidence(string $backend, string $storagePath): string
    {
        try {
            return $this->storage->exists($backend, $storagePath);
        } catch (\Throwable $e) {
            Log::warning('HistoryController could not establish storage presence', [
                'storage_backend' => $backend,
                'storage_path'    => $storagePath,
                'exception'       => $e->getMessage(),
            ]);

            return StorageService::PRESENCE_UNKNOWN;
        }
    }

    /**
     * POST /history/{id}/rename — rename a record's display filename.
     *
     * The stored file (storage_path) is untouched — only the display name on
     * the record is changed. The file extension is preserved.
     */
    public function rename(Request $request, int $id): JsonResponse
    {
        try {
            $record = $this->history->getRecord($id);
        } catch (\Throwable $e) {
            Log::error('HistoryController::rename failed to fetch record', [
                'id' => $id,
                'exception' => $e->getMessage(),
            ]);
            return response()->json(
                ['error' => 'Unable to rename the document. Please try again later.'],
                500
            );
        }

        if ($record === null) {
            return response()->json(['error' => 'Record not found.'], 404);
        }

        if ((int) $record['user_id'] !== Auth::id()) {
            return response()->json(['error' => 'Forbidden.'], 403);
        }

        $validated = $request->validate([
            'name' => ['required', 'string', 'max:255'],
        ]);

        $column = blank($record['translated_filename'] ?? null) ? 'original_filename' : 'translated_filename';
        $ext    = strtolower((string) pathinfo((string) $record[$column], PATHINFO_EXTENSION));

        // Clean the name and preserve the file extension.
        $newName = trim((string) $validated['name']);
        $newName = str_replace(['/', '\\'], '', $newName);
        if ($ext !== '' && strtolower((string) pathinfo($newName, PATHINFO_EXTENSION)) === '') {
            $newName .= '.' . $ext;
        }
        if ($ext !== '' && strtolower((string) pathinfo($newName, PATHINFO_EXTENSION)) !== $ext) {
            return response()->json(
                ['error' => "The file extension must remain .{$ext}."],
                422
            );
        }

        $result = $this->history->renameRecord($id, Auth::id(), $newName);

        if (!$result['renamed']) {
            return response()->json(['error' => 'Record not found or access denied.'], 404);
        }

        return response()->json(['success' => true, 'record' => $result['record']]);
    }

    /**
     * POST /history/{id}/bookmark — toggle whether the record is bookmarked.
     *
     * Persisted so the dedicated Bookmarked page can list everything a user
     * saved for later. Ownership is enforced before any state changes.
     */
    public function toggleBookmark(Request $request, int $id): JsonResponse
    {
        $toggled = $this->toggleFlag($id, 'is_bookmarked', 'bookmarked_at');

        return response()->json($toggled);
    }

    /**
     * POST /history/{id}/priority — toggle the "priority for review" flag.
     *
     * Lets a user ping a pending translation so admins can pick up the most
     * urgent items first. Ownership is enforced before any state changes.
     */
    public function togglePriority(Request $request, int $id): JsonResponse
    {
        $toggled = $this->toggleFlag($id, 'is_priority', 'priority_at');

        return response()->json($toggled);
    }

    /**
     * Toggle a boolean flag column with its paired timestamp on an owned record.
     *
     * @return array{success: bool, flag: string, value: bool, error?: string}
     */
    private function toggleFlag(int $id, string $column, string $timestampColumn): array
    {
        try {
            $record = $this->history->getRecord($id);
        } catch (\Throwable $e) {
            Log::error('HistoryController::toggleFlag failed to fetch record', [
                'id' => $id,
                'exception' => $e->getMessage(),
            ]);
            return ['success' => false, 'flag' => $column, 'value' => false, 'error' => 'Unable to update. Please try again later.'];
        }

        if ($record === null) {
            return ['success' => false, 'flag' => $column, 'value' => false, 'error' => 'Record not found.'];
        }

        if ((int) $record['user_id'] !== Auth::id()) {
            return ['success' => false, 'flag' => $column, 'value' => false, 'error' => 'Forbidden.'];
        }

        $value = !(bool) ($record[$column] ?? false);

        TranslationHistory::where('id', $id)->update([
            $column           => DB::raw($value ? 'true' : 'false'),
            $timestampColumn  => $value ? now() : null,
        ]);

        if ($column === 'is_priority' && $value) {
            $record = TranslationHistory::find($id);
            if ($record !== null) {
                \App\Support\AdminNotifier::priorityRequestRaised($record, Auth::user()->name);
            }
        }

        return ['success' => true, 'flag' => $column, 'value' => $value];
    }

    /**
     * DELETE /history/{id} — delete a translation record and its files.
     *
     * Rows and the durable cleanup list are committed together by deleteRecord.
     * Objects are then attempted immediately (best-effort); whatever survives
     * a backend outage stays pending in the outbox and the scheduled
     * translations:cleanup-storage command retries it — user data is never
     * silently orphaned.
     */
    public function destroy(Request $request, int $id): JsonResponse
    {
        try {
            $result = $this->history->deleteRecord($id, Auth::id());
        } catch (\Throwable $e) {
            Log::error('HistoryController::destroy failed', [
                'id' => $id,
                'exception' => $e->getMessage(),
            ]);
            return response()->json(['error' => 'Failed to delete translation. Please try again.'], 500);
        }

        if (! $result['deleted']) {
            return response()->json(['error' => 'Record not found or access denied.'], 404);
        }

        // Best-effort immediate pass; failures remain pending for the scheduled
        // command, so the request response never depends on storage health.
        try {
            $this->cleanup->processPending(count($result['storage_entries']) ?: 50);
        } catch (\Throwable $e) {
            Log::warning('HistoryController::destroy immediate cleanup failed', [
                'id' => $id,
                'exception' => $e->getMessage(),
            ]);
        }

        return response()->json(['success' => true]);
    }
}