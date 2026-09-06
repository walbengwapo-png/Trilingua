@extends('layouts.app')

@section('title', 'Admin - Activity Log')

@section('styles')
    @vite(['resources/css/views/admin.css'])
@endsection

@section('content')
<div class="stack">

    {{-- Page header --}}
    <div class="review-page-header">
        <div class="review-page-header__title">
            <h2>Activity Log</h2>
            <p>Consolidated audit trail of review and account activity.</p>
        </div>
        <div class="review-page-header__controls">
            <a href="{{ route('admin.dashboard') }}" class="review-btn">&larr; Back to Dashboard</a>
        </div>
    </div>

    @php
        // Deterministic list of every action the audit tables can emit.
        // Review actions come from translation_edit_log; account actions from
        // user_activity_log.
        $actions = ['verify', 'edit', 'flag', 'login_success', 'login_failed', 'logout', 'account_updated', 'password_changed'];
    @endphp

    {{-- Filters --}}
    <form method="GET" action="{{ route('admin.audit') }}" class="review-filters">
        <div class="review-filters__field">
            <label class="review-filters__label" for="type">Type</label>
            <select name="type" id="type" class="review-select">
                <option value="">All Types</option>
                <option value="review" @selected(($filters['type'] ?? '') === 'review')>Review</option>
                <option value="account" @selected(($filters['type'] ?? '') === 'account')>Account</option>
            </select>
        </div>

        <div class="review-filters__field">
            <label class="review-filters__label" for="action">Action</label>
            <select name="action" id="action" class="review-select">
                <option value="">All Actions</option>
                @foreach ($actions as $action)
                    <option value="{{ $action }}" @selected(($filters['action'] ?? '') === $action)>
                        {{ ucfirst(str_replace('_', ' ', $action)) }}
                    </option>
                @endforeach
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
            <button type="submit" class="review-btn review-btn--primary">Apply</button>
            <a href="{{ route('admin.audit') }}" class="review-btn">Reset</a>
        </div>
    </form>

    @if (!empty($error))
        <p class="empty-state">Unable to load the audit log. Please try again later.</p>
    @elseif ($entries->isEmpty())
        <p class="empty-state">No audit log entries found.</p>
    @else
        <div class="review-table-card">
            <table class="review-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Type</th>
                        <th>Actor</th>
                        <th>Action</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
                    @foreach ($entries as $entry)
                        @php
                            $isReview    = $entry->type === 'review';
                            $actionClass = match ($entry->action) {
                                'verify', 'login_success' => 'status-badge--verified',
                                'edit', 'account_updated', 'password_changed' => 'status-badge--edited',
                                'flag', 'login_failed' => 'status-badge--flagged',
                                default => 'status-badge--pending',
                            };
                        @endphp
                        <tr>
                            <td class="text-nowrap">
                                {{ \Carbon\Carbon::parse($entry->created_at)->format('Y-m-d H:i') }}
                            </td>
                            <td>
                                <span class="type-badge {{ $isReview ? 'type-badge--doc' : 'type-badge--text' }}">
                                    {{ $isReview ? 'Review' : 'Account' }}
                                </span>
                            </td>
                            <td>{{ $entry->actor }}</td>
                            <td>
                                <span class="status-badge {{ $actionClass }}">
                                    {{ ucfirst(str_replace('_', ' ', $entry->action)) }}
                                </span>
                            </td>
                            <td class="text-muted audit-details">
                                {{ $entry->target }}
                                @if (!empty($entry->note))
                                    <span class="audit-details__note">{{ $entry->note }}</span>
                                @endif
                            </td>
                        </tr>
                    @endforeach
                </tbody>
            </table>
        </div>

        <div class="review-pagination">
            {{ $entries->withQueryString()->links() }}
        </div>
    @endif

</div>
@endsection