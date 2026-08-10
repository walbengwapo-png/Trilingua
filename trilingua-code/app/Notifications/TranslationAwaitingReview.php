<?php

namespace App\Notifications;

use App\Models\TranslationHistory;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Notifications\Notification;

/**
 * Notify every admin that a user submitted a new translation awaiting review.
 *
 * Stored via the database channel (backed by the notifications table) and
 * rendered in the admin's header bell dropdown / notifications page.
 */
class TranslationAwaitingReview extends Notification
{
    use Queueable;

    public function __construct(
        public TranslationHistory $history,
        public ?string $submitterName = null,
    ) {
    }

    /**
     * @return array<int, string>
     */
    public function via(object $notifiable): array
    {
        return ['database'];
    }

    /**
     * @return array<string, mixed>
     */
    public function toDatabase(object $notifiable): array
    {
        return [
            'translation_id' => $this->history->id,
            'type' => $this->history->translation_type ?? 'document',
            'title' => $this->history->translated_filename
                ?? $this->history->original_filename
                ?? 'Translation',
            'source_language' => $this->history->source_language,
            'target_language' => $this->history->target_language,
            'submitter' => $this->submitterName ?? 'a user',
        ];
    }
}
