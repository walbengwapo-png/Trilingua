<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\User;
use Illuminate\Contracts\View\View;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Read-only admin analytics dashboard.
 *
 * All metrics are aggregated reads over translation_history, translation_blocks
 * and translation_edit_log. No state is written here.
 */
class DashboardController extends Controller
{
    public function index(Request $request): View
    {
        try {
            $data = [
                'stats'                => $this->stats(),
                'langPairFlags'        => $this->flaggedByLanguagePair(),
                'typeBreakdown'        => $this->flaggedByType(),
                'flagReasonBreakdown'  => $this->flagReasonBreakdown(),
                'avgTurnaround'        => $this->averageTurnaround(),
                'topReviewers'         => $this->topReviewers(),
                'activityOverTime'     => $this->activityOverTime(
                    $request->query('from'), $request->query('to')
                ),
                'recentActivity'       => $this->recentActivity(),
            ];
        } catch (\Throwable $e) {
            Log::error('Admin\DashboardController::index failed', [
                'exception' => $e->getMessage(),
            ]);
            $data = [
                'stats' => [
                    'total' => 0, 'pending' => 0, 'verified' => 0, 'edited' => 0,
                    'flagged' => 0, 'reviewed' => 0, 'verifiedWithoutEditPct' => 0,
                ],
                'langPairFlags' => [],
                'typeBreakdown' => [],
                'flagReasonBreakdown' => [],
                'avgTurnaround' => null,
                'topReviewers' => collect(),
                'activityOverTime' => collect(),
            ];
        }

        return view('admin.dashboard', $data);
    }

    /**
     * % verified without edit + core review counts.
     */
    private function stats(): array
    {
        $total = TranslationHistory::count();
        $flagged = TranslationHistory::where('review_status', 'flagged')->count();
        $edited = TranslationHistory::where('review_status', 'edited')->count();
        $verified = TranslationHistory::where('review_status', 'verified')->count();
        $pending = TranslationHistory::where('review_status', 'pending')->count();

        $reviewed = $verified + $edited + $flagged;
        $verifiedWithoutEditPct = $reviewed > 0 ? round($verified / $reviewed * 100, 1) : 0;

        return [
            'total' => $total,
            'pending' => $pending,
            'verified' => $verified,
            'edited' => $edited,
            'flagged' => $flagged,
            'reviewed' => $reviewed,
            'verifiedWithoutEditPct' => $verifiedWithoutEditPct,
        ];
    }

    /**
     * Most-flagged language pairs (submitted, top 8).
     */
    private function flaggedByLanguagePair(): array
    {
        return TranslationHistory::where('review_status', 'flagged')
            ->selectRaw('source_language, target_language, COUNT(*) as count')
            ->groupBy('source_language', 'target_language')
            ->orderByDesc('count')
            ->limit(8)
            ->get()
            ->map(fn ($r) => [
                'pair' => "$r->source_language → $r->target_language",
                'count' => (int) $r->count,
            ])
            ->all();
    }

    /**
     * Flag counts by translation type.
     */
    private function flaggedByType(): array
    {
        return TranslationHistory::where('review_status', 'flagged')
            ->selectRaw('translation_type, COUNT(*) as count')
            ->groupBy('translation_type')
            ->orderByDesc('count')
            ->get()
            ->pluck('count', 'translation_type')
            ->all();
    }

    /**
     * Flag-reason breakdown across flagged translations.
     *
     * Each translation is counted ONCE regardless of how many of its document
     * blocks share the flag reason — blocks merely mirror the document-level
     * flag (ReviewService::flagDocument cascades to every block), so counting
     * them would inflate the totals for a single document.
     */
    private function flagReasonBreakdown(): array
    {
        $byLabel = [];

        foreach (TranslationHistory::where('review_status', 'flagged')
            ->whereNotNull('flag_reason')
            ->get(['flag_reason']) as $r) {
            $byLabel[$r->flag_reason] = ($byLabel[$r->flag_reason] ?? 0) + 1;
        }

        arsort($byLabel);
        return $byLabel;
    }

    /**
     * Average review turnaround (hours) from submission to reviewed_at.
     */
    private function averageTurnaround(): ?float
    {
        $rows = TranslationHistory::whereNotNull('reviewed_at')
            ->whereNotNull('created_at')
            ->get(['created_at', 'reviewed_at']);

        if ($rows->isEmpty()) {
            return null;
        }

        $totalSeconds = $rows->sum(fn ($row) => $row->created_at->diffInSeconds($row->reviewed_at));

        if ($totalSeconds <= 0) {
            return null;
        }

        return round($totalSeconds / $rows->count() / 3600, 1);
    }

    /**
     * Most active reviewers (by number of review-log actions).
     */
    private function topReviewers(int $limit = 8)
    {
        return TranslationEditLog::query()
            ->select('admin_id', DB::raw('COUNT(*) as count'))
            ->whereNotNull('admin_id')
            ->groupBy('admin_id')
            ->orderByDesc('count')
            ->limit($limit)
            ->get()
            ->map(function ($row) {
                $user = User::find($row->admin_id);
                return [
                    'name' => $user?->name ?? 'Unknown',
                    'count' => (int) $row->count,
                ];
            });
    }

    /**
     * Recent mixed activity feed for the dashboard "System Activity" panel.
     *
     * @return array<int, array<string, mixed>>
     */
    private function recentActivity(int $limit = 20): array
    {
        $review = TranslationEditLog::query()
            ->select('id', 'action', 'admin_id', 'translation_history_id', 'created_at')
            ->with(['admin:id,name', 'translationHistory:id,translated_filename,original_filename'])
            ->orderByDesc('id')
            ->limit($limit)
            ->get()
            ->map(fn ($r) => [
                'type'       => 'review',
                'action'     => $r->action,
                'actor'      => $r->admin->name ?? 'Unknown',
                'target'     => ($r->translationHistory
                    ? ($r->translationHistory->translated_filename ?? $r->translationHistory->original_filename ?? '')
                    : '#' . $r->translation_history_id),
                'created_at' => $r->created_at,
            ]);

        $account = UserActivityLog::query()
            ->select('id', 'action', 'user_id', 'attempted_email', 'ip_address', 'created_at')
            ->with(['user:id,name'])
            ->orderByDesc('id')
            ->limit($limit)
            ->get()
            ->map(fn ($r) => [
                'type'       => 'account',
                'action'     => $r->action,
                'actor'      => $r->user->name ?? ($r->attempted_email ?? 'Unknown'),
                'target'     => $r->ip_address ?: '—',
                'created_at' => $r->created_at,
            ]);

        return $review
            ->concat($account)
            ->sortByDesc(fn ($r) => $r['created_at'] ?? null)
            ->take($limit)
            ->values()
            ->all();
    }

    /**
     * Verify/edit/flag action counts grouped by day.
     *
     * @param  string|null  $from  'Y-m-d'
     * @param  string|null  $to    'Y-m-d'
     * @return \Illuminate\Support\Collection<int, array<string, mixed>>
     */
    private function activityOverTime(?string $from, ?string $to): \Illuminate\Support\Collection
    {
        $query = TranslationEditLog::query();

        if ($from) {
            $query->whereDate('created_at', '>=', $from);
        } else {
            $query->whereDate('created_at', '>=', now()->subDays(29)->startOfDay());
        }

        if ($to) {
            $query->whereDate('created_at', '<=', $to);
        }

        $rows = $query->get(['action', 'created_at']);

        $byDate = [];
        foreach ($rows as $row) {
            $date = $row->created_at->toDateString();
            $byDate[$date] = $byDate[$date] ?? ['date' => $date, 'verify' => 0, 'edit' => 0, 'flag' => 0, 'total' => 0];
            $act = $row->action;
            if (in_array($act, ['verify', 'edit', 'flag'], true)) {
                $byDate[$date][$act]++;
                $byDate[$date]['total']++;
            }
        }

        ksort($byDate);
        return collect(array_values($byDate));
    }
}