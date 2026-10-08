<?php

namespace Tests\Feature;

use Illuminate\Http\Middleware\TrustProxies;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use Tests\TestCase;

class CloudProxyTest extends TestCase
{
    public function test_cloud_ingress_preserves_https_and_client_address(): void
    {
        $previous = $_ENV['LARAVEL_CLOUD'] ?? null;
        try {
            $_ENV['LARAVEL_CLOUD'] = '1';
            TrustProxies::flushState();
            $this->refreshApplication();
            Route::get('/cloud-proxy-test', static fn (Request $request): array => [
                'secure' => $request->isSecure(),
                'client' => $request->ip(),
            ]);
            $this->withServerVariables(['REMOTE_ADDR' => '10.0.0.10'])
                ->withHeaders(['X-Forwarded-Proto' => 'https', 'X-Forwarded-For' => '203.0.113.8'])
                ->get('/cloud-proxy-test')
                ->assertOk()->assertJson(['secure' => true, 'client' => '203.0.113.8']);
        } finally {
            if ($previous === null) {
                unset($_ENV['LARAVEL_CLOUD']);
            } else {
                $_ENV['LARAVEL_CLOUD'] = $previous;
            }
            TrustProxies::flushState();
        }
    }
}
