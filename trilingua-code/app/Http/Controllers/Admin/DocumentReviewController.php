<?php

namespace App\Http\Controllers\Admin;

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
 * All state changes go through Admin\ReviewService — this controller never
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
        } catch (\Throwable $e) {
            Log::error("DocumentReviewController::{$context} failed", [
                'exception' => $e->getMessage(),
            ]);
            return response()->json(['error' => $e->getMessage()], 500);
        }
    }

    /**
     * POST /admin/review/{translation}/blocks/{block}/verify
     */
    public function verifyBlock(Request $request, TranslationHistory $translation, int $block): JsonResponse
    {
        return $this->wrap(fn () => [
            'success' => true,
            'status' => $this->review->verifyBlock($translation->id, $block, Auth::id())->status,
        ], 'verifyBlock');
    }

    /**
     * POST /admin/review/{translation}/blocks/{block}/update — edit current_text.
     */
    public function updateBlock(Request $request, TranslationHistory $translation, int $block): JsonResponse
    {
        $validated = $request->validate([
            'current_text' => ['required', 'string'],
            'note' => ['nullable', 'string', 'max:2000'],
        ]);

        return $this->wrap(fn () => [
            'success' => true,
            'status' => $this->review->updateBlock(
                $translation->id,
                $block,
                Auth::id(),
                $validated['current_text'],
                $validated['note'] ?? null,
            )->status,
        ], 'updateBlock');
    }

    /**
     * POST /admin/review/{translation}/blocks/{block}/flag
     */
    public function flagBlock(Request $request, TranslationHistory $translation, int $block): JsonResponse
    {
        $validated = $request->validate([
            'reason' => ['required', 'string', 'in:' . implode(',', \App\Support\FlagReason::ALL)],
            'note' => ['nullable', 'string', 'max:2000'],
        ]);

        return $this->wrap(fn () => [
            'success' => true,
            'status' => $this->review->flagBlock(
                $translation->id,
                $block,
                Auth::id(),
                $validated['reason'],
                $validated['note'] ?? null,
            )->status,
        ], 'flagBlock');
    }

    /**
     * POST /admin/review/{translation}/bulk-approve — verify all blocks at/above a score threshold.
     */
    public function bulkApprove(Request $request, TranslationHistory $translation): JsonResponse
    {
        $validated = $request->validate([
            'threshold' => ['required', 'integer', 'min:0', 'max:100'],
        ]);

        return $this->wrap(function () use ($validated, $translation) {
            $result = $this->review->bulkApprove($translation->id, Auth::id(), (int) $validated['threshold']);
            return [
                'success' => true,
                'approved' => $result['approved'],
                'total' => $result['total'],
            ];
        }, 'bulkApprove');
    }

    /**
     * POST /admin/review/{translation}/save-regenerate — regenerate the document
     * from all edited blocks, return download links for the new + original.
     */
    public function saveAndRegenerate(Request $request, TranslationHistory $translation): JsonResponse
    {
        $validated = $request->validate([
            'note' => ['nullable', 'string', 'max:2000'],
        ]);

        return $this->wrap(function () use ($validated, $translation) {
            $translation->load('blocks');

            // Collect the CURRENT state of every block so reconstruction uses
            // the persisted current_text (edited or not) as the source of truth.
            $overrides = [];
            foreach ($translation->blocks as $block) {
                $overrides[(int) $block->block_index] = $block->current_text;
            }

            $result = $this->review->saveAndRegenerate(
                $translation->id,
                Auth::id(),
                $overrides,
                $validated['note'] ?? null,
            );

            // Generate a download link for the original alongside the new version.
            $originalUrl = null;
            if ($translation->original_storage_path) {
                try {
                    $originalUrl = $this->storage->generateSignedUrl($translation->original_storage_path)['signed_url'] ?? null;
                } catch (\Throwable $e) {
                    Log::warning('DocumentReviewController::saveAndRegenerate could not sign original file', [
                        'path' => $translation->original_storage_path,
                        'exception' => $e->getMessage(),
                    ]);
                }
            }

            return [
                'success' => true,
                'new_download_url' => $result['signed_url'],
                'new_download_filename' => $result['download_filename'],
                'original_download_url' => $originalUrl,
                'edited_blocks' => $result['edited_blocks'],
            ];
        }, 'saveAndRegenerate');
    }

    /**
     * GET /admin/review/{translation}/file — stream the translated file's bytes
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
            $bytes = $this->storage->downloadFile($translation->storage_path);
        } catch (\Throwable $e) {
            Log::error('DocumentReviewController::showTranslatedFile failed', [
                'storage_path' => $translation->storage_path,
                'exception' => $e->getMessage(),
            ]);
            abort(404, 'Translated file not found.');
        }

        $mime = (string) \mime_content_type($translation->storage_path);
        $mime = $mime !== '' ? $mime : $this->mimeForExtension($ext);

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