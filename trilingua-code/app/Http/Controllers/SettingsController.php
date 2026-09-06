<?php

namespace App\Http\Controllers;

use Illuminate\Contracts\View\View;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Log;
use App\Models\UserActivityLog;
use App\Support\UserPreferences;

class SettingsController extends Controller
{
    /**
     * Display the settings page.
     *
     * Supports an optional ?section=account query param (used by the Profile
     * link in the header dropdown) which is remembered in the session so the
     * settings view opens on that section.
     */
    public function show(Request $request): View
    {
        $user = Auth::user();
        $scrollToAccount = false;

        if ($request->has('section')) {
            $request->validate(['section' => 'string|in:account,general']);
            session(['_settings_section' => $request->query('section')]);
            $scrollToAccount = $request->query('section') === 'account';
        }

        $preferences = $user->resolvedPreferences();

        return view('settings', compact('user', 'scrollToAccount', 'preferences'));
    }

    /**
     * Update account information (name, email).
     */
    public function updateAccount(Request $request): RedirectResponse
    {
        $user = Auth::user();

        $validated = $request->validate([
            'name' => 'required|string|max:255',
            'email' => 'required|string|email|unique:users,email,' . $user->id,
        ]);

        // Capture previous values for audit trail
        $previousName = $user->name;
        $previousEmail = $user->email;

        $user->update($validated);

        // Log changed fields
        if ($previousName !== $validated['name']) {
            $this->logActivity([
                'user_id'       => Auth::id(),
                'action'        => 'account_updated',
                'ip_address'    => $request->ip(),
                'user_agent'    => $request->userAgent(),
                'previous_value'=> 'name: ' . $previousName,
                'new_value'     => 'name: ' . $validated['name'],
            ]);
        }
        if ($previousEmail !== $validated['email']) {
            $this->logActivity([
                'user_id'       => Auth::id(),
                'action'        => 'account_updated',
                'ip_address'    => $request->ip(),
                'user_agent'    => $request->userAgent(),
                'previous_value'=> 'email: ' . $previousEmail,
                'new_value'     => 'email: ' . $validated['email'],
            ]);
        }

        return back()->with('success', 'Account information updated successfully.');
    }

    /**
     * Update password.
     */
    public function updatePassword(Request $request): RedirectResponse
    {
        $request->validate([
            'current_password' => ['required', 'string', 'current_password'],
            'password' => ['required', 'string', 'min:8', 'confirmed'],
            'password_confirmation' => ['required', 'string'],
        ]);

        $user = Auth::user();
        $user->update([
            'password' => Hash::make($request->password),
        ]);

        // Log password change (never log password content)
        $this->logActivity([
            'user_id'       => Auth::id(),
            'action'        => 'password_changed',
            'ip_address'    => $request->ip(),
            'user_agent'    => $request->userAgent(),
            'previous_value'=> null,
            'new_value'     => null,
            'note'          => 'Password was changed.',
        ]);

        return back()->with('password_success', 'Password updated successfully.');
    }

    /**
     * Update durable translation, date, notification, accessibility, and theme
     * preferences. They deliberately live in one JSON field so adding a
     * preference does not require another user-schema change.
     */
    public function updateGeneral(Request $request): RedirectResponse
    {
        $user = Auth::user();
        $defaults = $user->resolvedPreferences();
        $validated = $request->validate([
            'theme' => 'required|string|in:light,dark',
            // These are optional at the HTTP boundary for backwards
            // compatibility with the original theme-only settings form.
            'source_language' => 'nullable|string|in:English,Cebuano,Filipino',
            'target_language' => 'nullable|string|in:English,Cebuano,Filipino',
            'translation_mode' => 'nullable|string|in:fast,balanced,thorough',
            'timezone' => 'nullable|timezone',
            'date_format' => 'nullable|string|in:M j, Y g:i A T,Y-m-d H:i T',
            'notifications.translation_complete' => 'nullable|boolean',
            'notifications.review_updates' => 'nullable|boolean',
            'reduced_motion' => 'nullable|boolean',
        ]);

        $sourceLanguage = $validated['source_language'] ?? $defaults['source_language'];
        $targetLanguage = $validated['target_language'] ?? $defaults['target_language'];
        if ($sourceLanguage === $targetLanguage) {
            return back()->withErrors(['target_language' => 'The default source and target languages must be different.'])->withInput();
        }
        $preferences = UserPreferences::normalize(array_merge($user->preferences ?? [], [
            'source_language' => $sourceLanguage,
            'target_language' => $targetLanguage,
            'translation_mode' => $validated['translation_mode'] ?? $defaults['translation_mode'],
            'timezone' => $validated['timezone'] ?? $defaults['timezone'],
            'date_format' => $validated['date_format'] ?? $defaults['date_format'],
            'notifications' => $request->has('notifications') ? [
                'translation_complete' => $request->boolean('notifications.translation_complete'),
                'review_updates' => $request->boolean('notifications.review_updates'),
            ] : $defaults['notifications'],
            'reduced_motion' => $request->has('reduced_motion') ? $request->boolean('reduced_motion') : $defaults['reduced_motion'],
            'theme' => $validated['theme'],
        ]));
        $user->update(['theme' => $validated['theme'], 'preferences' => $preferences]);

        return back()->with('general_success', 'General settings updated successfully.');
    }

    /**
     * Append an entry to user_activity_log.
     */
    private function logActivity(array $data): void
    {
        UserActivityLog::create($data);
    }
}
