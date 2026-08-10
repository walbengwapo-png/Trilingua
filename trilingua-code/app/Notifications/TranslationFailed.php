<?php

namespace App\Notifications;

use Illuminate\Bus\Queueable;
use Illuminate\Notifications\Notification;

/**
 * Notify a user that their queued document translation failed.
 *
 * Stored via the database channel (backed by the notifications table) and
 * rendered in the header bell dropdown.
 */
class TranslationFailed extends Notification
{
    use Queueable;

    public function __construct(
        public string $filename,
        public string $message,
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
            'translation_id' => null,
            'type' => 'document',
            'title' => $this->filename,
            'error' => $this->message,
        ];
    }
}
