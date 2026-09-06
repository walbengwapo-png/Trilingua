@extends('layouts.app')

@section('title', $user->name)

@section('styles')
    @vite(['resources/css/views/admin.css'])
@endsection

@section('content')
<div class="stack">

    {{-- Back link --}}
    <a href="{{ route('admin.users.index') }}" class="review-back">&larr; Back to Users</a>

    {{-- User header --}}
    <div class="review-detail-card user-profile">
        <div class="user-profile__row">
            <div class="user-profile__avatar" aria-hidden="true">{{ strtoupper(substr($user->name ?? 'U', 0, 1)) }}</div>
            <div class="user-profile__identity">
                <div class="user-profile__name">
                    {{ $user->name ?? 'Unknown' }}
                    @if ($user->is_admin)
                        <span class="status-badge status-badge--verified">Admin</span>
                    @else
                        <span class="status-badge status-badge--pending">Member</span>
                    @endif
                </div>
                <div class="user-profile__email">{{ $user->email }}</div>
                <div class="user-profile__meta">
                    Joined {{ $user->created_at ? \Carbon\Carbon::parse($user->created_at)->format('Y-m-d') : '—' }}
                    @if ($user->google_id)
                        <span class="type-badge type-badge--text">Google account</span>
                    @endif
                </div>
            </div>
            <div class="user-profile__actions">
                <a href="{{ route('admin.users.translations', $user->id) }}" class="review-btn review-btn--primary">View All Translations</a>
                <a href="{{ route('admin.review.index', ['user' => $user->id]) }}" class="review-btn">Review Queue</a>
            </div>
        </div>
    </div>

    {{-- Stat cards --}}
    <div class="cards-grid cards-grid--admin">
        <div class="stat-card">
            <div class="stat-card__label">Total Translations</div>
            <div class="stat-card__value">{{ $totals['total'] }}</div>
        </div>
        <div class="stat-card">
            <div class="stat-card__label">Words Translated</div>
            <div class="stat-card__value">{{ number_format($stats['wordsTranslated']) }}</div>
        </div>
        <div class="stat-card">
            <div class="stat-card__label">Documents</div>
            <div class="stat-card__value">{{ $stats['totalDocs'] }}</div>
        </div>
        <div class="stat-card">
            <div class="stat-card__label">This Month</div>
            <div class="stat-card__value">{{ $stats['translationsThisMonth'] }}</div>
        </div>
        <div class="stat-card">
            <div class="stat-card__label">Successful Logins</div>
            <div class="stat-card__value">{{ $loginCount }}</div>
        </div>
        <div class="stat-card">
            <div class="stat-card__label">Failed Logins</div>
            <div class="stat-card__value">{{ $failedLogins }}</div>
        </div>
    </div>

    {{-- Review status breakdown --}}
    <div class="review-detail-card">
        <h3 class="card-title">Review Status</h3>
        <div class="review-detail__meta">
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Pending</span>
                <span class="review-detail__meta-value">{{ $totals['pending'] }}</span>
            </div>
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Verified</span>
                <span class="review-detail__meta-value">{{ $totals['verified'] }}</span>
            </div>
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Edited</span>
                <span class="review-detail__meta-value">{{ $totals['edited'] }}</span>
            </div>
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Flagged</span>
                <span class="review-detail__meta-value">{{ $totals['flagged'] }}</span>
            </div>
        </div>
    </div>

    <div class="admin-grid-2">
        {{-- Recent translations --}}
        <div class="review-table-card">
            <h3 class="card-title">Recent Translations</h3>
            @if ($recent->isEmpty())
                <p class="empty-state">No translations yet.</p>
            @else
                <table class="review-table">
                    <thead><tr><th>Type</th><th>Content</th><th>Status</th><th>Date</th><th></th></tr></thead>
                    <tbody>
                        @foreach ($recent as $record)
                        @php
                            $isDoc   = $record->translation_type === 'document';
                            $preview = $isDoc
                                ? ($record->translated_filename ?? $record->original_filename ?? 'Document')
                                : \Illuminate\Support\Str::limit($record->source_text ?? '', 40);
                            $dateStr = \Carbon\Carbon::parse($record->created_at)->format('Y-m-d H:i');
                        @endphp
                        <tr>
                            <td><span class="type-badge type-badge--{{ $isDoc ? 'doc' : 'text' }}">{{ $isDoc ? 'Document' : 'Text' }}</span></td>
                            <td>{{ $preview }}</td>
                            <td><span class="status-badge status-badge--{{ $record->review_status }}">{{ ucfirst($record->review_status) }}</span></td>
                            <td class="text-nowrap">{{ $dateStr }}</td>
                            <td><a href="{{ route('admin.review.show', $record->id) }}" class="review-link">Review</a></td>
                        </tr>
                        @endforeach
                    </tbody>
                </table>
            @endif
        </div>

        {{-- Recent review activity (as reviewer) --}}
        <div class="review-table-card">
            <h3 class="card-title">Recent Review Activity</h3>
            @if ($reviewActions->isEmpty())
                <p class="empty-state">No review activity by this admin.</p>
            @else
                <table class="review-table">
                    <thead><tr><th>Action</th><th>Translation</th><th>Date</th></tr></thead>
                    <tbody>
                        @foreach ($reviewActions as $log)
                        @php
                            $target = $log->translationHistory
                                ? ($log->translationHistory->translated_filename ?? $log->translationHistory->original_filename ?? '#' . $log->translation_history_id)
                                : '#' . $log->translation_history_id;
                            $dateStr = \Carbon\Carbon::parse($log->created_at)->format('Y-m-d H:i');
                        @endphp
                        <tr>
                            <td><span class="status-badge status-badge--{{ $log->action }}">{{ ucfirst(str_replace('_', ' ', $log->action)) }}</span></td>
                            <td>{{ $target }}</td>
                            <td class="text-nowrap">{{ $dateStr }}</td>
                        </tr>
                        @endforeach
                    </tbody>
                </table>
            @endif
        </div>
    </div>

    {{-- Recent account activity --}}
    <div class="review-table-card">
        <h3 class="card-title">Recent Account Activity</h3>
        @if ($accountActions->isEmpty())
            <p class="empty-state">No account activity yet.</p>
        @else
            <table class="review-table">
                <thead><tr><th>Action</th><th>IP Address</th><th>Note</th><th>Date</th></tr></thead>
                <tbody>
                    @foreach ($accountActions as $log)
                    <tr>
                        <td><span class="status-badge status-badge--{{ $log->action }}">{{ ucfirst(str_replace('_', ' ', $log->action)) }}</span></td>
                        <td class="text-nowrap">{{ $log->ip_address ?: '—' }}</td>
                        <td class="audit-details">{{ $log->note ?: '—' }}</td>
                        <td class="text-nowrap">{{ \Carbon\Carbon::parse($log->created_at)->format('Y-m-d H:i') }}</td>
                    </tr>
                    @endforeach
                </tbody>
            </table>
        @endif
    </div>

</div>
@endsection