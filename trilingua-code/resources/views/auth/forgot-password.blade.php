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
        <x-notice type="success" title="Update" :message="session('status')" />
    @endif

    <form method="POST" action="{{ route('password.email') }}" class="auth-form">
        @csrf

        <div class="form-field">
            <label for="email">Email address</label>
            <input id="email" name="email" type="email" value="{{ old('email') }}"
                   placeholder="you@example.com" required autofocus autocomplete="email" />
            @error('email') <p class="error-message" role="alert">{{ \App\Support\UserMessages::readable($message) }}</p> @enderror
        </div>

        <button type="submit" class="btn-auth">Send reset link</button>

        <p class="auth-footer">
            Remember your password? <a href="{{ route('login') }}" class="link-bold">Sign in</a>
        </p>
    </form>
@endsection
