<!doctype html>
<html lang="en" data-theme="{{ auth()->user()->theme ?? 'light' }}" data-timezone="{{ auth()->user()->resolvedPreferences()['timezone'] ?? config('app.timezone') }}" @if(auth()->user()->resolvedPreferences()['reduced_motion'] ?? false) data-reduced-motion="true" @endif>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script>
        try { localStorage.setItem('trilingua-theme', '{{ auth()->user()->theme ?? 'light' }}'); } catch (e) {}
    </script>
    <title>@yield('title', 'Dashboard') — TriLingua</title>
    <link rel="icon" href="/favicon.svg" type="image/svg+xml">
    <link rel="icon" href="/favicon.ico" sizes="any">
    @vite(['resources/css/base.css', 'resources/css/layouts/app.css', 'resources/js/app.js'])
    @yield('styles')
    <meta name="csrf-token" content="{{ csrf_token() }}">
</head>
<body class="app-body">

{{-- Global toast container --}}
<div id="toast-container" aria-live="polite" aria-atomic="false" style="position:fixed;top:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:10px;pointer-events:none"></div>

{{-- Global error modal --}}
<div id="error-modal" class="app-error-modal" style="display:none" role="alertdialog" aria-modal="true" aria-labelledby="error-modal-title" aria-describedby="error-modal-msg">
    <div class="app-error-modal__overlay" id="error-modal-overlay"></div>
    <div class="app-error-modal__dialog">
        <button class="app-error-modal__close" id="error-modal-close" aria-label="Close">&times;</button>
        <div class="app-error-modal__icon" aria-hidden="true">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
        </div>
        <h3 class="app-error-modal__title" id="error-modal-title">Something went wrong</h3>
        <p class="app-error-modal__msg" id="error-modal-msg"></p>
        <button class="app-error-modal__btn" id="error-modal-ok">OK</button>
    </div>
</div>

{{-- Login success toast --}}
@if (session('login_success'))
<script>
    document.addEventListener('DOMContentLoaded', function () {
        showToast('success', 'Welcome back, {{ addslashes(auth()->user()->name ?? "User") }}!', 'You have successfully signed in.');
    });
</script>
@endif

{{-- Mobile top bar --}}
<div class="mobile-topbar" id="mobile-topbar">
    <a href="{{ route('dashboard') }}" class="mobile-topbar__brand">
        <div class="brand__icon" style="width:28px;height:28px;background:transparent">
            <svg width="100%" height="100%" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <circle cx="32" cy="19" r="14.5" fill="none" stroke="#ffffff" stroke-width="11"/>
                <circle cx="32" cy="19" r="14.5" fill="none" stroke="#3b82f6" stroke-width="8.5"/>
                <circle cx="20.7" cy="38.5" r="14.5" fill="none" stroke="#ffffff" stroke-width="11"/>
                <circle cx="20.7" cy="38.5" r="14.5" fill="none" stroke="#10b981" stroke-width="8.5"/>
                <circle cx="43.3" cy="38.5" r="14.5" fill="none" stroke="#ffffff" stroke-width="11"/>
                <circle cx="43.3" cy="38.5" r="14.5" fill="none" stroke="#f43f5e" stroke-width="8.5"/>
                <g transform="rotate(-6 32 32)">
                    <rect x="25.5" y="24" width="13" height="16" rx="3" fill="#ffffff"/>
                    <rect x="28" y="27.5" width="8" height="2.5" rx="1.25" fill="#3b82f6"/>
                    <rect x="28" y="32" width="8" height="2.5" rx="1.25" fill="#cbd5e1"/>
                    <rect x="28" y="36.5" width="6" height="2.5" rx="1.25" fill="#cbd5e1"/>
                </g>
            </svg>
        </div>
        <span class="mobile-topbar__name">TriLingua</span>
    </a>
    <button class="hamburger" id="hamburger-btn" aria-label="Open navigation menu" aria-expanded="false" aria-controls="sidebar">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
    </button>
</div>

{{-- Sidebar overlay (mobile) --}}
<div class="sidebar-overlay" id="sidebar-overlay" aria-hidden="true"></div>

<div class="app-container">

    {{-- Sidebar --}}
    <aside class="sidebar" id="sidebar">
        {{-- Brand --}}
        <a href="{{ route('dashboard') }}" class="brand">
            <div class="brand__icon" style="background:transparent">
                <svg width="100%" height="100%" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                    <circle cx="32" cy="19" r="14.5" fill="none" stroke="#ffffff" stroke-width="11"/>
                    <circle cx="32" cy="19" r="14.5" fill="none" stroke="#3b82f6" stroke-width="8.5"/>
                    <circle cx="20.7" cy="38.5" r="14.5" fill="none" stroke="#ffffff" stroke-width="11"/>
                    <circle cx="20.7" cy="38.5" r="14.5" fill="none" stroke="#10b981" stroke-width="8.5"/>
                    <circle cx="43.3" cy="38.5" r="14.5" fill="none" stroke="#ffffff" stroke-width="11"/>
                    <circle cx="43.3" cy="38.5" r="14.5" fill="none" stroke="#f43f5e" stroke-width="8.5"/>
                    <g transform="rotate(-6 32 32)">
                        <rect x="25.5" y="24" width="13" height="16" rx="3" fill="#ffffff"/>
                        <rect x="28" y="27.5" width="8" height="2.5" rx="1.25" fill="#3b82f6"/>
                        <rect x="28" y="32" width="8" height="2.5" rx="1.25" fill="#cbd5e1"/>
                        <rect x="28" y="36.5" width="6" height="2.5" rx="1.25" fill="#cbd5e1"/>
                    </g>
                </svg>
            </div>
            <span class="brand__name">TriLingua</span>
        </a>

        {{-- Navigation --}}
        <nav class="nav" aria-label="Main navigation">

            <a href="{{ route('dashboard') }}" class="nav-link {{ request()->routeIs('dashboard') ? 'active' : '' }}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
                    <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
                </svg>
                Dashboard
            </a>

            <a href="{{ route('translate') }}" class="nav-link {{ request()->routeIs('translate*') ? 'active' : '' }}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M5 8l6 6"/><path d="M4 14l6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/>
                    <path d="M22 22l-5-10-5 10"/><path d="M14 18h6"/>
                </svg>
                New Translation
            </a>

            <a href="{{ route('documents') }}" class="nav-link {{ request()->routeIs('documents*') ? 'active' : '' }}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>
                    <line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
                </svg>
                My Documents
            </a>

            <a href="{{ route('history') }}" class="nav-link {{ request()->routeIs('history*') ? 'active' : '' }}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <circle cx="12" cy="12" r="10"/>
                    <polyline points="12 6 12 12 16 14"/>
                </svg>
                Saved Translations
            </a>

            @if(auth()->user()->is_admin)
            <a href="{{ route('admin.dashboard') }}" class="nav-link {{ request()->routeIs('admin.*') ? 'active' : '' }}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                </svg>
                Admin
            </a>
            @endif

            <a href="{{ route('settings') }}" class="nav-link {{ request()->routeIs('settings*') ? 'active' : '' }}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <circle cx="12" cy="12" r="3"/>
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                </svg>
                Settings
            </a>
        </nav>
        {{-- User section at bottom --}}
        <div class="sidebar-user">
            <div class="sidebar-user__avatar" aria-hidden="true">
                {{ strtoupper(substr(auth()->user()->name ?? 'U', 0, 1)) }}
            </div>
            <div class="sidebar-user__info">
                <div class="sidebar-user__name">{{ auth()->user()->name ?? 'User' }}</div>
                <div class="sidebar-user__role">{{ auth()->user()->roleLabel() }}</div>
            </div>
            <form method="POST" action="{{ route('logout') }}">
                @csrf
                <button type="submit" class="sidebar-logout" title="Sign out">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                        <polyline points="16 17 21 12 16 7"/>
                        <line x1="21" y1="12" x2="9" y2="12"/>
                    </svg>
                </button>
            </form>
        </div>
    </aside>

    {{-- Main content --}}
    <main class="main">
        <header class="header">
            <div class="header-left">
                <h1 class="title">@yield('title', 'Dashboard')</h1>
                <p class="header-subtitle">@yield('subtitle', '')</p>
            </div>
            <div class="header-right">
                {{-- Notification bell --}}
                <div class="notif-wrap" id="notif-wrap">
                    <button class="header-icon-btn" id="notif-btn" aria-label="Notifications" title="Notifications" aria-haspopup="true" aria-expanded="false">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
                            <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
                        </svg>
                    </button>
                    <span class="notif-badge" id="notif-badge" hidden>0</span>

                    <div class="notif-dropdown" id="notif-dropdown" aria-hidden="true">
                        <div class="notif-dropdown__head">
                            <span class="notif-dropdown__title">Notifications</span>
                            <button type="button" class="notif-dropdown__markall" id="notif-markall">Mark all read</button>
                        </div>
                        <div class="notif-dropdown__list" id="notif-list">
                            <div class="notif-dropdown__empty">Loading…</div>
                        </div>
                        <a href="{{ route('notifications.page') }}" class="notif-dropdown__viewall">View all notifications</a>
                    </div>
                </div>

                {{-- User avatar dropdown --}}
                <div class="header-user" id="header-user-btn" role="button" tabindex="0" aria-haspopup="true" aria-expanded="false">
                    <div class="header-user__avatar" aria-hidden="true">
                        {{ strtoupper(substr(auth()->user()->name ?? 'U', 0, 1)) }}
                    </div>
                    <div class="header-user__info">
                        <span class="header-user__name">{{ auth()->user()->name ?? 'User' }}</span>
                        <span class="header-user__email">{{ auth()->user()->email ?? '' }}</span>
                    </div>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="header-user__chevron">
                        <polyline points="6 9 12 15 18 9"/>
                    </svg>
                </div>

                {{-- Dropdown menu --}}
                <div class="header-dropdown" id="header-dropdown" aria-hidden="true">
                    <div class="header-dropdown__info">
                        <div class="header-dropdown__avatar" aria-hidden="true">
                            {{ strtoupper(substr(auth()->user()->name ?? 'U', 0, 1)) }}
                        </div>
                        <div>
                            <div class="header-dropdown__name">{{ auth()->user()->name ?? 'User' }}</div>
                            <div class="header-dropdown__email">{{ auth()->user()->email ?? '' }}</div>
                        </div>
                    </div>
                    <div class="header-dropdown__divider"></div>
                    <a href="{{ route('profile') }}" class="header-dropdown__item">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                        Profile
                    </a>
                    <a href="{{ route('settings') }}" class="header-dropdown__item">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                        Settings
                    </a>
                    <div class="header-dropdown__divider"></div>
                    <form method="POST" action="{{ route('logout') }}">
                        @csrf
                        <button type="submit" class="header-dropdown__item header-dropdown__item--danger">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                            Sign out
                        </button>
                    </form>
                </div>
            </div>
        </header>

        <div>
            @yield('content')
        </div>
    </main>

</div>

<script>
// ── Global toast system ───────────────────────────────────────────────────
window.showToast = function (type, title, message, duration) {
    var colors = { success: '#10b981', error: '#ef4444', warning: '#f59e0b', info: '#3b82f6' };
    var t = type || 'success';
    var el = document.createElement('div');
    el.style.cssText = 'display:flex;align-items:center;gap:12px;padding:14px 16px;background:#fff;border-radius:12px;box-shadow:0 8px 32px rgba(15,23,42,0.14),0 2px 8px rgba(15,23,42,0.08);border-left:4px solid ' + (colors[t]||colors.info) + ';max-width:360px;pointer-events:all;animation:toast-in 0.35s cubic-bezier(0.34,1.56,0.64,1) forwards';
    el.setAttribute('role', 'alert');
    var body = document.createElement('div');
    body.style.cssText = 'flex:1;min-width:0';
    var heading = document.createElement('p');
    heading.style.cssText = 'margin:0 0 2px;font-size:.875rem;font-weight:600;color:#111827';
    heading.textContent = title || 'Update';
    body.appendChild(heading);
    if (message) { var detail = document.createElement('p'); detail.style.cssText = 'margin:0;font-size:.8125rem;color:#6b7280'; detail.textContent = message; body.appendChild(detail); }
    var dismiss = document.createElement('button');
    dismiss.type = 'button'; dismiss.setAttribute('aria-label', 'Dismiss'); dismiss.textContent = '×';
    dismiss.style.cssText = 'background:none;border:none;cursor:pointer;color:#9ca3af;padding:2px 6px;border-radius:4px;font-size:1.25rem;line-height:1';
    dismiss.addEventListener('click', function () { el.remove(); });
    el.appendChild(body); el.appendChild(dismiss);
    var container = document.getElementById('toast-container');
    if (container) container.appendChild(el);
    setTimeout(function () {
        el.style.animation = 'toast-out 0.25s ease forwards';
        setTimeout(function () { el.remove(); }, 260);
    }, duration || 4000);
};

// One safe JSON boundary for all asynchronous page interactions. A malformed
// proxy/server response never leaks raw HTML or an internal exception message.
window.TrilinguaUI = {
    request: function (url, options) {
        return fetch(url, options).then(function (response) {
            return response.text().then(function (raw) {
                var data = null; try { data = JSON.parse(raw); } catch (e) {}
                if (!response.ok) {
                    var error = data && data.error && typeof data.error === 'object' ? data.error : {};
                    var failure = new Error(error.message || 'We could not complete that request. Please try again.');
                    failure.referenceId = error.reference_id || (data && data.reference_id) || null;
                    failure.retryable = !!error.retryable;
                    throw failure;
                }
                if (!data) throw new Error('The server returned an unexpected response. Please try again.');
                return data;
            });
        });
    },
    message: function (error, fallback) {
        var message = (error && error.message) || fallback || 'We could not complete that request.';
        return error && error.referenceId ? message + ' Reference: ' + error.referenceId + '.' : message;
    }
};

// ── Global error modal ────────────────────────────────────────────────────
window.showErrorModal = function (title, message) {
    var modal  = document.getElementById('error-modal');
    var titleEl  = document.getElementById('error-modal-title');
    var msgEl    = document.getElementById('error-modal-msg');
    if (!modal) { window.alert(message || title || 'An error occurred.'); return; }

    if (titleEl)  titleEl.textContent = title || 'Something went wrong';
    if (msgEl)    msgEl.textContent   = message || '';

    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    var ok        = document.getElementById('error-modal-ok');
    var close     = document.getElementById('error-modal-close');
    var overlay   = document.getElementById('error-modal-overlay');

    function dismiss() {
        modal.style.display = 'none';
        document.body.style.overflow = '';
        if (ok)      ok.onclick      = null;
        if (close)   close.onclick   = null;
        if (overlay) overlay.onclick = null;
        document.removeEventListener('keydown', onKey);
    }
    function onKey(e) { if (e.key === 'Escape') dismiss(); }

    if (ok)      ok.onclick      = dismiss;
    if (close)   close.onclick   = dismiss;
    if (overlay) overlay.onclick = dismiss;
    document.addEventListener('keydown', onKey);
    if (ok) ok.focus();
};

// ── Hamburger / sidebar ───────────────────────────────────────────────────
(function () {
    var sidebar   = document.getElementById('sidebar');
    var overlay   = document.getElementById('sidebar-overlay');
    var hamburger = document.getElementById('hamburger-btn');

    function openSidebar()  { sidebar.classList.add('open'); overlay.classList.add('active'); hamburger.setAttribute('aria-expanded','true'); document.body.style.overflow='hidden'; }
    function closeSidebar() { sidebar.classList.remove('open'); overlay.classList.remove('active'); hamburger.setAttribute('aria-expanded','false'); document.body.style.overflow=''; }

    if (hamburger) hamburger.addEventListener('click', openSidebar);
    if (overlay)   overlay.addEventListener('click', closeSidebar);
    if (sidebar)   sidebar.querySelectorAll('.nav-link').forEach(function(l){ l.addEventListener('click', function(){ if(window.innerWidth<=768) closeSidebar(); }); });
    document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeSidebar(); });
})();

// ── Header user dropdown ──────────────────────────────────────────────────
(function () {
    var btn      = document.getElementById('header-user-btn');
    var dropdown = document.getElementById('header-dropdown');
    if (!btn || !dropdown) return;

    function open()  { dropdown.classList.add('open'); btn.setAttribute('aria-expanded','true'); dropdown.setAttribute('aria-hidden','false'); }
    function close() { dropdown.classList.remove('open'); btn.setAttribute('aria-expanded','false'); dropdown.setAttribute('aria-hidden','true'); }
    function toggle(){ dropdown.classList.contains('open') ? close() : open(); }

    btn.addEventListener('click', toggle);
    btn.addEventListener('keydown', function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggle(); } });
    document.addEventListener('click', function(e){ if(!btn.contains(e.target)&&!dropdown.contains(e.target)) close(); });
    document.addEventListener('keydown', function(e){ if(e.key==='Escape') close(); });
})();

// ── Notification bell ─────────────────────────────────────────────────────
(function () {
    var wrap   = document.getElementById('notif-wrap');
    var btn    = document.getElementById('notif-btn');
    var badge  = document.getElementById('notif-badge');
    var panel  = document.getElementById('notif-dropdown');
    var list   = document.getElementById('notif-list');
    var markAll = document.getElementById('notif-markall');
    if (!wrap || !btn || !panel || !list) return;

    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    if (csrfToken) csrfToken = csrfToken.getAttribute('content');

    function setUnread(n) {
        n = Number(n) || 0;
        if (n > 0) { badge.textContent = n > 99 ? '99+' : n; badge.hidden = false; }
        else { badge.hidden = true; }
    }

    function open() {
        panel.classList.add('open');
        btn.setAttribute('aria-expanded','true');
        panel.setAttribute('aria-hidden','false');
        load();
    }
    function close() {
        panel.classList.remove('open');
        btn.setAttribute('aria-expanded','false');
        panel.setAttribute('aria-hidden','true');
    }
    function toggle() { panel.classList.contains('open') ? close() : open(); }

    var dataUrl = @json(route('notifications.index', ['limit' => 20]));
    var readUrl = @json(route('notifications.read'));
    var timezone = document.documentElement.getAttribute('data-timezone') || 'UTC';

    function state(message, retry) {
        list.replaceChildren();
        var container = document.createElement('div');
        container.className = 'notif-dropdown__empty';
        var text = document.createElement('p'); text.textContent = message; container.appendChild(text);
        if (retry) { var retryButton = document.createElement('button'); retryButton.type = 'button'; retryButton.className = 'notif-dropdown__markall'; retryButton.textContent = 'Try again'; retryButton.addEventListener('click', load); container.appendChild(retryButton); }
        list.appendChild(container);
    }

    function safeUrl(value) {
        try { var parsed = new URL(value || '#', window.location.origin); return parsed.origin === window.location.origin ? parsed.href : '#'; }
        catch (e) { return '#'; }
    }

    function notificationTime(value) {
        if (!value) return '';
        try { return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short', timeZone: timezone }).format(new Date(value)); }
        catch (e) { return ''; }
    }

    function render(items) {
        list.replaceChildren();
        if (!items.length) { state('No notifications'); return; }
        items.forEach(function (n) {
            var data = n.data || {}, isRead = !!n.read_at;
            var item = document.createElement('a'); item.className = 'notif-item' + (isRead ? '' : ' notif-item--unread');
            item.href = safeUrl(n.url); item.dataset.id = n.id || ''; item.dataset.url = item.href;
            item.setAttribute('aria-label', (isRead ? 'Read' : 'Unread') + ' notification');
            var icon = document.createElement('span'); icon.className = 'notif-item__icon notif-item__icon--' + ((n.type || '').indexOf('Failed') !== -1 ? 'error' : 'success'); icon.setAttribute('aria-hidden', 'true');
            var body = document.createElement('div'); body.className = 'notif-item__body';
            var title = document.createElement('p'); title.className = 'notif-item__title'; title.textContent = data.title || 'Notification'; body.appendChild(title);
            var subtext = data.error ? 'Translation failed' : (data.source_language && data.target_language ? data.source_language + ' → ' + data.target_language : '');
            if (subtext) { var sub = document.createElement('p'); sub.className = 'notif-item__sub'; sub.textContent = subtext; body.appendChild(sub); }
            var time = notificationTime(n.created_at); if (time) { var date = document.createElement('time'); date.className = 'notif-item__time'; date.textContent = time; date.title = new Date(n.created_at).toISOString(); body.appendChild(date); }
            item.appendChild(icon); item.appendChild(body); list.appendChild(item);
            if (!isRead) item.addEventListener('click', function (event) { event.preventDefault(); markRead(item.dataset.id, item).finally(function () { if (item.dataset.url && item.dataset.url !== '#') window.location.assign(item.dataset.url); }); });
        });
    }

    function load() {
        state('Loading…');
        window.TrilinguaUI.request(dataUrl, { headers: { 'Accept': 'application/json' } })
            .then(function (res) { setUnread(res.unread_count || 0); render(Array.isArray(res.notifications) ? res.notifications : []); })
            .catch(function () { state('Notifications are temporarily unavailable.', true); });
    }

    function markRead(id, el) {
        var payload = id ? JSON.stringify({ id: id }) : '{}';
        return window.TrilinguaUI.request(readUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRF-TOKEN': csrfToken },
            body: payload
        })
            .then(function (res) {
                setUnread(res.unread_count || 0);
                if (el) { el.classList.remove('notif-item--unread'); }
            })
            .catch(function () {});
    }

    btn.addEventListener('click', toggle);
    if (markAll) markAll.addEventListener('click', function () { markRead(null, null); });

    document.addEventListener('click', function (e) {
        if (wrap && !wrap.contains(e.target)) close();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') close();
    });

    setUnread(badge.textContent);
    window.TrilinguaUI.request(@json(route('notifications.index', ['limit' => 1])), { headers: { 'Accept': 'application/json' } })
        .then(function (res) { setUnread(res.unread_count || 0); })
        .catch(function () {});
})();
</script>
@yield('scripts')
</body>
</html>
