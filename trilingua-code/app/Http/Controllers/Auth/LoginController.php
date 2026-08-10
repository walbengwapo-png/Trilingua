<?php

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Models\UserActivityLog;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Illuminate\Validation\ValidationException;

class LoginController extends Controller
{
    /**
     * Maximum login attempts before throttling
     */
    protected int $maxAttempts = 5;

    /**
     * Throttle duration in minutes
     */
    protected int $decayMinutes = 15;

    public function show()
    {
        return view('auth.login');
    }

    public function login(Request $request)
    {
        // Validate input
        $request->validate([
            'email' => 'required|email',
            'password' => 'required|string',
        ]);

        // Check if too many login attempts
        if ($this->hasTooManyLoginAttempts($request)) {
            $this->fireLockoutEvent($request);
            return $this->sendLockoutResponse($request);
        }

        $credentials = $request->only('email', 'password');
        $remember = $request->boolean('remember');

        if (Auth::attempt($credentials, $remember)) {
            // Clear login attempts on successful login
            $this->clearLoginAttempts($request);

            // Log successful login
            $this->logActivity([
                'user_id'         => Auth::id(),
                'attempted_email' => $request->input('email'),
                'action'          => 'login_success',
                'ip_address'      => $request->ip(),
                'user_agent'      => $request->userAgent(),
            ]);

            // Regenerate session to prevent session fixation
            $request->session()->regenerate();

            // Store additional security metadata
            $request->session()->put([
                'user_agent' => $request->userAgent(),
                'ip_address' => $request->ip(),
                'last_activity' => now(),
            ]);

            return redirect()->intended(route('dashboard'))->with('login_success', true);
        }

        // Log failed login
        $this->logActivity([
            'user_id'         => null,
            'attempted_email' => $request->input('email'),
            'action'          => 'login_failed',
            'ip_address'      => $request->ip(),
            'user_agent'      => $request->userAgent(),
        ]);

        // Increment login attempts on failure
        $this->incrementLoginAttempts($request);

        return back()->withErrors([
            'email' => 'The provided credentials do not match our records.',
        ])->onlyInput('email');
    }

    public function logout(Request $request)
    {
        // Log logout before destroying the session
        $this->logActivity([
            'user_id'    => Auth::id(),
            'action'     => 'logout',
            'ip_address' => $request->ip(),
            'user_agent' => $request->userAgent(),
        ]);

        Auth::logout();

        // Invalidate session and regenerate CSRF token
        $request->session()->invalidate();
        $request->session()->regenerateToken();

        return redirect()->route('login');
    }

    /**
     * Get the throttle key for the given request.
     */
    protected function throttleKey(Request $request): string
    {
        return Str::transliterate(Str::lower($request->input('email')).'|'.$request->ip());
    }

    /**
     * Determine if the user has too many failed login attempts.
     */
    protected function hasTooManyLoginAttempts(Request $request): bool
    {
        return RateLimiter::tooManyAttempts(
            $this->throttleKey($request),
            $this->maxAttempts
        );
    }

    /**
     * Increment the login attempts for the user.
     */
    protected function incrementLoginAttempts(Request $request): void
    {
        RateLimiter::hit(
            $this->throttleKey($request),
            $this->decayMinutes * 60
        );
    }

    /**
     * Clear the login locks for the given user credentials.
     */
    protected function clearLoginAttempts(Request $request): void
    {
        RateLimiter::clear($this->throttleKey($request));
    }

    /**
     * Fire an event when a lockout occurs.
     */
    protected function fireLockoutEvent(Request $request): void
    {
        // Log the lockout event for security monitoring
        \Log::warning('Login lockout', [
            'email' => $request->input('email'),
            'ip' => $request->ip(),
            'user_agent' => $request->userAgent(),
        ]);
    }

    /**
     * Append an entry to user_activity_log.
     */
    private function logActivity(array $data): void
    {
        UserActivityLog::create($data);
    }

    /**
     * Redirect the user after determining they are locked out.
     */
    protected function sendLockoutResponse(Request $request)
    {
        $seconds = RateLimiter::availableIn($this->throttleKey($request));
        $minutes = ceil($seconds / 60);

        throw ValidationException::withMessages([
            'email' => [
                "Too many login attempts. Please try again in {$minutes} minutes.",
            ],
        ])->status(429);
    }
}
