@extends('layouts.guest')

@section('title', 'Reset Password')

@section('styles')
    @vite(['resources/css/views/auth/login.css'])
@endsection

@section('content')
    <div class="auth-header">
        <h1>Set new password</h1>
        <p class="auth-subtitle">Choose a strong password for your account.</p>
    </div>

    <form method="POST" action="{{ route('password.update') }}" class="auth-form">
        @csrf

        <input type="hidden" name="token" value="{{ $token }}">

        <div class="form-field">
            <label for="email">Email address</label>
            <input id="email" name="email" type="email" value="{{ old('email', $email) }}"
                   placeholder="you@example.com" required autocomplete="email" />
            @error('email') <p class="error-message">{{ $message }}</p> @enderror
        </div>

        <div class="form-field">
            <label for="password">New password</label>
            <input id="password" name="password" type="password"
                   placeholder="Min. 8 characters" required autocomplete="new-password" />
            <div class="password-strength" id="password-strength" aria-live="polite">
                <div class="password-strength__bar">
                    <div class="password-strength__fill" id="strength-fill"></div>
                </div>
                <span class="password-strength__label" id="strength-label"></span>
            </div>
            @error('password') <p class="error-message">{{ $message }}</p> @enderror
        </div>

        <div class="form-field">
            <label for="password_confirmation">Confirm new password</label>
            <input id="password_confirmation" name="password_confirmation" type="password"
                   placeholder="Repeat your password" required autocomplete="new-password" />
        </div>

        <button type="submit" class="btn-auth">Reset password</button>
    </form>

<script>
(function () {
    var input = document.getElementById('password');
    var fill  = document.getElementById('strength-fill');
    var label = document.getElementById('strength-label');
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
        { max: 6, label: 'Strong',    color: '#10b981', width: '100%' },
    ];

    input.addEventListener('input', function () {
        var pw = input.value;
        if (!pw) { fill.style.width = '0'; label.textContent = ''; return; }
        var s   = score(pw);
        var lvl = levels.find(function (l) { return s <= l.max; }) || levels[levels.length - 1];
        fill.style.width      = lvl.width;
        fill.style.background = lvl.color;
        label.textContent     = lvl.label;
        label.style.color     = lvl.color;
    });
})();
</script>
@endsection
