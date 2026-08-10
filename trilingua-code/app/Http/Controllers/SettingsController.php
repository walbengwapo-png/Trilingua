<?php

namespace App\Http\Controllers;

use Illuminate\Contracts\View\View;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Log;
use App\Models\UserActivityLog;

class SettingsController extends Controller
{
    /**
     * Display the settings page.
     */
    public function show(): View
    {
        $user = Auth::user();

        return view('settings', compact('user'));
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
     * Update general settings (theme).
     */
    public function updateGeneral(Request $request): RedirectResponse
    {
        $validated = $request->validate([
            'theme' => 'required|string|in:light,dark',
        ]);

        $user = Auth::user();
        $user->update($validated);

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
