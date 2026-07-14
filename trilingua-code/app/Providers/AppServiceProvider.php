<?php

namespace App\Providers;

use GuzzleHttp\Client;
use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     */
    public function register(): void
    {
        // Register Guzzle HTTP client as a singleton so StorageService
        // can have it injected via the container.
        $this->app->singleton(Client::class, function () {
            return new Client([
                'timeout'         => 120,
                'connect_timeout' => 30,
                // Disable SSL verification on Windows where the system CA
                // certificate bundle may not be found by OpenSSL. Safe for
                // local development; production should use proper CA config.
                'verify'          => !str_contains(PHP_OS, 'WIN'),
            ]);
        });
    }

    /**
     * Bootstrap any application services.
     */
    public function boot(): void
    {
        //
    }
}
