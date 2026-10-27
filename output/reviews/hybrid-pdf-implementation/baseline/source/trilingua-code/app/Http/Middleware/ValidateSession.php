<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

class ValidateSession
{
    /**
     * Handle an incoming request.
     *
     * @param  \Closure(\Illuminate\Http\Request): (\Symfony\Component\HttpFoundation\Response)  $next
     */
    public function handle(Request $request, Closure $next): Response
    {
        // Skip validation for guest users
        if (!Auth::check()) {
            return $next($request);
        }

        $dirty = false;

        // Validate user agent hasn't changed (prevents session hijacking)
        $storedUserAgent = $request->session()->get('user_agent');
        if ($storedUserAgent && $storedUserAgent !== $request->userAgent()) {
            Log::info('User agent changed', [
                'user_id' => Auth::id(),
                'stored_agent' => $storedUserAgent,
                'current_agent' => $request->userAgent(),
                'ip' => $request->ip(),
            ]);
            $request->session()->put('user_agent', $request->userAgent());
            $dirty = true;
        }

        // Validate IP address hasn't changed drastically
        $storedIp = $request->session()->get('ip_address');
        if ($storedIp && $storedIp !== $request->ip()) {
            Log::info('User IP address changed', [
                'user_id' => Auth::id(),
                'old_ip' => $storedIp,
                'new_ip' => $request->ip(),
            ]);
            $request->session()->put('ip_address', $request->ip());
            $dirty = true;
        }

        // Coarse browser fingerprint: if the browser family/major version/OS
        // changed, rotate the session id (destroying the old session's data)
        // WITHOUT logging the user out. A changed browser half is the primary
        // session-hijacking signal.
        $fingerprint = $this->buildFingerprint($request);
        $storedFingerprint = $request->session()->get('session_fingerprint');

        if ($storedFingerprint !== null && $storedFingerprint !== $fingerprint) {
            Log::warning('Session browser fingerprint changed; rotating session', [
                'user_id' => Auth::id(),
                'stored_fingerprint' => $storedFingerprint,
                'current_fingerprint' => $fingerprint,
            ]);
            $request->session()->migrate(true);
            $request->session()->put('session_fingerprint', $fingerprint);
            $dirty = true;
        } elseif ($storedFingerprint === null) {
            // First request after enabling fingerprinting: store, don't rotate.
            $request->session()->put('session_fingerprint', $fingerprint);
            $dirty = true;
        }

        // Only touch the session (acquiring a lock) when something actually
        // changed. The old unconditional put('last_activity') forced a session
        // write on every single request, serialising all concurrent requests
        // from the same user when using the file or database session driver.
        if ($dirty) {
            $request->session()->put('last_activity', now());
        }

        return $next($request);
    }

    /**
     * Build a coarse "<browser>|<major version>|<os>" fingerprint from Client
     * Hints (sec-ch-ua) when present, falling back to the User-Agent string.
     * The granularity is intentionally coarse: only a change of browser family,
     * major version, or OS family triggers a rotation.
     */
    public function buildFingerprint(Request $request): string
    {
        $hint = $request->headers->get('sec-ch-ua');
        $platform = $request->headers->get('sec-ch-ua-platform');

        if ($hint !== null && $hint !== '') {
            $parsed = $this->parseSecChUa($hint);
            if ($parsed !== null) {
                [$browser, $version] = $parsed;
                $os = $this->normalizeOs($this->stripQuotes((string) $platform));

                return strtolower($browser) . '|' . $version . '|' . $os;
            }
        }

        return $this->parseUserAgent((string) $request->userAgent());
    }

    /**
     * @return array{0: string, 1: string}|null  [browser, major version]
     */
    private function parseSecChUa(string $header): ?array
    {
        $brands = [];
        if (preg_match_all('/([-\w.\/ ]+)\s*\/\s*"([^"]+)"/i', $header, $matches, PREG_SET_ORDER)) {
            foreach ($matches as $match) {
                $brands[trim($match[1], '" ')] = $match[2];
            }
        } elseif (preg_match_all('/"([^"]+)"\s*;\s*v\s*=\s*"([^"]+)"/', $header, $matches, PREG_SET_ORDER)) {
            foreach ($matches as $match) {
                $brands[$match[1]] = $match[2];
            }
        }

        $map = [];
        foreach ($brands as $brand => $version) {
            $map[$this->normalizeBrand($brand)] = $version;
        }

        // Prefer a specific browser over the generic Chromium scaffold.
        foreach (['edge', 'chrome', 'chromium', 'opera', 'firefox', 'safari'] as $candidate) {
            if (isset($map[$candidate])) {
                return [$candidate, (string) $map[$candidate]];
            }
        }

        return null;
    }

    private function normalizeBrand(string $brand): string
    {
        $name = strtolower(trim($brand));
        $name = str_replace(['google', 'microsoft'], '', $name);
        $name = preg_replace('/\s+/', '', $name) ?? $name;

        return match ($name) {
            'edge', 'edgechromium', 'microsoftedge' => 'edge',
            'chrome', 'chromegoogle' => 'chrome',
            'chromium' => 'chromium',
            'opera', 'opr', 'opera_network' => 'opera',
            'firefox' => 'firefox',
            'safari', 'version' => 'safari',
            default => $name,
        };
    }

    private function parseUserAgent(string $ua): string
    {
        $os = $this->osFromUserAgent($ua);

        if (preg_match('/Firefox\/(\d+)/', $ua, $m)) {
            return 'firefox|' . $m[1] . '|' . $os;
        }

        if (preg_match('/Trident\/\d[\d.]*/', $ua, $m) && preg_match('/rv:(\d+)/', $ua, $m2)) {
            return 'ie|' . $m2[1] . '|' . $os;
        }

        if (preg_match('/Edg[\e ]?\/(\d+)/', $ua, $m) || preg_match('/Edge\/(\d+)/', $ua, $m)) {
            return 'edge|' . $m[1] . '|' . $os;
        }

        if (preg_match('/OPR\/(\d+)/', $ua, $m) || preg_match('/Opera[\/ ](\d+)/', $ua, $m)) {
            return 'opera|' . $m[1] . '|' . $os;
        }

        if (preg_match('/Version\/(\d+)[\d.]*\s+Safari\//', $ua, $m)) {
            return 'safari|' . $m[1] . '|' . $os;
        }

        if (preg_match('/Chrome\/(\d+)/', $ua, $m)) {
            return 'chrome|' . $m[1] . '|' . $os;
        }

        return 'unknown|0|' . $os;
    }

    private function osFromUserAgent(string $ua): string
    {
        $ua = strtolower($ua);

        if (str_contains($ua, 'windows')) {
            return 'windows';
        }
        if (str_contains($ua, 'iphone') || str_contains($ua, 'ipad')) {
            return 'ios';
        }
        if (str_contains($ua, 'mac os x') || str_contains($ua, 'macintosh')) {
            return 'macos';
        }
        if (str_contains($ua, 'android')) {
            return 'android';
        }
        if (str_contains($ua, 'linux') || str_contains($ua, 'x11') || str_contains($ua, 'cros')) {
            return 'linux';
        }

        return 'unknown';
    }

    private function normalizeOs(string $os): string
    {
        $os = strtolower(trim($os));
        $os = str_replace(['"', ' '], '', $os);

        return match ($os) {
            'windows' => 'windows',
            'macos', 'macosx' => 'macos',
            'android' => 'android',
            'ios', 'iphoneos' => 'ios',
            'linux' => 'linux',
            default => 'unknown',
        };
    }

    private function stripQuotes(string $value): string
    {
        return trim($value, " \"");
    }
}