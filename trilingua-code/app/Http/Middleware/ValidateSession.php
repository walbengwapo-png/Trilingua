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

        // Validate user agent hasn't changed (prevents session hijacking)
        $storedUserAgent = $request->session()->get('user_agent');
        if ($storedUserAgent && $storedUserAgent !== $request->userAgent()) {
            // Log the mismatch but don't log the user out - user agents can
            // legitimately change (browser updates, extensions, etc.)
            \Log::info('User agent changed', [
                'user_id' => Auth::id(),
                'stored_agent' => $storedUserAgent,
                'current_agent' => $request->userAgent(),
                'ip' => $request->ip(),
            ]);

            // Update stored user agent to prevent repeated warnings
            $request->session()->put('user_agent', $request->userAgent());
        }

        // Validate IP address hasn't changed drastically (optional, can be strict)
        $storedIp = $request->session()->get('ip_address');
        if ($storedIp && $storedIp !== $request->ip()) {
            // Log IP change but don't logout (IPs can change legitimately)
            \Log::info('User IP address changed', [
                'user_id' => Auth::id(),
                'old_ip' => $storedIp,
                'new_ip' => $request->ip(),
            ]);
            
            // Update stored IP
            $request->session()->put('ip_address', $request->ip());
        }

        // Update last activity timestamp
        $request->session()->put('last_activity', now());

        return $next($request);
    }
}