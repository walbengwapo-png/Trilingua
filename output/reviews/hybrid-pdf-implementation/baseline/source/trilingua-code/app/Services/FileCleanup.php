<?php

namespace App\Services;

use Illuminate\Support\Facades\Log;

/**
 * Guarded removal of the per-submission scratch directory under
 * storage/app/uploads/{uuid}. Bytes are moved into these dirs before an intake
 * result is known, so every early return and failure path must clear them;
 * missing dirs and unlink hiccups are explicitly non-fatal.
 */
final class FileCleanup
{
    public static function dir(?string $dir): void
    {
        if ($dir === null || $dir === '' || ! is_dir($dir)) {
            return;
        }

        try {
            foreach (scandir($dir) ?: [] as $entry) {
                if ($entry === '.' || $entry === '..') {
                    continue;
                }
                @unlink($dir . DIRECTORY_SEPARATOR . $entry);
            }

            // https://bugs.php.net/bug.php?id=47246 — on Windows rmdir can
            // transiently fail right after removing children (lingering handle
            // from file watchers/AV), leaving an empty dir behind. Retry a few
            // times before declaring the pass failed; an empty leftover is
            // data-safe but should still be reclaimed.
            for ($attempt = 0; $attempt < 5; $attempt++) {
                if (@rmdir($dir)) {
                    break;
                }
                usleep(50_000);
            }
        } catch (\Throwable $e) {
            Log::warning('Failed to clean upload directory', [
                'dir' => $dir,
                'exception' => $e->getMessage(),
            ]);
        }
    }
}