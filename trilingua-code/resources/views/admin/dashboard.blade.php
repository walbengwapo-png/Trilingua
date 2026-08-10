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
            <p>Review queue analytics and system activity.</p>
        </div>
        <div class="review-page-header__controls">
            <a href="{{ route('admin.review.index') }}" class="review-btn">Open Review Queue</a>
            <a href="{{ route('admin.audit') }}" class="review-btn">View Full Audit Log</a>
        </div>
    </div>

    {{-- Core stat cards --}}
    <div class="cards-grid cards-grid--admin">
        <div class="stat-card">
            <div class="stat-card__label">Pending Review</div>
            <div class="stat-card__value">{{ $stats['pending'] }}</div>
            <a href="{{ route('admin.review.index') }}" class="stat-card__link">View queue &rarr;</a>
        </div>
        <div class="stat-card">
            <div class="stat-card__label">Verified (no edit)</div>
            <div class="stat-card__value">{{ $stats['verified'] }} <span class="stat-card__suffix">{{ $stats['verifiedWithoutEditPct'] }}%</span></div>
        </div>
        <div class="stat-card">
            <div class="stat-card__label">Avg Turnaround</div>
            <div class="stat-card__value">{{ $avgTurnaround === null ? '—' : $avgTurnaround . 'h' }}</div>
        </div>
    </div>

    <div class="admin-grid-2">
        {{-- System Activity panel --}}
        <div class="review-table-card">
            <h3 class="card-title">System Activity</h3>
            @if (empty($recentActivity))
                <p class="empty-state">No activity yet.</p>
            @else
                <table class="review-table">
                    <thead><tr><th>Date / Time</th><th>Type</th><th>Action</th><th>Actor</th><th>Target / IP</th></tr></thead>
                    <tbody>
                        @foreach ($recentActivity as $row)
                        <tr>
                            @php
                                $created = \Carbon\Carbon::parse($row['created_at'])->utc()->format('Y-m-d H:i') . ' UTC';
                                $typeBadge = $row['type'] === 'review' ? 'type-badge--doc' : 'type-badge--text';
                                $typeLabel = $row['type'] === 'review' ? 'Review' : 'Account';
                            @endphp
                            <td>{{ $created }}</td>
                            <td><span class="type-badge {{ $typeBadge }}">{{ $typeLabel }}</span></td>
                            <td><span class="status-badge status-badge--{{ $row['action'] }}">{{ ucfirst(str_replace('_', ' ', $row['action'])) }}</span></td>
                            <td>{{ $row['actor'] }}</td>
                            <td>{{ $row['target'] }}</td>
                        </tr>
                        @endforeach
                    </tbody>
                </table>
                <a href="{{ route('admin.audit') }}" class="review-btn" style="margin-top:12px">View full audit log &rarr;</a>
            @endif
        </div>

        {{-- Review Activity trend --}}
        <div class="review-table-card">
            <h3 class="card-title">Review Activity Trend
                @if ($activityOverTime->isNotEmpty())
                    <a href="{{ route('admin.audit') }}" class="review-btn" style="float:right;font-size:0.78rem">View all</a>
                @endif
            </h3>
            @if ($activityOverTime->isEmpty())
                <p class="empty-state">No review activity in the last 30 days.</p>
            @else
                <table class="review-table">
                    <thead><tr><th>Date</th><th>Verify</th><th>Edit</th><th>Flag</th><th>Total</th></tr></thead>
                    <tbody>
                        @foreach ($activityOverTime as $row)
                        <tr>
                            <td>{{ $row['date'] }}</td>
                            <td>{{ $row['verify'] }}</td>
                            <td>{{ $row['edit'] }}</td>
                            <td>{{ $row['flag'] }}</td>
                            <td><span class="count-badge">{{ $row['total'] }}</span></td>
                        </tr>
                        @endforeach
                    </tbody>
                </table>
            @endif
        </div>
    </div>

</div>
@endsection
