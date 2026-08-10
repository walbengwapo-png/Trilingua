@extends('layouts.app')

@section('title', 'Settings')

@section('styles')
    @vite(['resources/css/views/settings.css'])
@endsection

@section('content')
<div class="settings-layout">

    {{-- Sidebar --}}
    <aside class="settings-sidebar">
        <h2 class="settings-sidebar-title">Settings</h2>
        <nav class="settings-nav">
            <button
                type="button"
                class="settings-nav-link {{ !session('_settings_section') || session('_settings_section') === 'account' ? 'active' : '' }}"
                data-section="account"
                onclick="showSection('account', this)"
            >
                Account Settings
            </button>
            <button
                type="button"
                class="settings-nav-link {{ session('_settings_section') === 'general' ? 'active' : '' }}"
                data-section="general"
                onclick="showSection('general', this)"
            >
                General Settings
            </button>
        </nav>
    </aside>

    {{-- Content Area --}}
    <div class="settings-content">

        {{-- ===================== ACCOUNT SECTION ===================== --}}
        <div
            id="section-account"
            class="settings-section"
            style="{{ session('_settings_section') === 'general' ? 'display:none' : 'display:block' }}"
        >

            {{-- Account Information --}}
            <div class="settings-card">
                <h3 class="settings-card-title">Account Information</h3>
                <p class="settings-card-description">Update your name and email address.</p>

                @if (session('success'))
                    <div class="alert alert-success">
                        {{ session('success') }}
                    </div>
                @endif

                <form method="POST" action="{{ route('settings.account') }}" class="settings-form">
                    @csrf

                    <div class="form-field">
                        <label for="name" class="form-label">Name</label>
                        <input
                            id="name"
                            name="name"
                            type="text"
                            class="form-input {{ $errors->has('name') ? 'input-error' : '' }}"
                            value="{{ old('name', $user->name) }}"
                            required
                            autocomplete="name"
                        />
                        @error('name')
                            <p class="error-message">{{ $message }}</p>
                        @enderror
                    </div>

                    <div class="form-field">
                        <label for="email" class="form-label">Email Address</label>
                        <input
                            id="email"
                            name="email"
                            type="email"
                            class="form-input {{ $errors->has('email') ? 'input-error' : '' }}"
                            value="{{ old('email', $user->email) }}"
                            required
                            autocomplete="email"
                        />
                        @error('email')
                            <p class="error-message">{{ $message }}</p>
                        @enderror
                    </div>

                    <div class="form-actions">
                        <button type="submit" class="btn primary">Save Changes</button>
                    </div>
                </form>
            </div>

            {{-- Password Change --}}
            <div class="settings-card">
                <h3 class="settings-card-title">Change Password</h3>
                <p class="settings-card-description">Ensure your account is using a strong password.</p>

                @if (session('password_success'))
                    <div class="alert alert-success">
                        {{ session('password_success') }}
                    </div>
                @endif

                <form method="POST" action="{{ route('settings.password') }}" class="settings-form">
                    @csrf

                    <div class="form-field">
                        <label for="current_password" class="form-label">Current Password</label>
                        <input
                            id="current_password"
                            name="current_password"
                            type="password"
                            class="form-input {{ $errors->has('current_password') ? 'input-error' : '' }}"
                            required
                            autocomplete="current-password"
                        />
                        @error('current_password')
                            <p class="error-message">{{ $message }}</p>
                        @enderror
                    </div>

                    <div class="form-field">
                        <label for="password" class="form-label">New Password</label>
                        <input
                            id="password"
                            name="password"
                            type="password"
                            class="form-input {{ $errors->has('password') ? 'input-error' : '' }}"
                            required
                            autocomplete="new-password"
                        />
                        @error('password')
                            <p class="error-message">{{ $message }}</p>
                        @enderror
                    </div>

                    <div class="form-field">
                        <label for="password_confirmation" class="form-label">Confirm New Password</label>
                        <input
                            id="password_confirmation"
                            name="password_confirmation"
                            type="password"
                            class="form-input"
                            required
                            autocomplete="new-password"
                        />
                    </div>

                    <div class="form-actions">
                        <button type="submit" class="btn primary">Update Password</button>
                    </div>
                </form>
            </div>

        </div>{{-- end #section-account --}}

        {{-- ===================== GENERAL SECTION ===================== --}}
        <div
            id="section-general"
            class="settings-section"
            style="{{ session('_settings_section') === 'general' ? 'display:block' : 'display:none' }}"
        >

            <div class="settings-card">
                <h3 class="settings-card-title">General Preferences</h3>
                <p class="settings-card-description">Customize the appearance of the application.</p>

                @if (session('general_success'))
                    <div class="alert alert-success">
                        {{ session('general_success') }}
                    </div>
                @endif

                <form method="POST" action="{{ route('settings.general') }}" class="settings-form">
                    @csrf

                    {{-- Theme --}}
                    <div class="form-field">
                        <label for="theme" class="form-label">Theme</label>
                        <select
                            id="theme"
                            name="theme"
                            class="form-input {{ $errors->has('theme') ? 'input-error' : '' }}"
                        >
                            <option value="light" {{ old('theme', $user->theme ?? 'light') === 'light' ? 'selected' : '' }}>
                                Light
                            </option>
                            <option value="dark" {{ old('theme', $user->theme ?? 'light') === 'dark' ? 'selected' : '' }}>
                                Dark
                            </option>
                        </select>
                        @error('theme')
                            <p class="error-message">{{ $message }}</p>
                        @enderror
                    </div>

                    <div class="form-actions">
                        <button type="submit" class="btn primary">Save Preferences</button>
                    </div>
                </form>
            </div>

        </div>{{-- end #section-general --}}

    </div>{{-- end .settings-content --}}

</div>{{-- end .settings-layout --}}

<script>
    function showSection(section, btn) {
        // Hide all sections
        document.querySelectorAll('.settings-section').forEach(function (el) {
            el.style.display = 'none';
        });

        // Remove active from all nav links
        document.querySelectorAll('.settings-nav-link').forEach(function (el) {
            el.classList.remove('active');
        });

        // Show the selected section
        var target = document.getElementById('section-' + section);
        if (target) {
            target.style.display = 'block';
        }

        // Mark the clicked button as active
        if (btn) {
            btn.classList.add('active');
        }
    }

    // On page load, ensure the correct section is visible based on initial state
    (function () {
        var activeBtn = document.querySelector('.settings-nav-link.active');
        if (activeBtn) {
            var section = activeBtn.getAttribute('data-section');
            document.querySelectorAll('.settings-section').forEach(function (el) {
                el.style.display = 'none';
            });
            var target = document.getElementById('section-' + section);
            if (target) {
                target.style.display = 'block';
            }
        }
    })();
</script>
@endsection
