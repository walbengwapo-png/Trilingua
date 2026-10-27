<?php

namespace App\Console\Commands;

use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

class CheckStaleQueueJobs extends Command
{
    /**
     * The name and signature of the console command.
     */
    protected $signature = 'queue:check-stale
                            {--threshold=120 : Seconds a reserved job may run before it is flagged as stale}';

    /**
     * The console command description.
     */
    protected $description = 'Flag queue jobs that have been reserved (running) longer than a threshold without completing.';

    public function handle(): int
    {
        $threshold = (int) $this->option('threshold');
        $cutoff = time() - $threshold;

        $stale = DB::table('jobs')
            ->whereNotNull('reserved_at')
            ->where('reserved_at', '<', $cutoff)
            ->get(['id', 'queue', 'payload', 'attempts', 'reserved_at', 'available_at', 'created_at']);

        if ($stale->isEmpty()) {
            $this->info("No stale jobs. All reserved jobs are younger than {$threshold}s.");

            return self::SUCCESS;
        }

        $this->warn(sprintf('Found %d stale job(s) reserved for more than %ds:', $stale->count(), $threshold));

        $rows = $stale->map(function ($job) {
            $payload = json_decode($job->payload, true);
            $name = $payload['displayName'] ?? 'unknown';

            return [
                'id' => $job->id,
                'queue' => $job->queue,
                'job' => class_basename($name),
                'attempts' => $job->attempts,
                'running_for' => Carbon::now()->subSeconds(time() - (int) $job->reserved_at)->diffForHumans(),
                'reserved_at' => Carbon::createFromTimestampUTC((int) $job->reserved_at)->toDateTimeString(),
                'created_at' => Carbon::createFromTimestampUTC((int) $job->created_at)->toDateTimeString(),
            ];
        });

        $this->table(
            ['ID', 'Queue', 'Job', 'Attempts', 'Running For', 'Reserved At (UTC)', 'Created At (UTC)'],
            $rows
        );

        $this->warn('These jobs are either genuinely hung or were abandoned by a dead worker. Inspect before reprocessing.');

        return self::FAILURE;
    }
}
