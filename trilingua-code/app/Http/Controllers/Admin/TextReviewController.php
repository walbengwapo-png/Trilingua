<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\TranslationHistory;
use App\Services\Admin\ReviewService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;

/**
 * Admin write actions for TEXT translations.
 *
 * All state changes go through Admin\ReviewService — this controller never
 * writes to translation_history or translation_edit_log directly.
 */
class TextReviewController extends Controller
{
    public function __construct(private ReviewService $review) {}

    /**
     * POST /admin/review/{translation}/verify — mark a text translation verified.
     */
    public function verify(Request $request, TranslationHistory $translation): JsonResponse
    {
        try {
            $validated = $request->validate(['note' => ['nullable', 'string', 'max:2000']]);
            $this->review->verify($translation->id, Auth::id(), $validated['note'] ?? null);
        } catch (\Throwable $e) {
            Log::error('TextReviewController::verify failed', [
                'id' => $translation->id,
                'exception' => $e->getMessage(),
            ]);
            return response()->json(['error' => ['code' => 'review_update_failed', 'message' => 'The review could not be saved. Please try again.', 'retryable' => true]], 500);
        }

        return response()->json(['success' => true, 'status' => 'verified', 'audit' => ['action' => 'verify', 'persisted' => true]]);
    }

    /**
     * POST /admin/review/{translation}/update — edit the translated_text.
     */
    public function update(Request $request, TranslationHistory $translation): JsonResponse
    {
        $validated = $request->validate([
            'translated_text' => ['required', 'string'],
            'note' => ['nullable', 'string', 'max:2000'],
        ]);

        try {
            $this->review->editText(
                $translation->id,
                Auth::id(),
                $validated['translated_text'],
                $validated['note'] ?? null,
            );
        } catch (\Throwable $e) {
            Log::error('TextReviewController::update failed', [
                'id' => $translation->id,
                'exception' => $e->getMessage(),
            ]);
            return response()->json(['error' => ['code' => 'review_update_failed', 'message' => 'The edit could not be saved. Please try again.', 'retryable' => true]], 500);
        }

        return response()->json(['success' => true, 'status' => 'edited', 'audit' => ['action' => 'edit', 'persisted' => true]]);
    }

    /**
     * POST /admin/review/{translation}/flag — flag a text translation.
     */
    public function flag(Request $request, TranslationHistory $translation): JsonResponse
    {
        $validated = $request->validate([
            'reason' => ['required', 'string', 'in:' . implode(',', \App\Support\FlagReason::ALL)],
            'note' => ['required', 'string', 'max:2000'],
        ]);

        try {
            $this->review->flag(
                $translation->id,
                Auth::id(),
                $validated['reason'],
                $validated['note'] ?? null,
            );
        } catch (\Throwable $e) {
            Log::error('TextReviewController::flag failed', [
                'id' => $translation->id,
                'exception' => $e->getMessage(),
            ]);
            return response()->json(['error' => ['code' => 'review_update_failed', 'message' => 'The flag could not be saved. Please try again.', 'retryable' => true]], 500);
        }

        return response()->json(['success' => true, 'status' => 'flagged', 'audit' => ['action' => 'flag', 'persisted' => true]]);
    }
}
