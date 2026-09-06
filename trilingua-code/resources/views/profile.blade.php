@extends('layouts.app')

@section('title', 'Profile')

@section('styles')
    @vite(['resources/css/views/profile.css'])
@endsection

@section('content')
<div class="stack">

    {{-- Profile hero card --}}
    <div class="profile-hero">
        <div class="profile-hero__avatar" aria-hidden="true">
            {{ strtoupper(substr($user->name ?? 'U', 0, 1)) }}
        </div>
        <div class="profile-hero__main">
            <h2 class="profile-hero__name">{{ $user->name ?? 'User' }}</h2>
            <p class="profile-hero__email">{{ $user->email ?? '' }}</p>
            <div class="profile-badges">
                <span class="profile-badge profile-badge--role">{{ $profile['role'] }}</span>
                <span class="profile-badge profile-badge--account">{{ $profile['accountType'] }}</span>
            </div>
        </div>
    </div>

    {{-- Summary card --}}
    <div class="profile-card">
        <h3 class="profile-card__title">Account Summary</h3>
        <dl class="profile-info">
            <div class="profile-info__row">
                <dt>Member since</dt>
                <dd>{{ $profile['memberSince'] ?? '—' }}</dd>
            </div>
            <div class="profile-info__row">
                <dt>Account type</dt>
                <dd>{{ $profile['accountType'] }}</dd>
            </div>
            <div class="profile-info__row">
                <dt>Theme</dt>
                <dd>{{ $profile['theme'] }}</dd>
            </div>
            <div class="profile-info__row">
                <dt>Translations submitted</dt>
                <dd>{{ $profile['translations'] }}</dd>
            </div>
        </dl>
    </div>

    @if(!$user->is_admin)
    {{-- Translation Summary card --}}
    <div class="profile-card">
        <div class="profile-card__head">
            <h3 class="profile-card__title">Translation Summary</h3>
            <a href="{{ route('history') }}" class="profile-card__link">View history &rarr;</a>
        </div>

        <div class="profile-stats">
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $translationSummary['total'] }}</span>
                <span class="profile-stat__label">Translations</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $translationSummary['documents'] }}</span>
                <span class="profile-stat__label">Documents</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $translationSummary['text'] }}</span>
                <span class="profile-stat__label">Text</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $translationSummary['thisMonth'] }}</span>
                <span class="profile-stat__label">This month</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $translationSummary['languagePairs'] }}</span>
                <span class="profile-stat__label">Language pairs</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $translationSummary['avgQuality'] ?? '—' }}</span>
                <span class="profile-stat__label">Avg quality</span>
            </div>
        </div>

        @if ($translationSummary['total'] > 0)
        <div class="profile-pills">
            @foreach ($translationSummary['statusBreakdown'] as $status => $count)
                @if ($count > 0)
                <span class="profile-pill profile-pill--{{ $status }}">
                    {{ ucfirst($status) }} · {{ $count }}
                </span>
                @endif
            @endforeach
        </div>
        @endif

        <ul class="profile-list">
            @forelse ($translationSummary['recent'] as $item)
            <li class="profile-list__item">
                <span class="profile-list__dot" aria-hidden="true"></span>
                <span class="profile-list__text">{{ $item['name'] }}</span>
                <span class="profile-list__pair">{{ $item['source'] }} &rarr; {{ $item['target'] }}</span>
                <span class="profile-list__date">{{ $item['date'] }}</span>
                <span class="profile-pill profile-pill--{{ $item['status'] }}">{{ ucfirst($item['status']) }}</span>
            </li>
            @empty
            <li class="profile-list__empty">No translations yet. <a href="{{ route('translate') }}">Start your first one</a>.</li>
            @endforelse
        </ul>
    </div>

    {{-- Activity Summary card --}}
    <div class="profile-card">
        <div class="profile-card__head">
            <h3 class="profile-card__title">Activity Summary</h3>
        </div>

        <div class="profile-stats">
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $activitySummary['total'] }}</span>
                <span class="profile-stat__label">Events</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $activitySummary['logins'] }}</span>
                <span class="profile-stat__label">Logins</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $activitySummary['failedLogins'] }}</span>
                <span class="profile-stat__label">Failed logins</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $activitySummary['passwordChanges'] }}</span>
                <span class="profile-stat__label">Password changes</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $activitySummary['accountUpdates'] }}</span>
                <span class="profile-stat__label">Account updates</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $activitySummary['lastLogin'] ?? '—' }}</span>
                <span class="profile-stat__label">Last login</span>
            </div>
        </div>

        <ul class="profile-list">
            @forelse ($activitySummary['recent'] as $item)
            <li class="profile-list__item">
                <span class="profile-list__dot" aria-hidden="true"></span>
                <span class="profile-list__text">{{ $item['action'] }}</span>
                <span class="profile-list__date">{{ $item['created_at'] }}</span>
            </li>
            @empty
            <li class="profile-list__empty">No recorded activity yet.</li>
            @endforelse
        </ul>
    </div>
    @endif

    {{-- Admin Work Summary card --}}
    @if($user->is_admin)
    <div class="profile-card">
        <div class="profile-card__head">
            <h3 class="profile-card__title">Admin Work Summary</h3>
            <a href="{{ route('admin.review.index') }}" class="profile-card__link">Review queue &rarr;</a>
        </div>

        <div class="profile-stats">
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $adminWorkSummary['total'] }}</span>
                <span class="profile-stat__label">Reviews</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $adminWorkSummary['items'] }}</span>
                <span class="profile-stat__label">Items reviewed</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $adminWorkSummary['verifies'] }}</span>
                <span class="profile-stat__label">Verifications</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $adminWorkSummary['edits'] }}</span>
                <span class="profile-stat__label">Edits</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $adminWorkSummary['flags'] }}</span>
                <span class="profile-stat__label">Flags</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $adminWorkSummary['thisMonth'] }}</span>
                <span class="profile-stat__label">This month</span>
            </div>
            <div class="profile-stat">
                <span class="profile-stat__value">{{ $adminWorkSummary['pendingQueue'] }}</span>
                <span class="profile-stat__label">Pending queue</span>
            </div>
        </div>

        <ul class="profile-list">
            @forelse ($adminWorkSummary['recent'] as $item)
            <li class="profile-list__item profile-list__item--link">
                <a href="{{ route('admin.review.show', $item['translation_history_id']) }}" class="profile-list__link">
                    <span class="profile-pill profile-pill--{{ $item['action'] }}">{{ $item['label'] }}</span>
                    <span class="profile-list__text">{{ $item['name'] }}</span>
                    <span class="profile-list__date">{{ $item['created_at'] }}</span>
                </a>
            </li>
            @empty
            <li class="profile-list__empty">No review activity yet. <a href="{{ route('admin.review.index') }}">Open the review queue</a>.</li>
            @endforelse
        </ul>
    </div>
    @endif

    {{-- Actions --}}
    <div class="profile-actions">
        <a href="{{ route('settings', ['section' => 'account']) }}" class="btn primary">
            Edit Profile
        </a>
        <a href="{{ route('settings') }}" class="btn secondary">
            General Settings
        </a>
        @if ($user->is_admin)
        <a href="{{ route('admin.review.index') }}" class="btn secondary">
            Review Queue
        </a>
        <a href="{{ route('admin.dashboard') }}" class="btn secondary">
            Admin Dashboard
        </a>
        @endif
    </div>

</div>
@endsection