<?php

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Models\User;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Validation\Rules\Password;

class RegisterController extends Controller
{
    /**
     * Maximum registration attempts per IP
     */
    protected int $maxAttempts = 3;

    /**
     * Throttle duration in minutes
     */
    protected int $decayMinutes = 60;

    public function show()
    {
        return view('auth.register');
    }

    public function store(Request $request)
    {
        // Rate limit registration attempts by IP
        $throttleKey = 'register:'.$request->ip();
        
        if (RateLimiter::tooManyAttempts($throttleKey, $this->maxAttempts)) {
            $seconds = RateLimiter::availableIn($throttleKey);
            $minutes = ceil($seconds / 60);
            
            return back()->withErrors([
                'email' => "Too many registration attempts. Please try again in {$minutes} minutes.",
            ])->withInput($request->except('password', 'password_confirmation'));
        }

        // Validate input with strong password requirements
        $validated = $request->validate([
            'name' => ['required', 'string', 'max:255', 'regex:/^[a-zA-Z\s]+$/'],
            'email' => ['required', 'string', 'email', 'max:255', 'unique:users'],
            'password' => [
                'required',
                'string',
                'confirmed',
                Password::min(8)
                    ->mixedCase()
                    ->numbers()
                    ->symbols(),
            ],
        ], [
            'name.regex' => 'The name may only contain letters and spaces.',
            'password.min' => 'Password must be at least 8 characters.',
        ]);

        // Increment rate limiter
        RateLimiter::hit($throttleKey, $this->decayMinutes * 60);

        // Create user with hashed password
        $user = User::create([
            'name' => $validated['name'],
            'email' => $validated['email'],
            'password' => Hash::make($validated['password']),
        ]);

        // Log the user in
        Auth::login($user);

        // Regenerate session to prevent session fixation
        $request->session()->regenerate();
        
        // Store security metadata
        $request->session()->put([
            'user_agent' => $request->userAgent(),
            'ip_address' => $request->ip(),
            'last_activity' => now(),
        ]);

        // Log successful registration for security monitoring
        \Log::info('New user registered', [
            'user_id' => $user->id,
            'email' => $user->email,
            'ip' => $request->ip(),
        ]);

        return redirect()->route('dashboard')->with('login_success', true);
    }
}
