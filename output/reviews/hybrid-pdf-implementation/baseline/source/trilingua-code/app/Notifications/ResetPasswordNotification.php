<?php

namespace App\Notifications;

use Illuminate\Auth\Notifications\ResetPassword;
use Illuminate\Notifications\Messages\MailMessage;

class ResetPasswordNotification extends ResetPassword
{
    /**
     * Build the mail representation of the notification.
     */
    public function toMail($notifiable): MailMessage
    {
        $url = route('password.reset', [
            'token' => $this->token,
            'email' => $notifiable->getEmailForPasswordReset(),
        ]);

        return (new MailMessage)
            ->subject('Reset your TriLingua password')
            ->greeting('Hello ' . $notifiable->name . ',')
            ->line('We received a request to reset the password for your TriLingua account.')
            ->action('Reset Password', $url)
            ->line('This link will expire in ' . config('auth.passwords.users.expire', 60) . ' minutes.')
            ->line('If you did not request a password reset, no action is needed — your account is safe.')
            ->salutation('The TriLingua Team');
    }
}
