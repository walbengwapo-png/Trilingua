<?php

namespace App\Http\Controllers;

use Illuminate\Contracts\View\View;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Notifications\DatabaseNotification;
use Illuminate\Support\Facades\Auth;

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
        $notifications->getCollection()->transform(function (DatabaseNotification $notification) {
            $notification->target_url = $this->targetUrl($notification);

            return $notification;
        });

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
        $items = $query->limit($limit)->get()->map(function (DatabaseNotification $notification) {
            return [
                'id' => $notification->id,
                'type' => $notification->type,
                'data' => $notification->data,
                'read_at' => $notification->read_at,
                'created_at' => $notification->created_at,
                'url' => $this->targetUrl($notification),
            ];
        });

        return response()->json([
            'unread_count' => $unreadCount,
            'notifications' => $items,
        ]);
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

        return $id ? route('history', ['open' => $id]) : route('history');
    }
}
