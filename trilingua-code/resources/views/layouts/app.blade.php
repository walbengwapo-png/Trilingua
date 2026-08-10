<!doctype html>
<html lang="en" data-theme="{{ auth()->user()->theme ?? 'light' }}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>@yield('title', 'Dashboard') — TriLingua</title>
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
        <div class="brand__icon" style="width:28px;height:28px">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M5 8l6 6"/><path d="M4 14l6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="M22 22l-5-10-5 10"/><path d="M14 18h6"/>
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
            <div class="brand__icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M5 8l6 6"/><path d="M4 14l6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="M22 22l-5-10-5 10"/><path d="M14 18h6"/>
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
                <div class="sidebar-user__role">Member</div>
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
    var icons = {
        success: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
        error:   '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
        warning: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
        info:    '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>'
    };
    var colors = { success: '#10b981', error: '#ef4444', warning: '#f59e0b', info: '#3b82f6' };
    var t = type || 'success';
    var el = document.createElement('div');
    el.style.cssText = 'display:flex;align-items:center;gap:12px;padding:14px 16px;background:#fff;border-radius:12px;box-shadow:0 8px 32px rgba(15,23,42,0.14),0 2px 8px rgba(15,23,42,0.08);border-left:4px solid ' + (colors[t]||colors.info) + ';max-width:360px;pointer-events:all;animation:toast-in 0.35s cubic-bezier(0.34,1.56,0.64,1) forwards';
    el.setAttribute('role', 'alert');
    el.innerHTML =
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="' + (colors[t]||colors.info) + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0" aria-hidden="true">' + (icons[t]||icons.info) + '</svg>' +
        '<div style="flex:1;min-width:0"><p style="margin:0 0 2px;font-size:0.875rem;font-weight:600;color:#111827">' + title + '</p>' + (message ? '<p style="margin:0;font-size:0.8125rem;color:#6b7280">' + message + '</p>' : '') + '</div>' +
        '<button onclick="this.closest(\'[role=alert]\').remove()" style="background:none;border:none;cursor:pointer;color:#9ca3af;padding:2px;border-radius:4px;display:flex;flex-shrink:0" aria-label="Dismiss"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>';
    var container = document.getElementById('toast-container');
    if (container) container.appendChild(el);
    setTimeout(function () {
        el.style.animation = 'toast-out 0.25s ease forwards';
        setTimeout(function () { el.remove(); }, 260);
    }, duration || 4000);
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

    function load() {
        list.innerHTML = '<div class="notif-dropdown__empty">Loading…</div>';
        fetch('/notifications/data?limit=20', { headers: { 'Accept': 'application/json' } })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                setUnread(res.unread_count || 0);
                var items = res.notifications || [];
                if (!items.length) {
                    list.innerHTML = '<div class="notif-dropdown__empty">No notifications</div>';
                    return;
                }
                var html = '';
                items.forEach(function (n) {
                    var d = n.data || {};
                    var isRead = !!n.read_at;
                    var cls = 'notif-item' + (isRead ? '' : ' notif-item--unread');
                    var title = d.title || 'Notification';
                    var sub;
                    if (d.error) sub = 'Translation failed';
                    else if (d.source_language && d.target_language) sub = d.source_language + ' → ' + d.target_language;
                    else sub = '';
                    var url = n.url || '#';
                    var typeIcon = n.type && n.type.indexOf('Failed') !== -1 ? 'error' : 'success';
                    html += '<a class="' + cls + '" href="' + url + '" data-url="' + url + '" data-id="' + n.id + '" aria-label="' + (isRead ? 'Read' : 'Unread') + ' notification">' +
                        '<span class="notif-item__icon notif-item__icon--' + typeIcon + '" aria-hidden="true"></span>' +
                        '<div class="notif-item__body"><p class="notif-item__title">' + title + '</p>' +
                        (sub ? '<p class="notif-item__sub">' + sub + '</p>' : '') +
                        '<p class="notif-item__time">' + (n.created_at ? new Date(n.created_at).toLocaleString() : '') + '</p></div></a>';
                });
                list.innerHTML = html;

                function openNotification(el) {
                    var url = el.getAttribute('data-url');
                    if (url && url !== '#') {
                        markRead(el.getAttribute('data-id'), el).finally(function () {
                            window.location.href = url;
                        });
                    } else {
                        markRead(el.getAttribute('data-id'), el);
                    }
                }

                list.querySelectorAll('.notif-item--unread').forEach(function (el) {
                    el.addEventListener('click', function (e) { e.preventDefault(); openNotification(el); });
                    el.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openNotification(el); } });
                });
            })
            .catch(function () {
                list.innerHTML = '<div class="notif-dropdown__empty">Failed to load notifications</div>';
            });
    }

    function markRead(id, el) {
        var payload = id ? JSON.stringify({ id: id }) : '{}';
        return fetch('/notifications/read', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRF-TOKEN': csrfToken },
            body: payload
        })
            .then(function (r) { return r.json(); })
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
    fetch('/notifications/data?limit=1', { headers: { 'Accept': 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (res) { setUnread(res.unread_count || 0); })
        .catch(function () {});
})();
</script>
@yield('scripts')
</body>
</html>
