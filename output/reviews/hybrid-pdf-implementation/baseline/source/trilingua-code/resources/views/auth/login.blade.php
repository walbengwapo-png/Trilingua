@extends('layouts.guest')

@section('title','Sign in')

@section('styles')
    @vite(['resources/css/views/auth/login.css'])
@endsection

@section('content')
    {{-- Heading --}}
    <div class="auth-header">
        <h1>Welcome back</h1>
        <p class="auth-subtitle">Sign in to your TriLingua account.</p>
    </div>

    {{-- Success message (e.g. after password reset) --}}
    @if (session('status'))
        <div class="auth-alert auth-alert--success" role="alert">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            {{ session('status') }}
        </div>
    @endif

    {{-- Form --}}
    <form method="POST" action="{{ route('login.attempt') }}" class="auth-form">
        @csrf

        <div class="form-field">
            <label for="email">Email address</label>
            <input id="email" name="email" value="{{ old('email') }}" type="email" placeholder="you@example.com" required autofocus autocomplete="email" />
            @error('email') <p class="error-message">{{ $message }}</p> @enderror
        </div>

        <div class="form-field">
            <label for="password">Password</label>
            <div class="input-password-wrapper">
                <input id="password" name="password" type="password" placeholder="••••••••" required autocomplete="current-password" />
                <button type="button" class="btn-toggle-password" aria-label="Toggle password visibility"
                    onclick="(function(){var i=document.getElementById('password'),a=document.getElementById('icon-eye'),b=document.getElementById('icon-eye-off');if(i.type==='password'){i.type='text';a.style.display='none';b.style.display='block';}else{i.type='password';a.style.display='block';b.style.display='none';}})()">
                    <svg id="icon-eye" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                    </svg>
                    <svg id="icon-eye-off" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:none">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>
                    </svg>
                </button>
            </div>
            @error('password') <p class="error-message">{{ $message }}</p> @enderror
        </div>

        <div class="auth-forgot">
            <a href="{{ route('password.request') }}" class="link-underline">Forgot password?</a>
        </div>

        <button type="submit" class="btn-auth">Sign in</button>

        @if (config('services.google.client_id'))
        <div class="divider-text">or continue with</div>

        <div class="social-buttons">
            <a href="{{ route('auth.google.redirect') }}" class="btn-social btn-social--google" aria-label="Continue with Google">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M21 12.24c0-.68-.06-1.34-.17-1.98H12v3.75h4.96c-.21 1.13-.86 2.09-1.83 2.74v2.28h2.96c1.74-1.6 2.74-3.98 2.74-6.79z" fill="#4285F4"/>
                    <path d="M12 22c2.7 0 4.98-.9 6.64-2.44l-2.96-2.28c-.82.55-1.86.88-3.68.88-2.83 0-5.23-1.9-6.09-4.44H1.9v2.79C3.54 19.93 7.48 22 12 22z" fill="#34A853"/>
                    <path d="M5.91 13.72A7.01 7.01 0 015.6 12c0-.72.12-1.41.31-2.06V7.15H1.9A10 10 0 0012 2c2.7 0 4.98.9 6.64 2.44l-2.96 2.28C14.96 6.9 13.92 6.6 12 6.6c-3.3 0-6.11 1.98-7.19 4.86l1.1 2.26z" fill="#FBBC05"/>
                </svg>
                Continue with Google
            </a>
        </div>
        @endif

        <p class="auth-footer">
            Not a member? <a href="{{ route('register') }}" class="link-bold">Sign up</a>
        </p>
    </form>
@endsection
