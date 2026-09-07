<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\TranslationBlock;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\TranslationMetric;
use App\Models\User;
use App\Models\UserActivityLog;
use App\Support\CsvExporter;
use Illuminate\Contracts\View\View;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

/**
 * Admin analytics dashboard.
 *
 * Surfaces trended, actionable KPIs over raw counts: review throughput,
 * turnaround distribution (p50/p90), quality health, engine performance and
 * the flag "root cause" report. All metrics are read-only aggregations over
 * translation_history / translation_blocks / translation_edit_log /
 * translation_metrics. Supports CSV export of the main panels.
 */
class DashboardController extends Controller
{
    public function index(Request $request): View
    {
        try {
            $data = [
                'stats'                 => $this->stats(),
                'reviewSparkline'       => $this->reviewSparkline($request->query('from'), $request->query('to')),
                'avgQuality'            => $this->averageQuality(),
                'turnaround'            => $this->turnaroundDistribution(),
                'langPairFlags'         => $this->flaggedByLanguagePair(),
                'typeBreakdown'         => $this->flaggedByType(),
                'flagReasonBreakdown'   => $this->flagReasonBreakdown(),
                'avgTurnaround'         => $this->averageTurnaround(),
                'topReviewers'          => $this->topReviewers(),
                'activityOverTime'      => $this->activityOverTime(
                    $request->query('from'), $request->query('to')
                ),
                'recentActivity'        => $this->recentActivity(),
                'systemHealth'          => $this->systemHealth(),
                'engineHealth'          => $this->engineHealth(),
                'healthScorecard'       => $this->healthScorecard(),
                'userActivity'          => $this->userActivity(),
            ];
        } catch (\Throwable $e) {
            Log::error('Admin\DashboardController::index failed', [
                'exception' => $e->getMessage(),
            ]);
            $data = [
                'stats' => [
                    'total' => 0, 'pending' => 0, 'verified' => 0, 'edited' => 0,
                    'flagged' => 0, 'reviewed' => 0, 'verifiedWithoutEditPct' => 0,
                    'completionRate' => 0, 'pendingDelta' => 0,
                ],
                'reviewSparkline' => [],
                'avgQuality' => null,
                'turnaround' => null,
                'langPairFlags' => [],
                'typeBreakdown' => [],
                'flagReasonBreakdown' => [],
                'avgTurnaround' => null,
                'topReviewers' => collect(),
                'activityOverTime' => collect(),
                'recentActivity' => [],
                'systemHealth' => [
                    'queue_pending' => 0,
                    'queue_failed' => 0,
                    'db_ok' => false,
                    'storage_ok' => false,
                ],
                'engineHealth' => [
                    'samples' => 0,
                    'avg_latency_ms' => null,
                    'avg_llm_calls' => null,
                    'cache_hit_rate' => null,
                    'retranslation_rate' => null,
                    'active_provider' => null,
                    'active_model' => null,
                ],
                'healthScorecard' => [
                    'scored' => 0,
                    'below_threshold' => 0,
                    'below_pct' => 0,
                    'dominant_issue' => null,
                    'issue_distribution' => [],
                ],
                'userActivity' => [],
            ];
        }

        return view('admin.dashboard', $data);
    }

    /**
     * Review throughput + trend + completion rate.
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

        // Completion rate: of all submitted items, how many have been reviewed.
        $completionRate = $total > 0 ? round($reviewed / $total * 100, 1) : 0;

        // Pending submissions delta: new entrants last 7 days vs previous 7.
        $now = now();
        $recent7 = TranslationHistory::whereBetween('created_at', [$now->copy()->subDays(7)->startOfDay(), $now])->count();
        $prev7 = TranslationHistory::whereBetween('created_at', [$now->copy()->subDays(14)->startOfDay(), $now->copy()->subDays(7)->endOfDay()])->count();
        $pendingDelta = $prev7 > 0 ? round(($recent7 - $prev7) / $prev7 * 100) : 0;

        return [
            'total' => $total,
            'pending' => $pending,
            'verified' => $verified,
            'edited' => $edited,
            'flagged' => $flagged,
            'reviewed' => $reviewed,
            'verifiedWithoutEditPct' => $verifiedWithoutEditPct,
            'completionRate' => $completionRate,
            'pendingDelta' => $pendingDelta,
        ];
    }

    /**
     * Per-day pending-pushed-to-reviewed / newly-pending counts for a sparkline.
     * Shows how many items entered the queue (were submitted) per day over the
     * window, so admins can spot submission volume.
     */
    private function reviewSparkline(?string $from, ?string $to): array
    {
        $days = 30;
        $start = $from ? \Carbon\Carbon::parse($from)->startOfDay() : now()->subDays($days - 1)->startOfDay();
        $end = $to ? \Carbon\Carbon::parse($to)->endOfDay() : now();

        $rows = TranslationHistory::whereBetween('created_at', [$start, $end])
            ->get(['created_at']);

        $series = [];
        $cursor = $start->copy();
        while ($cursor <= $end) {
            $date = $cursor->toDateString();
            $series[$date] = ['date' => $date, 'count' => 0];
            $cursor->addDay();
        }

        foreach ($rows as $row) {
            $date = $row->created_at->toDateString();
            if (isset($series[$date])) {
                $series[$date]['count']++;
            }
        }

        return array_values($series);
    }

    /**
     * Overall average AI quality score across scored translations.
     */
    private function averageQuality(): ?float
    {
        $score = TranslationHistory::whereNotNull('quality_score')
            ->avg('quality_score');

        return $score === null ? null : round((float) $score, 1);
    }

    /**
     * Turnaround distribution: p50 / p90 / mean in hours.
     */
    private function turnaroundDistribution(): ?array
    {
        $hours = TranslationHistory::whereNotNull('reviewed_at')
            ->whereNotNull('created_at')
            ->get(['created_at', 'reviewed_at'])
            ->map(fn ($row) => max(0.0, $row->created_at->diffInSeconds($row->reviewed_at) / 3600))
            ->sort()
            ->values();

        if ($hours->isEmpty()) {
            return null;
        }

        $count = $hours->count();
        $p50 = $hours[ (int) floor(0.50 * ($count - 1)) ];
        $p90 = $hours[ (int) floor(0.90 * ($count - 1)) ];
        $mean = $hours->avg();

        return [
            'p50' => round((float) $p50, 1),
            'p90' => round((float) $p90, 1),
            'mean' => round((float) $mean, 1),
            'sample' => $count,
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

    /**
     * Lightweight system health snapshot: queue depth, DB connectivity, storage.
     */
    private function systemHealth(): array
    {
        $queuePending = 0;
        $queueFailed  = 0;
        $dbOk         = false;
        $storageOk    = false;

        try {
            $queuePending = \DB::table('jobs')->count();
        } catch (\Throwable $e) {
            // table may not exist yet
        }

        try {
            $queueFailed = \DB::table('failed_jobs')->count();
        } catch (\Throwable $e) {
            // table may not exist yet
        }

        try {
            \DB::select('SELECT 1');
            $dbOk = true;
        } catch (\Throwable $e) {
            // connection down
        }

        try {
            $storageOk = \Storage::disk('local')->put('_health_check', 'ok')
                         && \Storage::disk('local')->exists('_health_check')
                         && \Storage::disk('local')->delete('_health_check');
        } catch (\Throwable $e) {
            $storageOk = false;
        }

        return [
            'queue_pending' => $queuePending,
            'queue_failed'  => $queueFailed,
            'db_ok'         => $dbOk,
            'storage_ok'    => $storageOk,
        ];
    }

    /**
     * AI engine performance metrics surfaced from the Python service and
     * persisted in translation_metrics.
     */
    private function engineHealth(): array
    {
        $base = TranslationMetric::query();

        $count = (clone $base)->count();
        if ($count === 0) {
            return [
                'samples' => 0,
                'avg_latency_ms' => null,
                'avg_llm_calls' => null,
                'cache_hit_rate' => null,
                'retranslation_rate' => null,
                'active_provider' => null,
                'active_model' => null,
            ];
        }

        $avgLatency = (clone $base)->avg('total_time_ms');
        $avgLlmCalls = (clone $base)->avg('llm_calls');

        // Cache hit rate = hits ÷ (hits + misses) across document runs.
        $cacheHits = (clone $base)->sum('cache_hits');
        $cacheMisses = (clone $base)->sum('cache_misses');
        $cacheTotal = $cacheHits + $cacheMisses;
        $cacheHitRate = $cacheTotal > 0 ? round($cacheHits / $cacheTotal * 100, 1) : null;

        // Retranslation rate = retranslated ÷ total translated blocks.
        $translated = (clone $base)->sum('blocks_translated');
        $retranslated = (clone $base)->sum('retranslated_chunks');
        $retranslationRate = $translated > 0 ? round($retranslated / $translated * 100, 1) : null;

        // Most recent provider/model actually used.
        $latest = (clone $base)->orderByDesc('id')->first();

        return [
            'samples' => $count,
            'avg_latency_ms' => $avgLatency === null ? null : (int) round((float) $avgLatency),
            'avg_llm_calls' => $avgLlmCalls === null ? null : round((float) $avgLlmCalls, 1),
            'cache_hit_rate' => $cacheHitRate,
            'retranslation_rate' => $retranslationRate,
            'active_provider' => $latest?->provider,
            'active_model' => $latest?->model,
        ];
    }

    /**
     * Translation health scorecard: share of documents below the quality
     * threshold plus the dominant quality issue category across document blocks.
     */
    private function healthScorecard(): array
    {
        $totalScored = TranslationHistory::whereNotNull('quality_score')->count();
        $belowThreshold = TranslationHistory::whereNotNull('quality_score')
            ->where('quality_score', '<', 70)
            ->count();

        // Dominant issue category from block-level quality_issues JSON.
        $categories = [];
        TranslationBlock::whereNotNull('quality_issues')
            ->pluck('quality_issues')
            ->each(function ($issues) use (&$categories) {
                foreach ((array) $issues as $issue) {
                    $cat = $issue['category'] ?? null;
                    if ($cat) {
                        $categories[$cat] = ($categories[$cat] ?? 0) + 1;
                    }
                }
            });
        arsort($categories);
        $dominantIssue = array_key_first($categories) ? [
            'category' => array_key_first($categories),
            'count' => reset($categories),
        ] : null;

        // Total tracked issue count for the percentage context.
        $totalIssues = array_sum($categories) ?: 1;

        $issueDistribution = [];
        foreach ($categories as $cat => $count) {
            $issueDistribution[] = [
                'category' => $cat,
                'count' => $count,
                'pct' => round($count / $totalIssues * 100, 1),
            ];
        }

        return [
            'scored' => $totalScored,
            'below_threshold' => $belowThreshold,
            'below_pct' => $totalScored > 0 ? round($belowThreshold / $totalScored * 100, 1) : 0,
            'dominant_issue' => $dominantIssue,
            'issue_distribution' => $issueDistribution,
        ];
    }

    /**
     * Top active users by number of translations created in the last 30 days.
     */
    private function userActivity(int $limit = 10): array
    {
        return TranslationHistory::where('translation_history.created_at', '>=', now()->subDays(30))
            ->join('users', 'users.id', '=', 'translation_history.user_id')
            ->selectRaw('
                translation_history.user_id,
                users.name,
                users.email,
                COUNT(*) as translation_count,
                SUM(CASE WHEN translation_history.translation_type = ? THEN 1 ELSE 0 END) as doc_count,
                SUM(CASE WHEN translation_history.translation_type = ? THEN 1 ELSE 0 END) as text_count,
                MAX(translation_history.created_at) as last_active
            ', ['document', 'text'])
            ->groupBy('translation_history.user_id', 'users.name', 'users.email')
            ->orderByDesc('translation_count')
            ->limit($limit)
            ->get()
            ->map(fn ($r) => [
                'user_id'            => $r->user_id,
                'name'               => $r->name,
                'email'              => $r->email,
                'translation_count'  => (int) $r->translation_count,
                'doc_count'          => (int) $r->doc_count,
                'text_count'         => (int) $r->text_count,
                'last_active'        => $r->last_active,
            ])
            ->all();
    }

    /**
     * GET /admin/export/review-trends  — CSV of review activity by day.
     */
    public function exportReviewTrends(Request $request)
    {
        $rows = $this->activityOverTime(
            $request->query('from'), $request->query('to')
        )->map(fn ($r) => $r)->all();

        return CsvExporter::download('review-trends.csv', $rows, [
            'date' => 'Date',
            'verify' => 'Verify',
            'edit' => 'Edit',
            'flag' => 'Flag',
            'total' => 'Total',
        ]);
    }

    /**
     * GET /admin/export/flags  — CSV of flag reasons, pairs and types.
     */
    public function exportFlags(): Response
    {
        $reasons = $this->flagReasonBreakdown();
        $reasonRows = [];
        foreach ($reasons as $label => $count) {
            $reasonRows[] = ['reason' => $label, 'count' => $count];
        }

        return CsvExporter::download('flag-report.csv', $reasonRows, [
            'reason' => 'Flag Reason',
            'count' => 'Count',
        ]);
    }

    /**
     * GET /admin/export/users  — CSV of user activity (last 30 days).
     */
    public function exportUsers(): Response
    {
        return CsvExporter::download('user-activity.csv', $this->userActivity(), [
            'user_id' => 'User ID',
            'name' => 'Name',
            'email' => 'Email',
            'translation_count' => 'Translations',
            'doc_count' => 'Documents',
            'text_count' => 'Text',
            'last_active' => 'Last Active',
        ]);
    }
}