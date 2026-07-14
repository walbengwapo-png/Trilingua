<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\File;

class CleanupTempFiles extends Command
{
    protected $signature = 'trilingua:cleanup-temp';

    protected $description = 'Delete temporary translation files older than 24 hours';

    public function handle(): int
    {
        $tempDir = storage_path('app/temp');

        if (!is_dir($tempDir)) {
            $this->info('Temp directory does not exist. Nothing to clean.');
            return self::SUCCESS;
        }

        $ cutoff = now()->subHours(24);
        $deleted = 0;

        $files = File::files($tempDir);
        foreach ($files as $file) {
            if ($file->getMTime() < $cutoff->timestamp) {
                File::delete($file->getRealPath());
                $deleted++;
            }
        }

        $this->info("Cleaned up {$deleted} temporary file(s) older than 24 hours.");
        return self::SUCCESS;
    }
}
