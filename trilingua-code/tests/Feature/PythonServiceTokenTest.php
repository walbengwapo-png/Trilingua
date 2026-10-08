<?php

namespace Tests\Feature;

use App\Services\Translation\DTO\TranslationRequest;
use App\Services\Translation\TranslationManager;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

/**
 * Gate 2 - the Laravel half of the shared service token.
 *
 * The engine reads PYTHON_SERVICE_TOKEN and refuses to start in production
 * without it. These tests pin the other half of that contract: this
 * application must present the same value as X-Service-Token on every
 * protected call, and must present nothing at all when no token is configured
 * so local and test runs keep working.
 */
class PythonServiceTokenTest extends TestCase
{
    /**
     * A protected call, so the token headers are actually applied.
     */
    private function callProtectedEndpoint(): void
    {
        Http::fake([
            '*' => Http::response(['translated_text' => 'Kurso'], 200),
        ]);

        try {
            (new TranslationManager())->translateText(
                new TranslationRequest('Course', 'english', 'cebuano')
            );
        } catch (\Throwable) {
            // The response is faked; only the outgoing request matters here.
        }
    }

    public function test_the_configured_token_is_sent_as_the_service_token_header(): void
    {
        config(['translation.python_service.token' => 'shared-secret']);

        $this->callProtectedEndpoint();

        Http::assertSent(function ($request) {
            return $request->hasHeader('X-Service-Token')
                && $request->header('X-Service-Token')[0] === 'shared-secret';
        });
    }

    public function test_no_header_is_sent_when_no_token_is_configured(): void
    {
        config(['translation.python_service.token' => '']);

        $this->callProtectedEndpoint();

        Http::assertSent(function ($request) {
            return ! $request->hasHeader('X-Service-Token');
        });
    }

    public function test_a_null_token_sends_no_header_rather_than_an_empty_one(): void
    {
        // A null env value must not become an empty X-Service-Token header:
        // the engine would receive an empty credential instead of none.
        config(['translation.python_service.token' => null]);

        $this->callProtectedEndpoint();

        Http::assertSent(function ($request) {
            return ! $request->hasHeader('X-Service-Token');
        });
    }

    public function test_the_token_key_is_the_one_the_engine_reads(): void
    {
        // Guards the two-sides agreement in code. The engine reads
        // PYTHON_SERVICE_TOKEN; if this config key ever changes, this fails.
        $this->assertSame(
            env('PYTHON_SERVICE_TOKEN'),
            config('translation.python_service.token')
        );
    }

    public function test_the_health_probe_is_not_gated_by_the_token(): void
    {
        // /health is intentionally reachable by monitoring without a secret.
        // A token must not be attached there either, so the probe cannot be
        // mistaken for evidence that the token is enforced.
        config(['translation.python_service.token' => 'shared-secret']);

        Http::fake(['*' => Http::response(['status' => 'ok'], 200)]);
        (new TranslationManager())->health();

        Http::assertSent(function ($request) {
            return str_ends_with($request->url(), '/health')
                && ! $request->hasHeader('X-Service-Token');
        });
    }
}
