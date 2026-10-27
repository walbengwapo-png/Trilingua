<?php

namespace App\Support;

use App\Models\TranslationHistory;
use App\Models\User;
use App\Notifications\PriorityRequestRaised;
use App\Notifications\TranslationAwaitingReview;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Fan-out helpers for admin-facing notifications.
 *
 * All admin notifications ride the same `notifications` table via the
 * database channel, so they appear in every admin's bell + notifications page.
 */
class AdminNotifier
{
    /**
     * Tell every admin a new translation is awaiting review.
     */
    public static function awaitingReview(TranslationHistory $history, ?string $submitterName = null): void
    {
        try {
            $notification = new TranslationAwaitingReview($history, $submitterName);
            User::where('is_admin', '=', DB::raw('true'))->each(function (User $admin) use ($notification) {
                $admin->notify($notification);
            });
        } catch (\Throwable $e) {
            Log::warning('AdminNotifier: failed to send awaiting-review notification', [
                'translation_history_id' => $history->id ?? null,
                'exception' => $e->getMessage(),
            ]);
        }
    }

    /**
     * Tell every admin a user raised a priority review request.
     */
    public static function priorityRequestRaised(TranslationHistory $history, ?string $submitterName = null): void
    {
        try {
            $notification = new PriorityRequestRaised($history, $submitterName);
            User::where('is_admin', '=', DB::raw('true'))->each(function (User $admin) use ($notification) {
                $admin->notify($notification);
            });
        } catch (\Throwable $e) {
            Log::warning('AdminNotifier: failed to send priority-request notification', [
                'translation_history_id' => $history->id ?? null,
                'exception' => $e->getMessage(),
            ]);
        }
    }
}
