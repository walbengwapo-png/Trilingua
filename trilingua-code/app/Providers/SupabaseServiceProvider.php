<?php

namespace App\Providers;

use Illuminate\Support\ServiceProvider;

class SupabaseServiceProvider extends ServiceProvider
{
    /**
     * Bootstrap any application services.
     *
     * Validates that all required Supabase environment variables are present
     * and non-empty at application boot time.
     *
     * @throws \RuntimeException if any required variable is absent or empty.
     */
    public function boot(): void
    {
        // Skip validation during CLI commands like composer install / artisan package:discover
        if ($this->app->runningInConsole() && !$this->app->runningUnitTests()) {
            return;
        }

        $required = [
            'url' => 'SUPABASE_URL',
            'anon_key' => 'SUPABASE_ANON_KEY',
            'service_role_key' => 'SUPABASE_SERVICE_ROLE_KEY',
            'bucket' => 'SUPABASE_BUCKET',
        ];

        $missing = [];
        foreach ($required as $configKey => $var) {
            if (empty(config("supabase.{$configKey}"))) {
                $missing[] = $var;
            }
        }

        if (!empty($missing)) {
            throw new \RuntimeException(
                'Missing required Supabase environment variables: ' . implode(', ', $missing)
            );
        }
    }

    /**
     * Register any application services.
     */
    public function register(): void
    {
        //
    }
}
