<?php

use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Console\Scheduling\Schedule;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware): void {
        // Trust Cloudflare Tunnel / reverse proxy headers so HTTPS URLs are generated correctly
        $middleware->trustProxies(at: '*');

        // Add session validation middleware to web group
        $middleware->web(append: [
            \App\Http\Middleware\ValidateSession::class,
            \App\Http\Middleware\SecurityHeaders::class,
        ]);

        // Register middleware aliases
        $middleware->alias([
            'admin' => \App\Http\Middleware\EnsureUserIsAdmin::class,
        ]);

        // Configure rate limiting
        $middleware->throttleApi();
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        //
    })
    ->withSchedule(function (Schedule $schedule): void {
        // Reconcile the durable job state machine and flag stuck workers.
        $schedule->command('translations:reconcile')
            ->everyFifteenMinutes()
            ->withoutOverlapping();

        // Surface queue jobs whose lease expired without completing.
        $schedule->command('queue:check-stale --threshold=900')
            ->everyFifteenMinutes()
            ->withoutOverlapping();
    })
    ->create();
