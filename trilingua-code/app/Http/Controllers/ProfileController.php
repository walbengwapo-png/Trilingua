<?php

namespace App\Http\Controllers;

use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\UserActivityLog;
use App\Services\TranslationStatsService;
use Illuminate\Contracts\View\View;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;

class ProfileController extends Controller
{
    /**
     * Display the signed-in user's profile (read-only summary).
     *
     * Editing is intentionally kept on the Settings page; this view only
     * shows information and links out to the relevant sections.
     */
    public function show(Request $request): View
    {
        $user = Auth::user();

        $isGoogle = ! blank($user->google_id);
        $isAdmin = (bool) $user->is_admin;

        $profile = [
            'role'          => $isAdmin ? 'Administrator' : 'Member',
            'accountType'   => $isGoogle ? 'Google' : 'Email & Password',
            'memberSince'   => optional($user->created_at)->format('F j, Y'),
            'theme'         => ucfirst($user->theme ?? 'light'),
            'translations'  => $user->translations()->count(),
        ];

        if ($isAdmin) {
            return view('profile', compact('user', 'profile') + [
                'adminWorkSummary' => $this->adminWorkSummary($user->id),
            ]);
        }

        return view('profile', compact('user', 'profile') + [
            'translationSummary' => $this->translationSummary($user->id),
            'activitySummary'    => $this->activitySummary($user->id),
        ]);
    }

    /**
     * Aggregate the admin's review actions into a personal work summary.
     *
     * @return array<string, mixed>
     */
    private function adminWorkSummary(int $adminId): array
    {
        // Counters come from database aggregates over the admin's whole log;
        // only the five rows the panel lists are loaded.
        $c = TranslationEditLog::where('admin_id', $adminId)
            ->selectRaw('COUNT(*) AS total')
            ->selectRaw('COUNT(DISTINCT translation_history_id) AS items')
            ->selectRaw("SUM(CASE WHEN action = 'verify' THEN 1 ELSE 0 END) AS verifies")
            ->selectRaw("SUM(CASE WHEN action = 'edit' THEN 1 ELSE 0 END) AS edits")
            ->selectRaw("SUM(CASE WHEN action = 'flag' THEN 1 ELSE 0 END) AS flags")
            ->selectRaw('SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS this_month', [now()->copy()->startOfMonth()])
            ->first();

        $logs = TranslationEditLog::where('admin_id', $adminId)
            ->with('translationHistory:id,translated_filename,original_filename')
            ->orderByDesc('id')
            ->limit(5)
            ->get();

        $pendingQueue = TranslationHistory::where('review_status', 'pending')->count();

        $recent = $logs->map(function ($l) {
            $history = $l->translationHistory;
            $name = $history
                ? ($history->translated_filename ?? $history->original_filename ?? '#' . $l->translation_history_id)
                : '#' . $l->translation_history_id;

            return [
                'action'                => $l->action,
                'label'                 => ucfirst($l->action),
                'name'                  => $name,
                'translation_history_id'=> $l->translation_history_id,
                'created_at'            => optional($l->created_at)->format('M j, Y g:i A'),
            ];
        })->values();

        return [
            'total'         => (int) $c->total,
            'items'         => (int) $c->items,
            'verifies'      => (int) $c->verifies,
            'edits'         => (int) $c->edits,
            'flags'         => (int) $c->flags,
            'thisMonth'     => (int) $c->this_month,
            'pendingQueue'  => $pendingQueue,
            'recent'        => $recent,
        ];
    }

    /**
     * Aggregate the user's translation history into summary stats.
     *
     * @return array<string, mixed>
     */
    private function translationSummary(int $userId): array
    {
        // Counters are aggregated by the database over every row; only the
        // five most recent rows are loaded, because that is all the panel
        // actually lists. Reading a capped slice and reporting its length as
        // the user's lifetime total is the bug this replaces.
        $summary = TranslationStatsService::profileSummary($userId);

        $translations = TranslationHistory::where('user_id', $userId)
            ->orderBy('created_at', 'desc')
            ->orderBy('id', 'desc')
            ->limit(5)
            ->get();

        $recent = $translations->map(function ($t) {
            $name = $t->translation_type === 'document'
                ? ($t->original_filename ?? 'Untitled Document')
                : \Illuminate\Support\Str::limit($t->source_text ?? '', 45);

            return [
                'name'       => $name,
                'isDocument' => $t->translation_type === 'document',
                'source'     => $t->source_language ?? '?',
                'target'     => $t->target_language ?? '?',
                'date'       => optional($t->created_at)->format('M j, Y'),
                'status'     => $t->review_status ?? 'pending',
            ];
        })->values();

        return [
            'total'           => $summary['total'],
            'documents'       => $summary['documents'],
            'text'            => $summary['total'] - $summary['documents'],
            'thisMonth'       => $summary['thisMonth'],
            'languagePairs'   => $summary['languagePairs'],
            'avgQuality'      => $summary['avgQuality'],
            'statusBreakdown' => $summary['statusBreakdown'],
            'recent'          => $recent,
        ];
    }

    /**
     * Aggregate the user's account activity log into summary stats.
     *
     * @return array<string, mixed>
     */
    private function activitySummary(int $userId): array
    {
        $activities = UserActivityLog::where('user_id', $userId)
            ->orderBy('created_at', 'desc')
            ->limit(100)
            ->get();

        $count = fn (string $action) => $activities
            ->where('action', $action)
            ->count();

        $lastLogin = $activities
            ->first(fn ($a) => $a->action === 'login_success');

        $recent = $activities->take(5)->map(function ($a) {
            return [
                'action'     => $this->activityLabel($a->action),
                'created_at' => optional($a->created_at)->format('M j, Y g:i A'),
            ];
        })->values();

        return [
            'total'           => $activities->count(),
            'logins'          => $count('login_success'),
            'failedLogins'    => $count('login_failed'),
            'passwordChanges' => $count('password_changed'),
            'accountUpdates'  => $count('account_updated'),
            'lastLogin'       => optional($lastLogin?->created_at)->format('F j, Y'),
            'recent'          => $recent,
        ];
    }

    /**
     * Humanize an activity action key.
     */
    private function activityLabel(string $action): string
    {
        $labels = [
            'login_success'  => 'Successful login',
            'login_failed'   => 'Failed login',
            'logout'         => 'Sign out',
            'account_updated'=> 'Account updated',
            'password_changed' => 'Password changed',
            'registered'     => 'Registered',
        ];

        if (isset($labels[$action])) {
            return $labels[$action];
        }

        return ucwords(str_replace('_', ' ', $action));
    }
}