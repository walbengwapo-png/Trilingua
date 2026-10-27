<?php

namespace App\Support;

/**
 * Safe display-name handling for user-uploaded files.
 *
 * User-provided filenames are trusted for *display* only. They are never used
 * as filesystem paths (upload persistence uses a server-generated dir + leaf)
 * and never embedded in storage keys. This class scrubs the display name and
 * builds an RFC 5987 Content-Disposition header value so non-ASCII names
 * survive download headers without header-injection / traversal risk.
 */
class SafeFileNames
{
    public static function scrubDisplayName(string $name, int $maxLength = 180): string
    {
        $name = basename((string) $name);
        $name = str_replace(["\x00", '/', '\\'], '', $name);
        $name = trim($name, " \t\n\r\0\x0B.");

        if ($name === '') {
            $name = 'file';
        }

        if (mb_strlen($name) > $maxLength) {
            $ext = strtolower((string) pathinfo($name, PATHINFO_EXTENSION));
            $name = mb_substr($name, 0, $maxLength);
            $name .= $ext !== '' ? '.' . $ext : '';
        }

        $clean = preg_replace('/[\x00-\x1f\x7f]/', '', $name) ?? '';
        return $clean !== '' ? $clean : 'file';
    }

    public static function contentDisposition(string $filename, string $fallback = 'download'): string
    {
        $safeFallback = self::scrubDisplayName($filename);
        if ($safeFallback === 'file' || $safeFallback === '') {
            $safeFallback = $fallback . '.' . strtolower((string) pathinfo($filename, PATHINFO_EXTENSION));
        }

        // RFC 5987 encoded value preserves UTF-8 names (again, display-only).
        $encoded = rawurlencode($safeFallback);

        return "inline; filename=\"{$safeFallback}\"; filename*=UTF-8''{$encoded}";
    }
}