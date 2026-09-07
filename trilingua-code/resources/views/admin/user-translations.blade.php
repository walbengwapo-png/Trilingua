@extends('layouts.app')

@section('title', $user->name . ' — Translations')

@section('styles')
    @vite(['resources/css/views/admin.css'])
@endsection

@section('content')
<div class="stack">

    {{-- Back link --}}
    <a href="{{ route('admin.users.show', $user->id) }}" class="review-back">&larr; Back to {{ $user->name ?? 'User' }}</a>

    {{-- Page header --}}
    <div class="review-page-header">
        <div class="review-page-header__title">
            <h2>{{ $user->name ?? 'Unknown' }}'s Translations <span class="count-badge">{{ $records->total() }}</span></h2>
            <p>{{ $user->email }}</p>
        </div>
    </div>

    @if (!empty($error))
        <p class="empty-state">Unable to load this user's translations. Please try again later.</p>
    @else

    {{-- Filters --}}
    <form method="GET" action="{{ route('admin.users.translations', $user->id) }}" class="review-filters">
        <div class="review-filters__field">
            <label class="review-filters__label" for="f-type">Type</label>
            <select name="type" id="f-type" class="review-select">
                <option value="">All types</option>
                <option value="document" @selected(($filters['type'] ?? '') === 'document')>Document</option>
                <option value="text" @selected(($filters['type'] ?? '') === 'text')>Text</option>
            </select>
        </div>

        <div class="review-filters__field">
            <label class="review-filters__label" for="f-status">Status</label>
            <select name="status" id="f-status" class="review-select">
                <option value="">All statuses</option>
                @foreach (\App\Support\ReviewStatus::ALL as $s)
                    <option value="{{ $s }}" @selected(($filters['status'] ?? '') === $s)>{{ ucfirst($s) }}</option>
                @endforeach
            </select>
        </div>

        <div class="review-filters__field">
            <label class="review-filters__label" for="f-from">From</label>
            <input type="date" name="from" id="f-from" class="review-input" value="{{ $filters['from'] ?? '' }}">
        </div>

        <div class="review-filters__field">
            <label class="review-filters__label" for="f-to">To</label>
            <input type="date" name="to" id="f-to" class="review-input" value="{{ $filters['to'] ?? '' }}">
        </div>

        <div class="review-filters__actions">
            <button type="submit" class="review-btn review-btn--primary">Apply</button>
            <a href="{{ route('admin.users.translations', $user->id) }}" class="review-btn">Clear</a>
        </div>
    </form>

    @if ($records->isEmpty())
        <p class="empty-state">No translations match the current filters.</p>
    @else

    {{-- Translations table --}}
    <div class="review-table-card">
        <table class="review-table">
            <thead>
                <tr>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Language Pair</th>
                    <th>Content</th>
                    <th>Submitted At</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                @foreach ($records as $record)
                @php
                    $isDoc   = $record->translation_type === 'document';
                    $preview = $isDoc
                        ? ($record->translated_filename ?? $record->original_filename ?? 'Document')
                        : \Illuminate\Support\Str::limit($record->source_text ?? '', 60);
                    $dateStr = \Carbon\Carbon::parse($record->created_at)->format('Y-m-d H:i');
                @endphp
                <tr>
                    <td>
                        <span class="type-badge type-badge--{{ $isDoc ? 'doc' : 'text' }}">
                            {{ $isDoc ? 'Document' : 'Text' }}
                        </span>
                    </td>
                    <td><span class="status-badge status-badge--{{ $record->review_status }}">{{ ucfirst($record->review_status) }}</span></td>
                    <td>{{ $record->source_language ?? '—' }} → {{ $record->target_language ?? '—' }}</td>
                    <td>{{ $preview }}</td>
                    <td class="text-nowrap">{{ $dateStr }}</td>
                    <td>
                        <a href="{{ route('admin.review.show', $record->id) }}" class="review-link">Review</a>
                    </td>
                </tr>
                @endforeach
            </tbody>
        </table>
    </div>

    {{-- Pagination --}}
    <div class="review-pagination">
        {{ $records->withQueryString()->links() }}
    </div>

    @endif {{-- records empty --}}
    @endif {{-- error --}}

</div>
@endsection