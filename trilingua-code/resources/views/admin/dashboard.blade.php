@extends('layouts.app')

@section('title', 'Admin Dashboard')

@section('styles')
    @vite(['resources/css/views/admin.css'])
@endsection

@section('content')
<div class="stack">

    {{-- Page header --}}
    <div class="review-page-header">
        <div class="review-page-header__title">
            <h2>Admin Dashboard</h2>
            <p>Review queue analytics and flagging trends.</p>
        </div>
        <div class="review-page-header__controls">
            <a href="{{ route('admin.review.index') }}" class="review-btn">Open Review Queue</a>
        </div>
    </div>

    {{-- Stat cards --}}
    <div class="cards-grid cards-grid--admin">
        <div class="stat-card">
            <div class="stat-card__label">Total Translations</div>
            <div class="stat-card__value">{{ $stats['total'] }}</div>
        </div>
        <div class="stat-card">
            <div class="stat-card__label">Pending Review</div>
            <div class="stat-card__value">{{ $stats['pending'] }}</div>
        </div>
        <div class="stat-card">
            <div class="stat-card__label">Verified (no edit)</div>
            <div class="stat-card__value">{{ $stats['verified'] }} <span class="stat-card__suffix">{{ $stats['verifiedWithoutEditPct'] }}%</span></div>
        </div>
        <div class="stat-card">
            <div class="stat-card__label">Edited</div>
            <div class="stat-card__value">{{ $stats['edited'] }}</div>
        </div>
        <div class="stat-card">
            <div class="stat-card__label">Flagged</div>
            <div class="stat-card__value">{{ $stats['flagged'] }}</div>
        </div>
        <div class="stat-card">
            <div class="stat-card__label">Avg Turnaround</div>
            <div class="stat-card__value">{{ $avgTurnaround === null ? '—' : $avgTurnaround . 'h' }}</div>
        </div>
    </div>

    <div class="admin-grid-2">
        {{-- Flag-reason breakdown --}}
        <div class="review-table-card">
            <h3 class="card-title">Flagged by Reason</h3>
            @if (empty($flagReasonBreakdown))
                <p class="empty-state">No flags yet.</p>
            @else
                <table class="review-table">
                    <thead><tr><th>Reason</th><th>Count</th></tr></thead>
                    <tbody>
                        @foreach ($flagReasonBreakdown as $reason => $count)
                        <tr>
                            <td>{{ ucwords(str_replace('_', ' ', $reason)) }}</td>
                            <td><span class="count-badge">{{ $count }}</span></td>
                        </tr>
                        @endforeach
                    </tbody>
                </table>
            @endif
        </div>

        {{-- Flagged by language pair --}}
        <div class="review-table-card">
            <h3 class="card-title">Most-Flagged Language Pairs</h3>
            @if (empty($langPairFlags))
                <p class="empty-state">No flags yet.</p>
            @else
                <table class="review-table">
                    <thead><tr><th>Pair</th><th>Count</th></tr></thead>
                    <tbody>
                        @foreach ($langPairFlags as $row)
                        <tr>
                            <td>{{ $row['pair'] }}</td>
                            <td><span class="count-badge">{{ $row['count'] }}</span></td>
                        </tr>
                        @endforeach
                    </tbody>
                </table>
            @endif
        </div>

        {{-- Flagged by type --}}
        <div class="review-table-card">
            <h3 class="card-title">Flagged by Type</h3>
            @if (empty($typeBreakdown))
                <p class="empty-state">No flags yet.</p>
            @else
                <table class="review-table">
                    <thead><tr><th>Type</th><th>Count</th></tr></thead>
                    <tbody>
                        @foreach ($typeBreakdown as $type => $count)
                        <tr>
                            <td>{{ ucfirst($type) }}</td>
                            <td><span class="count-badge">{{ $count }}</span></td>
                        </tr>
                        @endforeach
                    </tbody>
                </table>
            @endif
        </div>

        {{-- Most active reviewers --}}
        <div class="review-table-card">
            <h3 class="card-title">Most Active Reviewers</h3>
            @if ($topReviewers->isEmpty())
                <p class="empty-state">No review activity yet.</p>
            @else
                <table class="review-table">
                    <thead><tr><th>Reviewer</th><th>Actions</th></tr></thead>
                    <tbody>
                        @foreach ($topReviewers as $row)
                        <tr>
                            <td>{{ $row['name'] }}</td>
                            <td><span class="count-badge">{{ $row['count'] }}</span></td>
                        </tr>
                        @endforeach
                    </tbody>
                </table>
            @endif
        </div>
    </div>

    {{-- Activity over time --}}
    <div class="review-table-card">
        <h3 class="card-title">Review Activity (Last 30 Days)</h3>
        @if ($activityOverTime->isEmpty())
            <p class="empty-state">No review activity in the last 30 days.</p>
        @else
            <table class="review-table">
                <thead><tr><th>Date</th><th>Verify</th><th>Edit</th><th>Flag</th></tr></thead>
                <tbody>
                    @foreach ($activityOverTime as $row)
                    <tr>
                        <td>{{ $row['date'] }}</td>
                        <td>{{ $row['verify'] }}</td>
                        <td>{{ $row['edit'] }}</td>
                        <td>{{ $row['flag'] }}</td>
                    </tr>
                    @endforeach
                </tbody>
            </table>
        @endif
    </div>

</div>
@endsection