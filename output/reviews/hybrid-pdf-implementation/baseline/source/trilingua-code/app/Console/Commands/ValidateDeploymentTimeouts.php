<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;

class ValidateDeploymentTimeouts extends Command
{
    protected $signature = 'deployment:validate-timeouts {--check-migrations : Refuse startup when database migrations are pending}';

    protected $description = 'Verify the effective (post-.env) timeout ladder is safe: python < job < worker < retry_after < reconcile/check-stale.';

    public function handle(): int
    {
        if ($this->option('check-migrations')) {
            $migrator = app('migrator');
            if (! $migrator->repositoryExists()) {
                $this->error('Migration repository missing. Run php artisan migrate before starting services.');
                return self::FAILURE;
            }
            $pending = array_diff(array_keys($migrator->getMigrationFiles(database_path('migrations'))), $migrator->getRepository()->getRan());
            if ($pending !== []) {
                $this->error('Pending migrations: '.implode(', ', $pending));
                $this->error('Run php artisan migrate before starting services.');
                return self::FAILURE;
            }
            $this->info('All database migrations are applied.');
        }

        $effective = config('timeouts');

        $stages = [
            'python_service'  => 'Python engine HTTP limit',
            'job'             => 'Illuminate job $timeout',
            'worker'          => 'queue worker --timeout',
            'retry_after'     => 'database queue lease (retry_after)',
            'reconcile_processing' => 'translations:reconcile processing timeout',
            'check_stale'     => 'queue:check-stale threshold (advisory)',
        ];

        $this->table(
            ['Stage', 'Role', 'Seconds'],
            array_map(
                static fn (string $key, string $role): array => [$key, $role, (string) ($effective[$key] ?? 'missing')],
                array_keys($stages),
                array_values($stages)
            )
        );

        $pairwise = [
            ['job', 'python_service', 'job $timeout must exceed the Python engine HTTP limit'],
            ['worker', 'job', 'worker --timeout must exceed the job $timeout'],
            ['retry_after', 'worker', 'database retry_after must exceed the worker --timeout so a live job is never re-leased'],
            ['reconcile_processing', 'retry_after', 'reconcile processing timeout must exceed retry_after so the reconciler never kills a live job'],
            ['check_stale', 'worker', 'queue:check-stale threshold should exceed worker --timeout'],
        ];

        $problems = [];

        foreach ($pairwise as [$higher, $lower, $message]) {
            $hi = (int) ($effective[$higher] ?? 0);
            $lo = (int) ($effective[$lower] ?? 0);
            if ($hi <= $lo) {
                $problems[] = "{$higher} ({$hi}s) must exceed {$lower} ({$lo}s): {$message}.";
            }
        }

        if ($problems !== []) {
            foreach ($problems as $problem) {
                $this->error('  - ' . $problem);
            }

            $this->error('Fix the timeout values in .env (or config defaults) before starting workers; unsafe values allow double execution or false reconciliation failures.');

            return self::FAILURE;
        }

        $this->info('Timeout ladder is safe:  python_service < job < worker < retry_after < reconcile/check-stale.');

        return $this->validateQueueAtomicity();
    }

    /**
     * Intake relies on the queued-state write and the queue insert sharing ONE
     * commit boundary. That is only true for the database driver when the jobs
     * table lives on the same connection as translation_jobs and the insert
     * takes part in the caller's transaction (after_commit = false).
     *
     * No cross-driver atomicity is claimed. If these do not hold, the intake
     * path cannot distinguish "enqueued and committed" from "rolled back", so
     * deployment must fail loudly rather than silently degrade.
     */
    private function validateQueueAtomicity(): int
    {
        $default = (string) config('queue.default');
        $connection = config('queue.connections.'.$default);

        if (! is_array($connection)) {
            $this->error("  - Queue connection '{$default}' is not configured.");

            return self::FAILURE;
        }

        $driver = (string) ($connection['driver'] ?? '');

        $this->table(
            ['Queue setting', 'Effective value'],
            [
                ['driver', $driver],
                ['connection', ($connection['connection'] ?? null) === null ? '(default)' : (string) $connection['connection']],
                ['table', (string) ($connection['table'] ?? '(none)')],
                ['after_commit', var_export($connection['after_commit'] ?? null, true)],
            ]
        );

        if ($driver !== 'database') {
            $this->warn("  - Queue driver is '{$driver}'. Intake will not claim enqueue/rollback atomicity; unresolved dispatches are reported as temporarily unavailable instead.");

            return self::SUCCESS;
        }

        $queueConnection = $connection['connection'] ?? null;
        $defaultConnection = (string) config('database.default');

        if ($queueConnection !== null && (string) $queueConnection !== $defaultConnection) {
            $this->error("  - DB_QUEUE_CONNECTION is '{$queueConnection}' but DB_CONNECTION is '{$defaultConnection}'. The jobs table is on a different connection, so the queued-state write and the queue insert CANNOT share a transaction.");
            $this->error('    Unset DB_QUEUE_CONNECTION so the queue uses the same connection as translation_jobs.');

            return self::FAILURE;
        }

        if (($connection['after_commit'] ?? false) === true) {
            $this->error('  - queue.connections.'.$default.'.after_commit is true, so the queue insert is deferred past the caller transaction and can outlive a rollback.');
            $this->error('    Set after_commit to false so a rolled-back state transaction leaves no receivable job.');

            return self::FAILURE;
        }

        $this->info('Queue atomicity preconditions hold: driver=database, connection='.$defaultConnection.', after_commit=false.');

        return self::SUCCESS;
    }
}
