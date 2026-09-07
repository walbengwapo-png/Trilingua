<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Models\UserActivityLog;
use App\Services\TranslationStatsService;
use Illuminate\Contracts\View\View;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Read-only admin user directory.
 *
 * Index shows every registered user with activity summaries; the detail page
 * shows per-user stats, recent translations and recent review/account activity;
 * the translations page lists a single user's translation_history records.
 * Nothing here writes to the database — it is all aggregated reads.
 */
class UserController extends Controller
{
    /**
     * GET /admin/users — list all users with activity summary.
     *
     * Supported query params (all optional):
     *   ?q    free-text search over name/email
     *   ?sort recent|name|translations
     */
    public function index(Request $request): View
    {
        try {
            $query = User::query()
                ->select('users.*')
                ->withCount([
                    'translations as translations_count',
                    'reviewedTranslations as reviewed_count',
                ]);

            if ($search = trim((string) $request->query('q'))) {
                $like = '%' . mb_strtolower($search) . '%';
                $query->where(function ($q) use ($like) {
                    $q->whereRaw('LOWER(name) LIKE ?', [$like])
                        ->orWhereRaw('LOWER(email) LIKE ?', [$like]);
                });
            }

            switch ($request->query('sort')) {
                case 'name':
                    $query->orderBy('name');
                    break;
                case 'translations':
                    $query->orderByDesc('translations_count');
                    break;
                default:
                    $query->orderByDesc('created_at');
            }

            $users = $query->paginate(20)->withQueryString();

            return view('admin.users', [
                'users'   => $users,
                'filters' => $request->query(),
            ]);
        } catch (\Throwable $e) {
            Log::error('UserController::index failed', [
                'exception' => $e->getMessage(),
            ]);

            return view('admin.users', [
                'users'   => collect(),
                'filters' => $request->query(),
                'error'   => true,
            ]);
        }
    }

    /**
     * GET /admin/users/{user} — per-user overview.
     */
    public function show(User $user): View
    {
        $records = TranslationHistory::where('user_id', $user->id)
            ->orderBy('created_at', 'desc')
            ->limit(200)
            ->get()
            ->toArray();

        $stats = TranslationStatsService::compute($records);

        $totals = [
            'total'    => TranslationHistory::where('user_id', $user->id)->count(),
            'pending'  => TranslationHistory::where('user_id', $user->id)->where('review_status', 'pending')->count(),
            'verified' => TranslationHistory::where('user_id', $user->id)->where('review_status', 'verified')->count(),
            'edited'   => TranslationHistory::where('user_id', $user->id)->where('review_status', 'edited')->count(),
            'flagged'  => TranslationHistory::where('user_id', $user->id)->where('review_status', 'flagged')->count(),
        ];

        $recent = TranslationHistory::where('user_id', $user->id)
            ->orderBy('created_at', 'desc')
            ->limit(5)
            ->get();

        $reviewActions = TranslationEditLog::query()
            ->with('translationHistory:id,translated_filename,original_filename')
            ->where('admin_id', $user->id)
            ->orderByDesc('id')
            ->limit(5)
            ->get();

        $accountActions = UserActivityLog::where('user_id', $user->id)
            ->orderByDesc('id')
            ->limit(5)
            ->get();

        $loginCount    = UserActivityLog::where('user_id', $user->id)->where('action', 'login_success')->count();
        $failedLogins  = UserActivityLog::where('user_id', $user->id)->where('action', 'login_failed')->count();

        return view('admin.user-detail', compact(
            'user', 'stats', 'totals', 'recent',
            'reviewActions', 'accountActions', 'loginCount', 'failedLogins'
        ));
    }

    /**
     * GET /admin/users/{user}/translations — every translation a user submitted.
     *
     * Supported query params (all optional): ?type, ?status, ?from, ?to.
     */
    public function translations(Request $request, User $user): View
    {
        try {
            $query = TranslationHistory::where('user_id', $user->id);

            if ($type = $request->query('type')) {
                $query->where('translation_type', $type);
            }

            if ($status = $request->query('status')) {
                $query->where('review_status', $status);
            }

            if ($from = $request->query('from')) {
                $query->whereDate('created_at', '>=', $from);
            }

            if ($to = $request->query('to')) {
                $query->whereDate('created_at', '<=', $to);
            }

            $records = $query
                ->orderBy('created_at', 'desc')
                ->paginate(15)
                ->withQueryString();

            return view('admin.user-translations', [
                'user'    => $user,
                'records' => $records,
                'filters' => $request->query(),
            ]);
        } catch (\Throwable $e) {
            Log::error('UserController::translations failed', [
                'exception' => $e->getMessage(),
                'user_id'   => $user->id,
            ]);

            return view('admin.user-translations', [
                'user'    => $user,
                'records' => collect(),
                'filters' => $request->query(),
                'error'   => true,
            ]);
        }
    }
}