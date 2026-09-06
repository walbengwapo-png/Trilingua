@extends('layouts.app')

@section('title', 'Users')

@section('styles')
    @vite(['resources/css/views/admin.css'])
@endsection

@section('content')
<div class="stack">

    {{-- Page header --}}
    <div class="review-page-header">
        <div class="review-page-header__title">
            <h2>Users <span class="count-badge">{{ $users->total() }}</span></h2>
            <p>Directory of all registered accounts.</p>
        </div>
    </div>

    @if (!empty($error))
        <p class="empty-state">Unable to load the user list. Please try again later.</p>
    @else

    {{-- Filters --}}
    <form method="GET" action="{{ route('admin.users.index') }}" class="review-filters">
        <div class="review-filters__field review-filters__field--search">
            <label class="review-filters__label" for="f-q">Search</label>
            <input type="search" name="q" id="f-q" class="review-input"
                   placeholder="Search name or email…"
                   value="{{ $filters['q'] ?? '' }}"
                   aria-label="Search users">
        </div>

        <div class="review-filters__field">
            <label class="review-filters__label" for="f-sort">Sort</label>
            <select name="sort" id="f-sort" class="review-select">
                <option value="recent" @selected(($filters['sort'] ?? 'recent') === 'recent')>Most recent</option>
                <option value="name" @selected(($filters['sort'] ?? '') === 'name')>Name (A–Z)</option>
                <option value="translations" @selected(($filters['sort'] ?? '') === 'translations')>Most translations</option>
            </select>
        </div>

        <div class="review-filters__actions">
            <button type="submit" class="review-btn review-btn--primary">Apply</button>
            <a href="{{ route('admin.users.index') }}" class="review-btn">Clear</a>
        </div>
    </form>

    @if ($users->isEmpty())
        <p class="empty-state">No users match the current filters.</p>
    @else

    {{-- Users table --}}
    <div class="review-table-card">
        <table class="review-table">
            <thead>
                <tr>
                    <th>User</th>
                    <th>Role</th>
                    <th>Translations</th>
                    <th>Reviewed</th>
                    <th>Joined</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                @foreach ($users as $row)
                <tr>
                    <td>
                        <div class="user-cell">
                            <div class="user-cell__avatar" aria-hidden="true">{{ strtoupper(substr($row->name ?? 'U', 0, 1)) }}</div>
                            <div class="user-cell__meta">
                                <div class="user-cell__name">{{ $row->name ?? 'Unknown' }}</div>
                                <div class="user-cell__email">{{ $row->email }}</div>
                            </div>
                        </div>
                    </td>
                    <td>
                        @if ($row->is_admin)
                            <span class="status-badge status-badge--verified">Admin</span>
                        @else
                            <span class="status-badge status-badge--pending">Member</span>
                        @endif
                    </td>
                    <td>{{ $row->translations_count }}</td>
                    <td>{{ $row->reviewed_count }}</td>
                    <td class="text-nowrap">
                        {{ $row->created_at ? \Carbon\Carbon::parse($row->created_at)->format('Y-m-d') : '—' }}
                    </td>
                    <td>
                        <a href="{{ route('admin.users.show', $row->id) }}" class="review-link">View</a>
                    </td>
                </tr>
                @endforeach
            </tbody>
        </table>
    </div>

    {{-- Pagination --}}
    <div class="review-pagination">
        {{ $users->withQueryString()->links() }}
    </div>

    @endif {{-- users empty --}}
    @endif {{-- error --}}

</div>
@endsection