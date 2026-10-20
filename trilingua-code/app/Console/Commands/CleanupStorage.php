<?php

namespace App\Console\Commands;

use App\Services\StorageCleanupService;
use Illuminate\Console\Command;

class CleanupStorage extends Command
{
    protected $signature = 'translations:cleanup-storage
                           {--limit=50 : Max outbox rows to process per run}
                           {--candidate-grace=3600 : Min age (s) before reclaiming a publish candidate}';

    protected $description = 'Retry storage-object cleanups recorded by history deletion and reclaim stale publish candidates';

    public function handle(StorageCleanupService $cleanup): int
    {
        $result = $cleanup->processPending((int) $this->option('limit'));

        $this->info(sprintf(
            'Storage cleanup: %d processed, %d remaining pending.',
            $result['processed'],
            $result['remaining']
        ));

        $reclaimed = $cleanup->reclaimStalePublishCandidates(
            (int) $this->option('candidate-grace'),
            (int) $this->option('limit')
        );

        $this->info(sprintf(
            'Publish-candidate reclamation: %d reclaimed, %d remaining pending.',
            $reclaimed['reclaimed'],
            $reclaimed['remaining']
        ));

        return self::SUCCESS;
    }
}