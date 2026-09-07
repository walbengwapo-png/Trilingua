<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
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
            \Log::info('User agent changed', [
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
            \Log::info('User IP address changed', [
                'user_id' => Auth::id(),
                'old_ip' => $storedIp,
                'new_ip' => $request->ip(),
            ]);
            $request->session()->put('ip_address', $request->ip());
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
}