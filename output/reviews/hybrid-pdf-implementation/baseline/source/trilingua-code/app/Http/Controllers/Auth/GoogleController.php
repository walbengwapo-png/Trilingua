<?php

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Models\User;
use App\Models\UserActivityLog;
use Illuminate\Http\RedirectResponse;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Laravel\Socialite\Facades\Socialite;

/**
 * Sign in / sign up with Google via OAuth 2.0.
 *
 * The client id/secret live in config/services.php (GOOGLE_* env vars).
 * When GOOGLE_CLIENT_ID is not configured, the login/register views hide the
 * Google button, so these routes are only reachable once credentials exist.
 */
class GoogleController extends Controller
{
    /**
     * Send the user to Google's OAuth consent screen.
     */
    public function redirect(): RedirectResponse
    {
        if (blank(config('services.google.client_id'))) {
            return redirect()->route('login')->withErrors([
                'email' => 'Sign in with Google is not configured yet.',
            ]);
        }

        return Socialite::driver('google')->redirect();
    }

    /**
     * Handle Google's callback, find-or-create the user, and sign them in.
     */
    public function callback(): RedirectResponse
    {
        try {
            $googleUser = Socialite::driver('google')->user();
        } catch (\Throwable $e) {
            Log::warning('Google OAuth callback failed', [
                'exception' => $e->getMessage(),
            ]);

            return redirect()->route('login')->withErrors([
                'email' => 'Unable to sign in with Google. Please try again.',
            ]);
        }

        if ($googleUser === null || blank($googleUser->getEmail())) {
            return redirect()->route('login')->withErrors([
                'email' => 'Google did not return a valid account. Please try again.',
            ]);
        }

        $email     = mb_strtolower(trim((string) $googleUser->getEmail()));
        $googleId  = (string) $googleUser->getId();
        $name      = $googleUser->getName() ?: Str::before($email, '@');
        $avatar    = $googleUser->getAvatar();

        // Find by google_id first, then fall back to matching email so existing
        // email/password accounts are linked rather than duplicated.
        $user = User::where('google_id', $googleId)->first();

        if ($user === null) {
            $user = User::where('email', $email)->first();

            if ($user === null) {
                $user = User::create([
                    'name'     => $name,
                    'email'    => $email,
                    'password' => Str::random(40), // never surfaced anywhere
                    'google_id'=> $googleId,
                ]);
            } else {
                $user->update(['google_id' => $googleId]);
            }
        }

        Auth::login($user);
        request()->session()->regenerate();

        request()->session()->put([
            'user_agent' => request()->userAgent(),
            'ip_address' => request()->ip(),
            'last_activity' => now(),
        ]);

        $this->logActivity([
            'user_id'         => $user->id,
            'attempted_email' => $email,
            'action'          => 'login_success',
            'ip_address'      => request()->ip(),
            'user_agent'      => request()->userAgent(),
            'note'            => 'Signed in with Google.',
        ]);

        return redirect()->route('dashboard')->with('login_success', true);
    }

    /**
     * Append an entry to user_activity_log.
     */
    private function logActivity(array $data): void
    {
        UserActivityLog::create($data);
    }
}