<?php

namespace App\Http\Controllers\Admin;

use App\Exceptions\ReviewConflictException;
use App\Exceptions\TranslationException;
use App\Http\Controllers\Controller;
use App\Models\TranslationHistory;
use App\Services\Admin\ReviewService;
use App\Services\StorageService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;

use Symfony\Component\HttpFoundation\StreamedResponse;

/**
 * Admin write actions for DOCUMENT translations (block-level).
 *
 * All state changes go through Admin\ReviewService - this controller never
 * writes to translation_blocks, translation_history, or translation_edit_log
 * directly. ai_translated_text is immutable: edits always target current_text
 * and the previous value is audited first.
 */
class DocumentReviewController extends Controller
{
    public function __construct(
        private ReviewService $review,
        private StorageService $storage,
    ) {}

    private function wrap(callable $fn, string $context): JsonResponse
    {
        try {
            return response()->json($fn());
        } catch (TranslationException $e) {
            Log::error("DocumentReviewController::{$context} failed", [
                'exception' => $e->getMessage(),
            ]);
            return response()->json(['error' => $e->getMessage()], 422);
        } catch (\InvalidArgumentException $e) {
            // findHistory/findBlock and flag-reason guards are client-input
            // errors, not server faults; surface them as 422.
            Log::info("DocumentReviewController::{$context} rejected input", [
                'exception' => $e->getMessage(),
            ]);
            return response()->json(['error' => $e->getMessage()], 422);
        } catch (ReviewConflictException $e) {
            Log::info("DocumentReviewController::{$context} conflict", [
                'exception' => $e->getMessage(),
            ]);
            return response()->json(['error' => $e->getMessage()], 409);
        } catch (\Throwable $e) {
            Log::error("DocumentReviewController::{$context} failed", [
                'exception' => $e->getMessage(),
            ]);
            return response()->json(['error' => $e->getMessage()], 500);
        }
    }

    /**
     * POST /admin/review/{translation}/verify-document - mark the whole document
     * verified and cascade every block to verified.
     */
    public function verifyDocument(Request $request, TranslationHistory $translation): JsonResponse
    {
        return $this->wrap(fn () => [
            'success' => true,
            'status' => $this->review->verifyDocument($translation->id, Auth::id())->review_status,
        ], 'verifyDocument');
    }

    /**
     * POST /admin/review/{translation}/blocks/{block}/update - edit current_text.
     *
     * Draft editing is protected against stale submissions: the client must send
     * the draft_revision it rendered (expected_draft_revision). If the revision
     * has moved (another admin edited), the write is refused with HTTP 409 and
     * no draft text is overwritten.
     */
    public function updateBlock(Request $request, TranslationHistory $translation, int $block): JsonResponse
    {
        $validated = $request->validate([
            'current_text' => ['required', 'string'],
            'note' => ['nullable', 'string', 'max:2000'],
            'expected_draft_revision' => ['required', 'integer'],
        ]);

        return $this->wrap(fn () => [
            'success' => true,
            'status' => $this->review->updateBlock(
                $translation->id,
                $block,
                Auth::id(),
                $validated['current_text'],
                $validated['note'] ?? null,
                (int) $validated['expected_draft_revision'],
            )->status,
            'draft' => true,
            'message' => 'Saved as a draft. The download still shows the last published version - use Save & Regenerate to publish it.',
        ], 'updateBlock');
    }

    /**
     * POST /admin/review/{translation}/flag-document - mark the whole document
     * flagged and cascade every block to flagged with the same reason/note.
     */
    public function flagDocument(Request $request, TranslationHistory $translation): JsonResponse
    {
        $validated = $request->validate([
            'reason' => ['required', 'string', 'in:' . implode(',', \App\Support\FlagReason::ALL)],
            'note' => ['nullable', 'string', 'max:2000'],
        ]);

        return $this->wrap(fn () => [
            'success' => true,
            'status' => $this->review->flagDocument(
                $translation->id,
                Auth::id(),
                $validated['reason'],
                $validated['note'] ?? null,
            )->review_status,
        ], 'flagDocument');
    }

    /**
     * POST /admin/review/{translation}/save-regenerate - publish the current
     * block draft as a new downloadable file and return download links for the
     * new + original version.
     *
     * Accepts optional `blocks` ({block_id: new_text}) so on-screen edits that
     * were not individually "Save Edit"-ted are persisted through the audited
     * path before the document is re-rendered. Publication is protected against
     * concurrency: the client must send the draft_revision (expected_draft_revision)
     * and the currently published pointer (expected_storage_path) it rendered; if
     * either moved, the candidate is discarded and the request returns HTTP 409.
     */
    public function saveAndRegenerate(Request $request, TranslationHistory $translation): JsonResponse
    {
        $validated = $request->validate([
            'note' => ['nullable', 'string', 'max:2000'],
            'blocks' => ['sometimes', 'array'],
            'blocks.*' => ['string'],
            'expected_draft_revision' => ['required', 'integer'],
            // Empty renders as null (ConvertEmptyStringsToNull): a record with no
            // published pointer yet legitimately carries no pointer to protect.
            'expected_storage_path' => ['nullable', 'string'],
        ]);

        return $this->wrap(function () use ($validated, $translation) {
            $result = $this->review->saveAndRegenerate(
                $translation->id,
                Auth::id(),
                $validated['blocks'] ?? [],
                $validated['note'] ?? null,
                (int) $validated['expected_draft_revision'],
                $validated['expected_storage_path'] ?? null,
            );

            $history = $result['history'];
            $originalUrl = $this->originalDownloadUrl($history);

            if ($result['storage_backend'] === StorageService::BACKEND_LOCAL) {
                // Local objects are streamed through the authenticated admin
                // route (backend-aware read); there is no object URL to sign.
                $newUrl = route('admin.review.document.file', $history->id);
            } else {
                $newUrl = $result['signed_url'];
            }

            return [
                'success' => true,
                'new_download_url' => $newUrl,
                'new_download_filename' => $result['download_filename'],
                'storage_backend' => $result['storage_backend'],
                'original_download_url' => $originalUrl,
                'edited_blocks' => $result['edited_blocks'],
                'draft' => $result['draft'],
                'published' => $result['published'],
                'message' => 'New version published and is now the downloadable file. The superseded file has been scheduled for removal and is no longer downloadable.',
            ];
        }, 'saveAndRegenerate');
    }

    /**
     * Download link for the ORIGINAL file, backend-aware: signed URL for
     * Supabase objects, the authenticated streaming route for local fallback.
     */
    private function originalDownloadUrl(TranslationHistory $history): ?string
    {
        if (blank($history->original_storage_path)) {
            return null;
        }

        $backend = $history->original_storage_backend ?: StorageService::BACKEND_SUPABASE;

        if ($backend === StorageService::BACKEND_LOCAL) {
            return route('admin.review.original-file', $history->id);
        }

        try {
            return $this->storage->generateSignedUrl($history->original_storage_path)['signed_url'] ?? null;
        } catch (\Throwable $e) {
            Log::warning('DocumentReviewController could not sign original file', [
                'path' => $history->original_storage_path,
                'exception' => $e->getMessage(),
            ]);
            return null;
        }
    }

    /**
     * GET /admin/review/{translation}/original-file - stream the ORIGINAL
     * source bytes (backend-aware) so a local-fallback original still has an
     * admin preview/download link.
     */
    public function showOriginalFile(TranslationHistory $translation): StreamedResponse
    {
        if ($translation->translation_type !== 'document' || blank($translation->original_storage_path)) {
            abort(404, 'Original file not found.');
        }

        $filename = $translation->original_filename ?: 'original';
        $ext      = strtolower((string) pathinfo($filename, PATHINFO_EXTENSION));

        try {
            $backend = $translation->original_storage_backend ?: StorageService::BACKEND_SUPABASE;
            $bytes = $this->storage->read($backend, $translation->original_storage_path);
        } catch (\Throwable $e) {
            Log::error('DocumentReviewController::showOriginalFile failed', [
                'original_storage_path' => $translation->original_storage_path,
                'exception' => $e->getMessage(),
            ]);
            abort(404, 'Original file not found.');
        }

        $mime = $this->mimeForExtension($ext);
        if ($mime === 'application/octet-stream' && function_exists('finfo_open')) {
            $finfo = new \finfo(FILEINFO_MIME_TYPE);
            $sniffed = $finfo->buffer((string) $bytes);
            if (is_string($sniffed) && $sniffed !== '' && $sniffed !== 'application/octet-stream') {
                $mime = $sniffed;
            }
        }

        return new StreamedResponse(function () use ($bytes) {
            echo $bytes;
        }, 200, [
            'Content-Type'        => $mime,
            'Content-Disposition' => 'inline; filename="' . $filename . '"',
            'Cache-Control'       => 'private, max-age=60',
        ]);
    }

    /**
     * GET /admin/review/{translation}/file - stream the translated file's bytes
     * with the correct Content-Type.
     *
     * Returns a same-origin copy of the Supabase object so the browser can read
     * it for client-side preview (PDF iframe, mammoth/SheetJS conversion)
     * without hitting CORS on the signed URL.
     */
    public function showTranslatedFile(TranslationHistory $translation): StreamedResponse
    {
        if ($translation->translation_type !== 'document' || blank($translation->storage_path)) {
            abort(404, 'Translated file not found.');
        }

        $filename = $translation->translated_filename ?: 'translation.pdf';
        $ext      = strtolower((string) pathinfo($filename, PATHINFO_EXTENSION));

        try {
            $backend = $translation->storage_backend ?: StorageService::BACKEND_SUPABASE;
            $bytes = $this->storage->read($backend, $translation->storage_path);
        } catch (\Throwable $e) {
            Log::error('DocumentReviewController::showTranslatedFile failed', [
                'storage_path' => $translation->storage_path,
                'exception' => $e->getMessage(),
            ]);
            abort(404, 'Translated file not found.');
        }

        // The storage_path is a Supabase bucket key, not a local filesystem
        // path - mime_content_type() would fail on it (it throws under
        // Laravel's handler). Detect from the filename extension first, which
        // is authoritative for every format we produce, and only fall back to
        // in-memory content sniffing for unknown extensions. Office formats are
        // ZIP archives, so finfo alone would misreport them as application/zip
        // - hence the extension-first order.
        $mime = $this->mimeForExtension($ext);
        if ($mime === 'application/octet-stream' && function_exists('finfo_open')) {
            $finfo = new \finfo(FILEINFO_MIME_TYPE);
            $sniffed = $finfo->buffer((string) $bytes);
            if (is_string($sniffed) && $sniffed !== '' && $sniffed !== 'application/octet-stream') {
                $mime = $sniffed;
            }
        }

        $response = new StreamedResponse(function () use ($bytes) {
            echo $bytes;
        }, 200, [
            'Content-Type'        => $mime,
            'Content-Disposition' => 'inline; filename="' . $filename . '"',
            'Cache-Control'       => 'private, max-age=60',
        ]);

        return $response;
    }

    /**
     * Best-effort MIME lookup, used when the storage path has no on-disk extension.
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
}