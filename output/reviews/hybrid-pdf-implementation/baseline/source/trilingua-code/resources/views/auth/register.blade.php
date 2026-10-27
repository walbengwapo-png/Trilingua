@extends('layouts.guest')

@section('title','Create account')

@section('styles')
    @vite(['resources/css/views/auth/register.css'])
@endsection

@section('content')
    {{-- Heading --}}
    <div class="auth-header">
        <h1>Create account</h1>
        <p class="auth-subtitle">Join TriLingua and start translating today.</p>
    </div>

    {{-- Form --}}
    <form method="POST" action="{{ route('register.store') }}" class="auth-form">
        @csrf

        <div class="form-field">
            <label for="name">Full name</label>
            <input id="name" name="name" value="{{ old('name') }}" type="text" placeholder="Your name" required autofocus autocomplete="name" />
            @error('name') <p class="error-message">{{ $message }}</p> @enderror
        </div>

        <div class="form-field">
            <label for="email">Email address</label>
            <input id="email" name="email" value="{{ old('email') }}" type="email" placeholder="you@example.com" required autocomplete="email" />
            @error('email') <p class="error-message">{{ $message }}</p> @enderror
        </div>

        <div class="form-field">
            <label for="password">Password</label>
            <input id="password" name="password" type="password" placeholder="Min. 8 characters" required autocomplete="new-password" />
            <div class="password-strength" id="password-strength" aria-live="polite">
                <div class="password-strength__bar">
                    <div class="password-strength__fill" id="strength-fill"></div>
                </div>
                <span class="password-strength__label" id="strength-label"></span>
            </div>
            <span class="field-hint">Must include uppercase, lowercase, number and symbol.</span>
            @error('password') <p class="error-message">{{ $message }}</p> @enderror
        </div>

        <div class="form-field">
            <label for="password_confirmation">Confirm password</label>
            <input id="password_confirmation" name="password_confirmation" type="password" placeholder="Repeat your password" required autocomplete="new-password" />
        </div>

        <button type="submit" class="btn-auth">Create account</button>

        @if (config('services.google.client_id'))
        <div class="divider-text">or continue with</div>

        <div class="social-buttons">
            <a href="{{ route('auth.google.redirect') }}" class="btn-social btn-social--google" aria-label="Sign up with Google">
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
            Already a member? <a href="{{ route('login') }}" class="link-bold">Sign in</a>
        </p>
    </form>

<script>
(function () {
    var input  = document.getElementById('password');
    var fill   = document.getElementById('strength-fill');
    var label  = document.getElementById('strength-label');
    if (!input || !fill || !label) return;

    function score(pw) {
        var s = 0;
        if (pw.length >= 8)  s++;
        if (pw.length >= 12) s++;
        if (/[A-Z]/.test(pw)) s++;
        if (/[a-z]/.test(pw)) s++;
        if (/[0-9]/.test(pw)) s++;
        if (/[^A-Za-z0-9]/.test(pw)) s++;
        return s;
    }

    var levels = [
        { max: 1, label: 'Too weak',  color: '#ef4444', width: '15%' },
        { max: 2, label: 'Weak',      color: '#f97316', width: '30%' },
        { max: 3, label: 'Fair',      color: '#f59e0b', width: '55%' },
        { max: 4, label: 'Good',      color: '#84cc16', width: '75%' },
        { max: 6, label: 'Strong',    color: '#10b981', width: '100%' }
    ];

    input.addEventListener('input', function () {
        var pw = input.value;
        if (!pw) { fill.style.width = '0'; label.textContent = ''; return; }
        var s = score(pw);
        var lvl = levels.find(function (l) { return s <= l.max; }) || levels[levels.length - 1];
        fill.style.width = lvl.width;
        fill.style.background = lvl.color;
        label.textContent = lvl.label;
        label.style.color = lvl.color;
    });
})();
</script>
@endsection
