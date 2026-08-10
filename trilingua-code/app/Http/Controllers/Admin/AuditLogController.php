<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\UserActivityLog;
use Illuminate\Contracts\View\View;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

/**
 * Read-only admin audit trail viewer.
 *
 * Consolidates translation_edit_log (review actions) and user_activity_log
 * (login, logout, account changes) into one paginated surface. No state is
 * written here — both tables are append-only.
 */
class AuditLogController extends Controller
{
    public function index(Request $request): View
    {
        try {
            $type   = $request->query('type', '');
            $action = $request->query('action', '');
            $from   = $request->query('from', '');
            $to     = $request->query('to', '');

            $reviewQuery = TranslationEditLog::query()
                ->with(['admin', 'translationHistory']);

            $accountQuery = UserActivityLog::query()
                ->with('user');

            if ($type === 'review') {
                $entries = $this->filterReview($reviewQuery, $action, $from, $to)
                    ->orderByDesc('id')
                    ->paginate(25)
                    ->withQueryString();
            } elseif ($type === 'account') {
                $entries = $this->filterAccount($accountQuery, $action, $from, $to)
                    ->orderByDesc('id')
                    ->paginate(25)
                    ->withQueryString();
            } else {
                // Merge both sources client-side via a unified collection,
                // then paginate manually (both sources are small enough).
                $reviewRows = $this->filterReview($reviewQuery, $action, $from, $to)
                    ->get(['id', 'action', 'admin_id', 'translation_history_id', 'note', 'created_at'])
                    ->map(function ($log) {
                        return (object) [
                            'id'           => $log->id,
                            'type'         => 'review',
                            'action'       => $log->action,
                            'actor'        => $log->admin->name ?? 'Unknown',
                            'target'       => ($log->translationHistory
                                ? ('#' . $log->translationHistory->id . ' — ' . ($log->translationHistory->translated_filename ?? $log->translationHistory->original_filename ?? ''))
                                : ('#' . $log->translation_history_id)),
                            'note'         => $log->note ?? '',
                            'created_at'   => $log->created_at,
                        ];
                    });

                $accountRows = $this->filterAccount($accountQuery, $action, $from, $to)
                    ->get(['id', 'action', 'user_id', 'attempted_email', 'ip_address', 'note', 'created_at'])
                    ->map(function ($log) {
                        return (object) [
                            'id'         => $log->id,
                            'type'       => 'account',
                            'action'     => $log->action,
                            'actor'      => $log->user->name ?? ($log->attempted_email ?? 'Unknown'),
                            'target'     => $log->ip_address ?: '—',
                            'note'       => $log->note ?? '',
                            'created_at' => $log->created_at,
                        ];
                    });

                $merged = $reviewRows->concat($accountRows)
                    ->sortByDesc('created_at')
                    ->values();

                $entries = new \Illuminate\Pagination\LengthAwarePaginator(
                    $merged->forPage($request->page ?? 1, 25),
                    $merged->count(),
                    25,
                    $request->page ?? 1,
                    ['path' => $request->url(), 'query' => $request->query()]
                );
            }

            return view('admin.audit', [
                'entries' => $entries,
                'filters' => $request->query(),
                'error'   => false,
            ]);
        } catch (\Throwable $e) {
            Log::error('AuditLogController::index failed to load audit log', [
                'exception' => $e->getMessage(),
            ]);

            return view('admin.audit', [
                'entries' => collect(),
                'filters' => $request->query(),
                'error'   => true,
            ]);
        }
    }

    private function filterReview($query, ?string $action, ?string $from, ?string $to)
    {
        if ($action) {
            $query->where('action', $action);
        }
        if ($from) {
            $query->whereDate('created_at', '>=', $from);
        }
        if ($to) {
            $query->whereDate('created_at', '<=', $to);
        }
        return $query;
    }

    private function filterAccount($query, ?string $action, ?string $from, ?string $to)
    {
        if ($action) {
            $query->where('action', $action);
        }
        if ($from) {
            $query->whereDate('created_at', '>=', $from);
        }
        if ($to) {
            $query->whereDate('created_at', '<=', $to);
        }
        return $query;
    }

    /**
     * Per-record edit history for the admin review detail pages.
     *
     * @return array<int, array<string, mixed>>
     */
    public static function forRecord(int $historyId, int $limit = 25): array
    {
        return TranslationEditLog::with('admin')
            ->where('translation_history_id', $historyId)
            ->orderByDesc('id')
            ->limit($limit)
            ->get()
            ->map(fn ($log) => [
                'id'           => $log->id,
                'admin'        => $log->admin?->name ?? 'Unknown',
                'action'       => $log->action,
                'block_id'     => $log->translation_block_id,
                'block_index'  => $log->translation_block_id
                    ? ($log->translationBlock?->block_index ?? null)
                    : null,
                'previous'     => $log->previous_text,
                'new'          => $log->new_text,
                'note'         => $log->note,
                'created_at'   => $log->created_at,
            ])
            ->all();
    }
}
