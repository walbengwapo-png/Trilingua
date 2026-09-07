<?php

use App\Http\Middleware\EnsureUserIsAdmin;
use App\Http\Middleware\SecurityHeaders;
use App\Http\Middleware\ValidateSession;
use Illuminate\Console\Scheduling\Schedule;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware): void {
        // Trust only Cloudflare edge proxies (Tunnel/CDN) so X-Forwarded-* headers
        // cannot be spoofed by arbitrary clients. Never use `*` here.
        // If the deployment moves to a different ingress/CDN, update this list.
        $middleware->trustProxies(at: [
            // Cloudflare IPv4
            '173.245.48.0/20',
            '103.21.244.0/22',
            '103.22.200.0/22',
            '103.31.4.0/22',
            '141.101.64.0/18',
            '108.162.192.0/18',
            '190.93.240.0/20',
            '188.114.96.0/20',
            '197.234.240.0/22',
            '198.41.128.0/17',
            '162.158.0.0/15',
            '104.16.0.0/13',
            '104.24.0.0/14',
            '172.64.0.0/13',
            '131.0.72.0/22',
            // Cloudflare IPv6
            '2400:cb00::/32',
            '2606:4700::/32',
            '2803:f800::/32',
            '2405:b500::/32',
            '2405:8100::/32',
            '2a06:98c0::/29',
            '2c0f:f248::/32',
        ]);

        // Add session validation middleware to web group
        $middleware->web(append: [
            ValidateSession::class,
            SecurityHeaders::class,
        ]);

        // Register middleware aliases
        $middleware->alias([
            'admin' => EnsureUserIsAdmin::class,
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
