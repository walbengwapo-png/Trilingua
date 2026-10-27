<?php

namespace Tests\Feature;

use App\Http\Middleware\ValidateSession;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;
use Tests\TestCase;

/**
 * Feature tests for ValidateSession's coarse browser fingerprint logic.
 *
 * Covers:
 *  - Fingerprint parsing from Chromium client hints (sec-ch-ua).
 *  - Fingerprint parsing from the traditional User-Agent string (Firefox,
 *    Safari, and any client that never sends sec-ch-ua).
 *  - Same-browser repeat requests must NOT log the user out, for both paths.
 *  - A genuine fingerprint mismatch rotates the session ID (destroying the old
 *    session's data) WITHOUT logging the user out.
 */
class ValidateSessionTest extends TestCase
{
    use RefreshDatabase;

    private const CHROME_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';
    private const CHROME_SEC_CH_UA = '"Chromium";v="126", "Google Chrome";v="126", "Not.A/Brand";v="8"';
    private const FIREFOX_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0';
    private const SAFARI_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15';

    /**
     * Build a request with the given HTTP server variables (headers).
     */
    private function makeRequest(array $server = []): Request
    {
        return Request::create('/dashboard', 'GET', [], [], [], array_merge([
            'HTTP_HOST' => 'localhost',
        ], $server));
    }

    /**
     * Run the middleware over a request wired to a given session store.
     */
    private function runMiddleware(Request $request, $session): Response
    {
        $request->setLaravelSession($session);

        return (new ValidateSession())->handle(
            $request,
            fn ($req) => new Response('ok')
        );
    }

    // -------------------------------------------------------------------------
    // Fingerprint parsing
    // -------------------------------------------------------------------------

    public function test_sec_ch_ua_path_parses_chrome(): void
    {
        $request = $this->makeRequest([
            'HTTP_SEC_CH_UA'          => self::CHROME_SEC_CH_UA,
            'HTTP_SEC_CH_UA_PLATFORM' => '"Windows"',
            'HTTP_USER_AGENT'         => self::CHROME_UA,
        ]);

        $this->assertSame('chrome|126|windows', (new ValidateSession())->buildFingerprint($request));
    }

    public function test_sec_ch_ua_path_parses_edge(): void
    {
        $request = $this->makeRequest([
            'HTTP_SEC_CH_UA'          => '"Not.A/Brand";v="8", "Chromium";v="126", "Microsoft Edge";v="126"',
            'HTTP_SEC_CH_UA_PLATFORM' => '"macOS"',
            'HTTP_USER_AGENT'         => 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0',
        ]);

        $this->assertSame('edge|126|macos', (new ValidateSession())->buildFingerprint($request));
    }

    public function test_ua_fallback_path_parses_firefox(): void
    {
        $request = $this->makeRequest(['HTTP_USER_AGENT' => self::FIREFOX_UA]);

        $this->assertSame('firefox|120|windows', (new ValidateSession())->buildFingerprint($request));
    }

    public function test_ua_fallback_path_parses_safari(): void
    {
        $request = $this->makeRequest(['HTTP_USER_AGENT' => self::SAFARI_UA]);

        $this->assertSame('safari|17|macos', (new ValidateSession())->buildFingerprint($request));
    }

    public function test_ua_fallback_path_parses_legacy_ie(): void
    {
        $request = $this->makeRequest([
            'HTTP_USER_AGENT' => 'Mozilla/5.0 (Windows NT 6.1; Trident/7.0; rv:11.0) like Gecko',
        ]);

        $this->assertSame('ie|11|windows', (new ValidateSession())->buildFingerprint($request));
    }

    // -------------------------------------------------------------------------
    // Same-browser repeat requests must not log the user out
    // -------------------------------------------------------------------------

    public function test_same_browser_with_sec_ch_ua_is_not_logged_out(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);

        $session = $this->app['session']->driver();
        $session->start();
        $session->put('session_fingerprint', 'chrome|126|windows');

        $before = $session->getId();
        $request = $this->makeRequest([
            'HTTP_SEC_CH_UA'          => self::CHROME_SEC_CH_UA,
            'HTTP_SEC_CH_UA_PLATFORM' => '"Windows"',
            'HTTP_USER_AGENT'         => self::CHROME_UA,
        ]);

        $response = $this->runMiddleware($request, $session);

        $this->assertSame(200, $response->getStatusCode());
        $this->assertAuthenticated();
        $this->assertSame($before, $session->getId(), 'session must NOT be rotated for a same-browser repeat request');
    }

    public function test_same_browser_with_firefox_ua_fallback_is_not_logged_out(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);

        $session = $this->app['session']->driver();
        $session->start();
        $session->put('session_fingerprint', 'firefox|120|windows');

        $before = $session->getId();
        $request = $this->makeRequest(['HTTP_USER_AGENT' => self::FIREFOX_UA]);

        $response = $this->runMiddleware($request, $session);

        $this->assertSame(200, $response->getStatusCode());
        $this->assertAuthenticated();
        $this->assertSame($before, $session->getId(), 'session must NOT be rotated for a same-browser repeat request');
    }

    // -------------------------------------------------------------------------
    // Mismatch: rotate session ID (destroy old) but keep the user logged in
    // -------------------------------------------------------------------------

    public function test_fingerprint_mismatch_rotates_session_but_keeps_auth(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);

        $session = $this->app['session']->driver();
        $session->start();
        $session->put('session_fingerprint', 'firefox|120|windows');

        $before = $session->getId();
        $request = $this->makeRequest([
            'HTTP_SEC_CH_UA'          => self::CHROME_SEC_CH_UA,
            'HTTP_SEC_CH_UA_PLATFORM' => '"Windows"',
            'HTTP_USER_AGENT'         => self::CHROME_UA,
        ]);

        $response = $this->runMiddleware($request, $session);

        $this->assertSame(200, $response->getStatusCode());
        $this->assertAuthenticated();
        $this->assertNotSame($before, $session->getId(), 'session ID must be rotated on a fingerprint mismatch');
        $this->assertSame('chrome|126|windows', $session->get('session_fingerprint'), 'new fingerprint must be stored');
    }

    public function test_first_request_after_deploy_stores_fingerprint_without_logout(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);

        $session = $this->app['session']->driver();
        $session->start();
        $this->assertNull($session->get('session_fingerprint'));

        $request = $this->makeRequest(['HTTP_USER_AGENT' => self::FIREFOX_UA]);

        $response = $this->runMiddleware($request, $session);

        $this->assertSame(200, $response->getStatusCode());
        $this->assertAuthenticated();
        $this->assertSame('firefox|120|windows', $session->get('session_fingerprint'));
    }

    // -------------------------------------------------------------------------
    // End-to-end through the HTTP stack
    // -------------------------------------------------------------------------

    public function test_http_repeat_request_with_same_sec_ch_ua_stays_authenticated(): void
    {
        $user = User::factory()->create();

        $headers = [
            'SEC_CH_UA'          => self::CHROME_SEC_CH_UA,
            'SEC_CH_UA_PLATFORM' => '"Windows"',
            'USER_AGENT'         => self::CHROME_UA,
        ];

        $this->actingAs($user)->get('/dashboard', $headers)->assertOk();
        $this->assertAuthenticated();

        $this->actingAs($user)->get('/dashboard', $headers)->assertOk();
        $this->assertAuthenticated();
    }

    public function test_http_repeat_request_with_firefox_ua_stays_authenticated(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)->get('/dashboard', ['USER_AGENT' => self::FIREFOX_UA])->assertOk();
        $this->assertAuthenticated();

        $this->actingAs($user)->get('/dashboard', ['USER_AGENT' => self::FIREFOX_UA])->assertOk();
        $this->assertAuthenticated();
    }
}
