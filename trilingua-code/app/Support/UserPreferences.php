<?php

namespace App\Support;

final class UserPreferences
{
    public const DEFAULTS = [
        'source_language' => 'English',
        'target_language' => 'Cebuano',
        'translation_mode' => 'balanced',
        'timezone' => 'Asia/Manila',
        'date_format' => 'M j, Y g:i A T',
        'notifications' => [
            'translation_complete' => true,
            'review_updates' => true,
        ],
        'reduced_motion' => false,
        'theme' => 'light',
    ];

    /** @param array<string, mixed>|null $preferences */
    public static function normalize(?array $preferences): array
    {
        $preferences ??= [];
        $notifications = array_merge(self::DEFAULTS['notifications'], (array) ($preferences['notifications'] ?? []));

        return array_merge(self::DEFAULTS, $preferences, ['notifications' => $notifications]);
    }
}
