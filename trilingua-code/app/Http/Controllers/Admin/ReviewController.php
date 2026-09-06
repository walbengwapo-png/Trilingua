<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Services\StorageService;
use Illuminate\Contracts\View\View;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class ReviewController extends Controller
{
    public function __construct(private StorageService $storage) {}

    /**
     * GET /admin/review — render the admin review queue.
     *
     * Lists every translation across all users so an admin can pick items to
     * review. Read-only: no state is changed here.
     *
     * Supported query filters (all optional):
     *   ?status            pending|verified|edited|flagged
     *   ?user              submitter user id
     *   ?lang_pair         "Source → Target" or "Source,Target"
     *   ?from & ?to        date range (inclusive, Y-m-d)
     *   ?type              document|text
     *   ?priority          0|1 — filter by priority-review flag
     *   ?q                 free-text search over filenames + translation text
     *
     * Default sort: priority flags first, then unscored items, then lowest
     * quality_score, so the translations that most need review rise to the top.
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

            if ($langPair = trim((string) $request->query('lang_pair'))) {
                $parts = preg_split('/\s*(?:→|,)\s*/', $langPair, 2);
                if (count($parts) === 2) {
                    $query->where('source_language', trim($parts[0]));
                    $query->where('target_language', trim($parts[1]));
                }
            }

            if ($type = $request->query('type')) {
                $query->where('translation_type', $type);
            }

            $priority = $request->query('priority');
            if ($priority === '0' || $priority === '1') {
                $query->where('is_priority', '=', \Illuminate\Support\Facades\DB::raw($priority === '1' ? 'true' : 'false'));
            }

            if ($from = $request->query('from')) {
                $query->whereDate('created_at', '>=', $from);
            }

            if ($to = $request->query('to')) {
                $query->whereDate('created_at', '<=', $to);
            }

            if ($search = trim((string) $request->query('q'))) {
                $like = '%' . mb_strtolower($search) . '%';
                $query->where(function ($q) use ($like) {
                    $q->whereRaw('LOWER(original_filename) LIKE ?', [$like])
                        ->orWhereRaw('LOWER(translated_filename) LIKE ?', [$like])
                        ->orWhereRaw('LOWER(source_text) LIKE ?', [$like])
                        ->orWhereRaw('LOWER(translated_text) LIKE ?', [$like]);
                });
            }

            // Priority flags first, then unscored translations rise to the top,
            // then worst-scored first.
            $queue = $query
                ->orderBy('is_priority', 'desc')
                ->orderByRaw('quality_score IS NULL DESC, quality_score ASC')
                ->orderBy('created_at')
                ->paginate(15);

            $submitters = User::whereIn('id', function ($q) {
                $q->select('user_id')
                    ->from('translation_history')
                    ->whereNotNull('user_id');
            })
                ->orderBy('name')
                ->get(['id', 'name']);

            $langPairs = TranslationHistory::query()
                ->whereNotNull('source_language')
                ->whereNotNull('target_language')
                ->select('source_language', 'target_language')
                ->distinct()
                ->orderBy('source_language')
                ->orderBy('target_language')
                ->get()
                ->map(fn ($row) => $row->source_language . ' → ' . $row->target_language);

            return view('admin.queue', [
                'queue'      => $queue,
                'filters'    => $request->query(),
                'submitters' => $submitters,
                'langPairs'  => $langPairs,
            ]);
        } catch (\Throwable $e) {
            Log::error('ReviewController::index failed to load review queue', [
                'exception' => $e->getMessage(),
            ]);

            return view('admin.queue', [
                'queue'      => collect(),
                'filters'    => $request->query(),
                'submitters' => collect(),
                'langPairs'  => collect(),
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
            // Block list with filters + pagination. Documents can contain
            // hundreds of blocks, so we must NOT eager-load them all.
            $blocksQuery = $history->blocks();

            if ($status = $request->query('status')) {
                $blocksQuery->where('status', $status);
            }

            if ($scoreMin = $request->query('score_min')) {
                $blocksQuery->where('quality_score', '>=', (int) $scoreMin);
            }

            if ($search = trim((string) $request->query('search'))) {
                $like = '%' . mb_strtolower($search) . '%';
                $blocksQuery->where(function ($q) use ($like) {
                    $q->whereRaw('LOWER(source_text) LIKE ?', [$like])
                        ->orWhereRaw('LOWER(current_text) LIKE ?', [$like])
                        ->orWhereRaw('LOWER(ai_translated_text) LIKE ?', [$like]);
                });
            }

            $sort = $request->query('sort', 'score');
            if ($sort === 'index') {
                $blocksQuery->orderBy('block_index');
            } elseif ($sort === 'status') {
                $blocksQuery->orderBy('status')->orderBy('block_index');
            } else {
                // Worst-scored first; unscored blocks rise to the top for review.
                $blocksQuery->orderByRaw('quality_score IS NULL DESC, quality_score ASC')
                    ->orderBy('block_index');
            }

            $blocks = $blocksQuery->paginate(25)->withQueryString();

            // Whole-document view: every block in document order so the page can
            // render the translation as one continuous document (no badges or
            // per-block categorization), independent of the paginated list.
            $documentBlocks = $history->blocks()
                ->orderBy('block_index')
                ->get(['id', 'block_index', 'current_text', 'ai_translated_text']);

            // Per-record admin audit trail for the collapsible "Edit History".
            $editHistory = \App\Http\Controllers\Admin\AuditLogController::forRecord($history->id);

            // Build the translated-file preview data for the two-pane layout.
            // Serve through the inline route (Content-Disposition: inline)
            // instead of a raw storage signed URL, whose disposition depends on
            // the storage driver and often forces a DOWNLOAD. Admins want to
            // preview the document inline, not trigger a download.
            $previewUrl = null;
            if (!blank($history->storage_path)) {
                $previewUrl = route('admin.review.document.file', $history->id);
            }

            return view('admin.review-document', [
                'record'        => $history,
                'blocks'        => $blocks,
                'documentBlocks'=> $documentBlocks,
                'totalBlocks'   => $history->blocks()->count(),
                'blocksFilter'  => $request->query(),
                'previewUrl'    => $previewUrl,
                'isPdf'         => strtolower((string) pathinfo((string) $history->translated_filename, PATHINFO_EXTENSION)) === 'pdf',
                'previewExt'    => strtolower((string) pathinfo((string) $history->translated_filename, PATHINFO_EXTENSION)),
                'editHistory'   => $editHistory,
            ]);
        }

        $editHistory = \App\Http\Controllers\Admin\AuditLogController::forRecord($history->id);

        return view('admin.review-text', ['record' => $history, 'editHistory' => $editHistory]);
    }
}