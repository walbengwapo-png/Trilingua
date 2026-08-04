<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\TranslationHistory;
use Illuminate\Contracts\View\View;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class ReviewController extends Controller
{
    /**
     * GET /admin/review — render the admin review queue.
     *
     * Lists every translation across all users so an admin can pick items to
     * review. Read-only: no state is changed here.
     *
     * Supported query filters (all optional):
     *   ?status            pending|verified|edited|flagged
     *   ?user              submitter user id
     *   ?lang_pair         "Source→Target" (case-insensitive)
     *   ?from & ?to        date range (inclusive, Y-m-d)
     *   ?type              document|text
     *
     * Default sort: lowest quality_score first, so the worst translations rise
     * to the top of the queue.
     */
    public function index(Request $request): View
    {
        try {
            $query = TranslationHistory::query()->with('user');

            if ($status = $request->query('status')) {
                $query->where('review_status', $status);
            }

            if ($user = $request->query('user')) {
                $query->where('user_id', (int) $user);
            }

            if ($langPair = $request->query('lang_pair')) {
                [$source, $target] = array_pad(explode(',', $langPair, 2), 2, '');
                $query->whereRaw('LOWER(source_language) = ?', [strtolower(trim($source))]);
                $query->whereRaw('LOWER(target_language) = ?', [strtolower(trim($target))]);
            }

            if ($type = $request->query('type')) {
                $query->where('translation_type', $type);
            }

            if ($from = $request->query('from')) {
                $query->whereDate('created_at', '>=', $from);
            }

            if ($to = $request->query('to')) {
                $query->whereDate('created_at', '<=', $to);
            }

            $queue = $query->orderBy('quality_score')->orderBy('created_at')->paginate(15);

            $submitters = TranslationHistory::with('user')
                ->get()
                ->pluck('user')
                ->filter()
                ->unique('id')
                ->sortBy('name')
                ->values();

            return view('admin.queue', [
                'queue'      => $queue,
                'filters'    => $request->query(),
                'submitters' => $submitters,
            ]);
        } catch (\Throwable $e) {
            Log::error('ReviewController::index failed to load review queue', [
                'exception' => $e->getMessage(),
            ]);

            return view('admin.queue', [
                'queue'      => collect(),
                'filters'    => $request->query(),
                'submitters' => collect(),
                'error'      => true,
            ]);
        }
    }

    /**
     * GET /admin/review/{translation} — show a single translation for read-only review.
     *
     * Dispatches to the text or document detail view based on translation_type.
     * No verify / edit / flag actions are exposed here (write actions live in
     * TextReviewController / DocumentReviewController).
     */
    public function show(Request $request, TranslationHistory $translation): View
    {
        $history = $translation->load(['user', 'reviewer']);

        if ($history->translation_type === 'document') {
            $history->load('blocks');
            return view('admin.review-document', ['record' => $history]);
        }

        return view('admin.review-text', ['record' => $history]);
    }
}