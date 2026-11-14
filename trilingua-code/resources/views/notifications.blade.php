@extends('layouts.app')

@section('title', 'Notifications')

@section('styles')
    @vite(['resources/css/views/notifications.css'])
@endsection

@section('content')
<div class="stack">

    @if ($error)
        <p class="error-message">Unable to load notifications. Please try again later.</p>
    @else

    {{-- Page header --}}
    <div class="notif-page-header">
        <div class="notif-page-header__title">
            <h2>Notifications <span class="count-badge">{{ $unreadCount }}</span></h2>
            <p class="notif-page-header__sub">Unread</p>
        </div>
        <div class="notif-page-header__controls">
            <div class="notif-tabs" role="tablist" aria-label="Notification filter">
                <a href="{{ route('notifications.page') }}"
                   class="notif-tab {{ !$unreadOnly ? 'notif-tab--active' : '' }}"
                   role="tab"
                   aria-selected="{{ !$unreadOnly ? 'true' : 'false' }}">All</a>
                <a href="{{ route('notifications.page', ['unread' => 1]) }}"
                   class="notif-tab {{ $unreadOnly ? 'notif-tab--active' : '' }}"
                   role="tab"
                   aria-selected="{{ $unreadOnly ? 'true' : 'false' }}">Unread</a>
            </div>
            @if ($unreadCount > 0)
                <button type="button" class="notif-markall" id="notif-markall-page">Mark all read</button>
            @endif
        </div>
    </div>

    @if ($notifications->isEmpty())
        <p class="empty-state">No notifications yet. Notifications about your translations will appear here.</p>
    @else

    <div class="notif-list" id="notif-list-page">
        @foreach ($notifications as $notification)
            @php
                $isRead = $notification->read_at !== null;
                $title = $notification->display_title;
                $sub = $notification->description;
                $icon = $notification->icon;

                $time = $notification->created_at ? \Carbon\Carbon::parse($notification->created_at)->diffForHumans() : '';
            @endphp
            <a href="{{ $notification->target_url ?? '#' }}"
               class="notif-item {{ $isRead ? '' : 'notif-item--unread' }}"
               data-id="{{ $notification->id }}"
               data-read="{{ $isRead ? '1' : '0' }}">
                <span class="notif-item__icon notif-item__icon--{{ $icon }}" aria-hidden="true"></span>
                <span class="notif-item__body">
                    <span class="notif-item__title">{{ $title }}</span>
                    <span class="notif-item__sub">{{ $sub }}</span>
                    <span class="notif-item__time">{{ $time }}</span>
                </span>
                @if (!$isRead)
                    <span class="notif-item__dot" aria-hidden="true"></span>
                @endif
            </a>
        @endforeach
    </div>

    {{-- Pagination --}}
    <div class="notif-pagination">
        {{ $notifications->withQueryString()->links() }}
    </div>

    @endif {{-- empty --}}
    @endif {{-- error --}}

</div>
@endsection

@section('scripts')
<script>
(function () {
    'use strict';

    var csrfToken = document.querySelector('meta[name="csrf-token"]').content;

    function markRead(id, el) {
        var payload = id ? JSON.stringify({ id: id }) : '{}';
        return fetch('/notifications/read', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-CSRF-TOKEN': csrfToken,
            },
            body: payload,
        })
            .then(function (r) { return window.readAppJson(r); })
            .then(function (res) {
                if (el) {
                    el.classList.remove('notif-item--unread');
                    el.setAttribute('data-read', '1');
                    var dot = el.querySelector('.notif-item__dot');
                    if (dot) dot.remove();
                }
                var badge = document.querySelector('.notif-page-header .count-badge');
                if (badge && typeof res.unread_count !== 'undefined') {
                    badge.textContent = res.unread_count;
                }
            })
            .catch(function (error) {
                showToast('warning', 'Update not confirmed', error.message);
                throw error;
            });
    }

    // Mark a single unread item as read, then follow its target route once the
    // read POST has settled so the in-flight request isn't aborted by nav.
    document.querySelectorAll('.notif-item--unread').forEach(function (el) {
        el.addEventListener('click', function (e) {
            var href = el.getAttribute('href');
            if (href && href !== '#') {
                e.preventDefault();
                markRead(el.getAttribute('data-id'), el).catch(function () {}).finally(function () {
                    window.location.href = href;
                });
            } else {
                markRead(el.getAttribute('data-id'), el).catch(function () {});
            }
        });
    });

    // Mark all as read, then reload so badges/tabs stay consistent.
    var markAllBtn = document.getElementById('notif-markall-page');
    if (markAllBtn) {
        markAllBtn.addEventListener('click', function () {
            markAllBtn.disabled = true;
            markRead(null, null)
                .then(function () { window.location.reload(); })
                .catch(function () { markAllBtn.disabled = false; });
        });
    }
})();
</script>
@endsection
