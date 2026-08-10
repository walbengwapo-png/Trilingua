@extends('layouts.app')

@section('title', 'System Activity & Audit Log')

@section('styles')
    @vite(['resources/css/views/admin.css'])
@endsection

@section('content')
<div class="stack">

    <div class="review-page-header">
        <div class="review-page-header__title">
            <h2>System Activity & Audit Log</h2>
            <p>Every admin review action, login, logout, and account change.</p>
        </div>
        <div class="review-page-header__controls">
            <a href="{{ route('admin.dashboard') }}" class="review-btn">Back to Dashboard</a>
        </div>
    </div>

    {{-- Filter form --}}
    <form method="GET" action="{{ route('admin.audit') }}" class="review-filters">
        <div class="review-filters__field">
            <label class="review-filters__label" for="type">Type</label>
            <select name="type" id="type" class="review-select">
                <option value="">All types</option>
                <option value="review" @selected(($filters['type'] ?? '') === 'review')>Review actions</option>
                <option value="account" @selected(($filters['type'] ?? '') === 'account')>Account activity</option>
            </select>
        </div>
        <div class="review-filters__field">
            <label class="review-filters__label" for="action">Action</label>
            <select name="action" id="action" class="review-select">
                <option value="">All actions</option>
                <optgroup label="Review">
                    <option value="verify" @selected(($filters['action'] ?? '') === 'verify')>Verify</option>
                    <option value="edit" @selected(($filters['action'] ?? '') === 'edit')>Edit</option>
                    <option value="flag" @selected(($filters['action'] ?? '') === 'flag')>Flag</option>
                </optgroup>
                <optgroup label="Account">
                    <option value="login_success" @selected(($filters['action'] ?? '') === 'login_success')>Login success</option>
                    <option value="login_failed" @selected(($filters['action'] ?? '') === 'login_failed')>Login failed</option>
                    <option value="logout" @selected(($filters['action'] ?? '') === 'logout')>Logout</option>
                    <option value="account_updated" @selected(($filters['action'] ?? '') === 'account_updated')>Account updated</option>
                    <option value="password_changed" @selected(($filters['action'] ?? '') === 'password_changed')>Password changed</option>
                </optgroup>
            </select>
        </div>
        <div class="review-filters__field">
            <label class="review-filters__label" for="from">From</label>
            <input type="date" name="from" id="from" class="review-input" value="{{ $filters['from'] ?? '' }}">
        </div>
        <div class="review-filters__field">
            <label class="review-filters__label" for="to">To</label>
            <input type="date" name="to" id="to" class="review-input" value="{{ $filters['to'] ?? '' }}">
        </div>
        <div class="review-filters__actions">
            <button type="submit" class="review-btn review-btn--primary">Filter</button>
            <a href="{{ route('admin.audit') }}" class="review-btn">Clear</a>
        </div>
    </form>

    @if ($error)
        <p class="error-message">Unable to load the audit log. Please try again later.</p>
    @elseif ($entries->isEmpty())
        <p class="empty-state">No audit entries match the current filters.</p>
    @else
        <table class="review-table">
            <thead>
                <tr>
                    <th>Date / Time</th>
                    <th>Type</th>
                    <th>Action</th>
                    <th>Actor</th>
                    <th>Target</th>
                    <th>Note</th>
                </tr>
            </thead>
            <tbody>
                @foreach ($entries as $entry)
                    @php
                        $log      = $entry instanceof \App\Models\TranslationEditLog;
                        $actor    = $log ? ($entry->admin->name ?? 'Unknown') : ($entry->user->name ?? ($entry->attempted_email ?? 'Unknown'));
                        $action   = $entry->action;
                        $isReview = $log;
                        $typeBadge = $isReview ? 'type-badge--doc' : 'type-badge--text';
                        $typeLabel = $isReview ? 'Review' : 'Account';
                        $target   = $isReview
                            ? ($entry->translationHistory
                                ? ('#' . $entry->translationHistory->id . ' — ' . ($entry->translationHistory->translated_filename ?? $entry->translationHistory->original_filename ?? ''))
                                : ('#' . $entry->translation_history_id))
                            : ($entry->ip_address ?: '—');
                        $note      = $isReview ? ($entry->note ?? '') : ($entry->note ?? '');
                        $createdAt = $entry->created_at?->utc()->format('Y-m-d H:i') . ' UTC' ?? '—';
                    @endphp
                    <tr>
                        <td>{{ $createdAt }}</td>
                        <td><span class="type-badge {{ $typeBadge }}">{{ $typeLabel }}</span></td>
                        <td><span class="status-badge status-badge--{{ $action }}">{{ ucfirst(str_replace('_', ' ', $action)) }}</span></td>
                        <td>{{ $actor }}</td>
                        <td>{{ $target }}</td>
                        <td>{{ $note ?: '—' }}</td>
                    </tr>
                @endforeach
            </tbody>
        </table>

        <div style="margin-top:16px">
            {{ $entries->appends($filters)->links() }}
        </div>
    @endif

</div>
@endsection