<?php

namespace App\Http\Controllers;

use Illuminate\Contracts\View\View;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Notifications\DatabaseNotification;
use Illuminate\Support\Facades\Auth;
use App\Models\TranslationHistory;
use Illuminate\Support\Collection;

/**
 * In-app notification feed for the header bell.
 *
 * Reads the Laravel database notification channel for the authenticated user.
 * Read-only listing plus a mark-as-read action; nothing else mutates here.
 */
class NotificationController extends Controller
{
    /**
     * GET /notifications — render the full notifications page.
     *
     * Server-rendered list (50 per page) with an optional `?unread=1` filter
     * and an unread-count badge. Works for both regular users and admins.
     */
    public function page(Request $request): View
    {
        $user = Auth::user();

        $query = $user->notifications();
        if ($request->boolean('unread')) {
            $query->whereNull('read_at');
        }

        $notifications = $query->paginate(50)->withQueryString();
        $this->present($notifications->getCollection());

        return view('notifications', [
            'notifications' => $notifications,
            'unreadCount'   => $user->unreadNotifications()->count(),
            'unreadOnly'    => $request->boolean('unread'),
            'error'         => false,
        ]);
    }

    /**
     * GET /notifications/data — return the user's notifications (newest first).
     *
     * Includes a compact unread count and an `unread_only` filter option.
     */
    public function index(Request $request): JsonResponse
    {
        $user = Auth::user();
        $limit = (int) $request->query('limit', 20);
        $limit = min(max($limit, 1), 100);

        $unreadCount = $user->unreadNotifications()->count();

        $query = $user->notifications();
        if ($request->boolean('unread_only')) {
            $query->whereNull('read_at');
        }
        $items = $this->present($query->limit($limit)->get())->map(function (DatabaseNotification $notification) {
            return [
                'id' => $notification->id,
                'type' => $notification->type,
                'data' => $notification->data,
                'read_at' => $notification->read_at,
                'created_at' => $notification->created_at,
                'url' => $this->targetUrl($notification),
                'display_title' => $notification->display_title,
                'description' => $notification->description,
                'icon' => $notification->icon,
            ];
        });

        return response()->json([
            'unread_count' => $unreadCount,
            'notifications' => $items,
        ]);
    }

    private function present(Collection $notifications): Collection
    {
        $ids = $notifications->map(fn ($item) => $item->data['translation_id'] ?? null)->filter()->unique();
        $records = TranslationHistory::whereIn('id', $ids)
            ->when(!Auth::user()?->is_admin, fn ($query) => $query->where('user_id', Auth::id()))
            ->get(['id', 'original_filename', 'translated_filename', 'source_text'])->keyBy('id');

        return $notifications->transform(function (DatabaseNotification $notification) use ($records) {
            $data = $notification->data ?? [];
            $kind = class_basename($notification->type);
            $id = $data['translation_id'] ?? null;
            $name = $records->get($id)?->displayName() ?: ($data['title'] ?? 'Translation');
            $event = match ($kind) {
                'TranslationCompleted' => 'Translation completed',
                'TranslationFailed' => 'Translation failed',
                'TranslationAwaitingReview' => 'Awaiting review',
                'PriorityRequestRaised' => 'Priority review requested',
                default => 'Translation update',
            };
            $context = array_filter([
                !empty($data['source_language']) && !empty($data['target_language'])
                    ? $data['source_language'].' → '.$data['target_language'] : null,
                $id ? 'Translation #'.$id : null,
                !$id && !empty($data['job_id']) ? 'Job #'.$data['job_id'] : null,
                $data['submitter'] ?? null,
            ]);
            $notification->display_title = $event.' — '.$name;
            $notification->description = implode(' · ', $context);
            $notification->icon = match ($kind) {
                'TranslationFailed' => 'error',
                'TranslationAwaitingReview' => 'awaiting',
                'PriorityRequestRaised' => 'priority',
                default => 'success',
            };
            $notification->target_url = $this->targetUrl($notification);

            return $notification;
        });
    }

    /**
     * POST /notifications/read — mark one or all notifications as read.
     *
     * Body: { id?: notification id }. When no id is given, everything is read.
     */
    public function markRead(Request $request): JsonResponse
    {
        $user = Auth::user();
        $id = $request->input('id');

        if ($id) {
            $user->notifications()
                ->where('id', $id)
                ->update(['read_at' => now()]);
        } else {
            $user->unreadNotifications()->update(['read_at' => now()]);
        }

        return response()->json([
            'success' => true,
            'unread_count' => $user->unreadNotifications()->count(),
        ]);
    }

    /**
     * Resolve where a notification should take the user when clicked.
     *
     * Admin-facing notifications (awaiting review, priority requests) jump
     * straight to the matching record in the admin review queue. Everything
     * else lands on the Saved Translations page, auto-opening the record's
     * details when the notification carries a translation id.
     */
    private function targetUrl(DatabaseNotification $notification): string
    {
        $data = $notification->data ?? [];
        $id   = $data['translation_id'] ?? null;
        $kind = class_basename($notification->type);

        if (Auth::user()?->is_admin
            && in_array($kind, ['TranslationAwaitingReview', 'PriorityRequestRaised'], true)) {
            return $id ? route('admin.review.show', $id) : route('admin.review.index');
        }

        return $id ? route('history.view', $id) : route('history');
    }
}
