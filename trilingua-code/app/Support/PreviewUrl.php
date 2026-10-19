<?php

namespace App\Support;

final class PreviewUrl
{
    public static function pdf(?string $value): string
    {
        $value = trim($value ?? '');
        if (preg_match('/[\x00-\x20<>"\'\\\\]/', $value)) {
            return 'about:blank';
        }
        if (str_starts_with($value, '/') && ! str_starts_with($value, '//')) {
            return $value;
        }
        if (filter_var($value, FILTER_VALIDATE_URL) && in_array(strtolower(parse_url($value, PHP_URL_SCHEME) ?? ''), ['https', 'http'], true)) {
            return $value;
        }

        return 'about:blank';
    }
}
