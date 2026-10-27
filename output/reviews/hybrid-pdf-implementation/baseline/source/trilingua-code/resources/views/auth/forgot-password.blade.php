@extends('layouts.guest')

@section('title', 'Forgot Password')

@section('styles')
    @vite(['resources/css/views/auth/login.css'])
@endsection

@section('content')
    <div class="auth-header">
        <h1>Forgot password?</h1>
        <p class="auth-subtitle">Enter your email and we'll send you a reset link.</p>
    </div>

    {{-- Success message --}}
    @if (session('status'))
        <div class="auth-alert auth-alert--success" role="alert">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            {{ session('status') }}
        </div>
    @endif

    <form method="POST" action="{{ route('password.email') }}" class="auth-form">
        @csrf

        <div class="form-field">
            <label for="email">Email address</label>
            <input id="email" name="email" type="email" value="{{ old('email') }}"
                   placeholder="you@example.com" required autofocus autocomplete="email" />
            @error('email') <p class="error-message">{{ $message }}</p> @enderror
        </div>

        <button type="submit" class="btn-auth">Send reset link</button>

        <p class="auth-footer">
            Remember your password? <a href="{{ route('login') }}" class="link-bold">Sign in</a>
        </p>
    </form>
@endsection
