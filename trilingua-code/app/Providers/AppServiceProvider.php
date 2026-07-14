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
                'verify'          => true,
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
