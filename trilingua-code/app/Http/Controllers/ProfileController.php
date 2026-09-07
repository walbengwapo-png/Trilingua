<?php

namespace App\Http\Controllers;

use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\UserActivityLog;
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
        $logs = TranslationEditLog::where('admin_id', $adminId)
            ->with('translationHistory:id,translated_filename,original_filename')
            ->orderByDesc('id')
            ->limit(200)
            ->get();

        $total     = $logs->count();
        $items     = $logs->pluck('translation_history_id')->unique()->count();
        $verifies  = $logs->where('action', 'verify')->count();
        $edits     = $logs->where('action', 'edit')->count();
        $flags     = $logs->where('action', 'flag')->count();
        $thisMonth = $logs->filter(
            fn ($l) => $l->created_at && $l->created_at->isCurrentMonth()
        )->count();

        $pendingQueue = TranslationHistory::where('review_status', 'pending')->count();

        $recent = $logs->take(5)->map(function ($l) {
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
            'total'         => $total,
            'items'         => $items,
            'verifies'      => $verifies,
            'edits'         => $edits,
            'flags'         => $flags,
            'thisMonth'     => $thisMonth,
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
        $translations = TranslationHistory::where('user_id', $userId)
            ->orderBy('created_at', 'desc')
            ->limit(200)
            ->get();

        $total      = $translations->count();
        $documents  = $translations->where('translation_type', 'document')->count();
        $thisMonth  = $translations->filter(
            fn ($t) => $t->created_at && $t->created_at->isCurrentMonth()
        )->count();

        $pairs      = $translations
            ->filter(fn ($t) => $t->source_language || $t->target_language)
            ->map(fn ($t) => ($t->source_language ?? '?') . '|' . ($t->target_language ?? '?'))
            ->unique()
            ->count();

        $quality    = $translations
            ->pluck('quality_score')
            ->filter(fn ($q) => $q !== null && $q >= 0)
            ->values();

        $avgQuality = $quality->isNotEmpty()
            ? round($quality->avg(), 1)
            : null;

        $statusBreakdown = [
            'pending'  => $translations->where('review_status', 'pending')->count(),
            'verified' => $translations->where('review_status', 'verified')->count(),
            'edited'   => $translations->where('review_status', 'edited')->count(),
            'flagged'  => $translations->where('review_status', 'flagged')->count(),
        ];

        $recent = $translations->take(5)->map(function ($t) {
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
            'total'           => $total,
            'documents'       => $documents,
            'text'            => $total - $documents,
            'thisMonth'       => $thisMonth,
            'languagePairs'   => $pairs,
            'avgQuality'      => $avgQuality,
            'statusBreakdown' => $statusBreakdown,
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