<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;

class ValidateProduction extends Command
{
    protected $signature = 'deployment:validate-production {--check-migrations : Verify the deployed database schema}';

    protected $description = 'Reject unsafe production configuration before a Laravel Cloud rollout.';

    public function handle(): int
    {
        $checks = [
            'APP_ENV must be production.' => config('app.env') === 'production',
            'APP_DEBUG must be false.' => config('app.debug') === false,
            'APP_KEY must be set.' => filled(config('app.key')),
            'APP_URL must use HTTPS.' => $this->isRemoteHttps(config('app.url')),
            'Use an external PostgreSQL or MySQL database, not ephemeral SQLite.' => in_array(config('database.default'), ['pgsql', 'mysql', 'mariadb'], true),
            'PostgreSQL connections must require TLS.' => config('database.default') !== 'pgsql' || in_array(config('database.connections.pgsql.sslmode'), ['require', 'verify-ca', 'verify-full'], true),
            'SESSION_DRIVER must be database or redis.' => in_array(config('session.driver'), ['database', 'redis'], true),
            'Session cookies must be secure and HTTP-only.' => config('session.secure') === true && config('session.http_only') === true,
            'CACHE_STORE must be database or redis.' => in_array(config('cache.default'), ['database', 'redis'], true),
            'QUEUE_CONNECTION must remain database for transactional document dispatch.' => config('queue.default') === 'database',
            'PYTHON_SERVICE_URL must be the remote HTTPS translation service.' => $this->isRemoteHttps(config('translation.python_service.url')),
            'Cloud Python requires PYTHON_DOCUMENT_JOBS=true for long documents.' => ! str_ends_with((string) parse_url(config('translation.python_service.url'), PHP_URL_HOST), '.laravel.cloud') || config('translation.python_service.document_jobs') === true,
            'Durable Python document jobs require PostgreSQL.' => ! config('translation.python_service.document_jobs') || config('database.default') === 'pgsql',
            'PYTHON_SERVICE_TOKEN must contain at least 32 characters.' => strlen((string) config('translation.python_service.token')) >= 32,
            'SUPABASE_URL must use HTTPS.' => $this->isRemoteHttps(config('supabase.url')),
            'SUPABASE_SERVICE_ROLE_KEY and SUPABASE_BUCKET must be set.' => filled(config('supabase.service_role_key')) && filled(config('supabase.bucket')),
            'Disable local fallback storage on Cloud; its disk is ephemeral.' => ! config('storage.fallback.enabled'),
        ];

        $failed = array_keys(array_filter($checks, static fn (bool $valid): bool => ! $valid));
        foreach ($failed as $message) {
            $this->error($message);
        }
        if ($failed !== []) {
            return self::FAILURE;
        }

        $this->info('Production configuration checks passed (configuration only; live services are not tested).');

        return $this->call('deployment:validate-timeouts', [
            '--check-migrations' => $this->option('check-migrations'),
        ]);
    }

    private function isRemoteHttps(?string $url): bool
    {
        return filter_var($url, FILTER_VALIDATE_URL) !== false
            && parse_url($url, PHP_URL_SCHEME) === 'https'
            && ! in_array(strtolower((string) parse_url($url, PHP_URL_HOST)), ['localhost', '127.0.0.1', '[::1]'], true);
    }
}
