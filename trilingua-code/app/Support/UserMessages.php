<?php

namespace App\Support;

class UserMessages
{
    public static function catalog(): array
    {
        static $catalog;
        return $catalog ??= json_decode(file_get_contents(resource_path('messages/en.json')), true, 512, JSON_THROW_ON_ERROR);
    }

    public static function get(string $code): array
    {
        return self::catalog()['messages'][$code] ?? self::catalog()['messages']['action_failed'];
    }

    public static function readable(mixed $value, string $fallback = 'action_failed', int $depth = 0): string
    {
        if ($depth > 3) {
            return self::get($fallback)['message'];
        }
        if (is_array($value)) {
            $value = $value['message'] ?? $value['error'] ?? $value['detail'] ?? '';
        }
        if (!is_string($value) || trim($value) === '') {
            return self::get($fallback)['message'];
        }
        $text = trim($value);
        if (str_starts_with($text, '{')) {
            $decoded = json_decode($text, true);
            return is_array($decoded) ? self::readable($decoded, $fallback, $depth + 1) : self::get($fallback)['message'];
        }
        foreach (self::catalog()['patterns'] as $rule) {
            if (preg_match('~'.$rule['pattern'].'~i', $text)) {
                $message = self::get($rule['code'])['message'];
                if (preg_match('/Reference:\s*([a-f0-9-]{36})\b/i', $text, $match)) {
                    $message .= ' Reference: '.$match[1];
                }
                return $message;
            }
        }
        return strlen($text) > 600 || str_contains($text, '<')
            ? self::get($fallback)['message'] : (self::catalog()['copy'][$text] ?? $text);
    }
}
