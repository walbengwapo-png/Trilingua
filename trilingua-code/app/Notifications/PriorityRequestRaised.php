<?php

namespace App\Notifications;

use App\Models\TranslationHistory;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Notifications\Notification;

/**
 * Notify every admin that a user flagged a translation as "priority for review".
 *
 * Sent only when the flag flips ON, so admins are not spammed on toggle-off.
 * Stored via the database channel and rendered in the admin's header bell.
 */
class PriorityRequestRaised extends Notification
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
