<?php

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Password;

class ForgotPasswordController extends Controller
{
    /**
     * Show the forgot password form.
     */
    public function show()
    {
        return view('auth.forgot-password');
    }

    /**
     * Send a password reset link to the given email.
     */
    public function send(Request $request)
    {
        $request->validate([
            'email' => ['required', 'email'],
        ]);

        // We always return the same message to prevent email enumeration.
        Password::sendResetLink($request->only('email'));

        return back()->with('status', 'If an account with that email exists, we\'ve sent a password reset link.');
    }
}
