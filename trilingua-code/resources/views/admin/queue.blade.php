@extends('layouts.app')

@section('title', 'Review Queue')

@section('styles')
    @vite(['resources/css/views/admin.css'])
@endsection

@section('content')
<div class="stack">

    {{-- Page header --}}
    <div class="review-page-header">
        <div class="review-page-header__title">
            <h2>Review Queue <span class="count-badge">{{ $queue->total() }}</span></h2>
            <p>Read-only queue of every translation across all users.</p>
        </div>
    </div>

    @if (!empty($error))
        <p class="empty-state">Unable to load the review queue. Please try again later.</p>
    @else

    {{-- Filters --}}
    <form method="GET" action="{{ route('admin.review.index') }}" class="review-filters">
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
            <label class="review-filters__label" for="f-user">Submitter</label>
            <select name="user" id="f-user" class="review-select">
                <option value="">All users</option>
                @foreach ($submitters as $submitter)
                    <option value="{{ $submitter->id }}" @selected((string) ($filters['user'] ?? '') === (string) $submitter->id)>{{ $submitter->name }}</option>
                @endforeach
            </select>
        </div>

        <div class="review-filters__field">
            <label class="review-filters__label" for="f-type">Type</label>
            <select name="type" id="f-type" class="review-select">
                <option value="">All types</option>
                <option value="document" @selected(($filters['type'] ?? '') === 'document')>Document</option>
                <option value="text" @selected(($filters['type'] ?? '') === 'text')>Text</option>
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
            <a href="{{ route('admin.review.index') }}" class="review-btn">Clear</a>
        </div>
    </form>

    @if ($queue->isEmpty())
        <p class="empty-state">No translations match the current filters.</p>
    @else

    {{-- Queue table --}}
    <div class="review-table-card">
        <table class="review-table">
            <thead>
                <tr>
                    <th>Score</th>
                    <th>Status</th>
                    <th>Type</th>
                    <th>Language Pair</th>
                    <th>Content</th>
                    <th>Submitted By</th>
                    <th>Submitted At</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                @foreach ($queue as $record)
                @php
                    $score   = $record->quality_score;
                    $level   = $score === null ? '' : ($score < 60 ? 'low' : ($score < 80 ? 'medium' : 'high'));
                    $isDoc   = $record->translation_type === 'document';
                    $preview = $isDoc
                        ? ($record->original_filename ?? 'Document')
                        : \Illuminate\Support\Str::limit($record->source_text ?? '', 60);
                    $dateStr = \Carbon\Carbon::parse($record->created_at)->utc()->format('Y-m-d H:i') . ' UTC';
                @endphp
                <tr>
                    <td>
                        <span class="quality-score">
                            <span class="quality-score__dot quality-score__dot--{{ $level }}" aria-hidden="true"></span>
                            {{ $score === null ? '—' : $score }}
                        </span>
                    </td>
                    <td><span class="status-badge status-badge--{{ $record->review_status }}">{{ ucfirst($record->review_status) }}</span></td>
                    <td>
                        <span class="type-badge type-badge--{{ $isDoc ? 'doc' : 'text' }}">
                            {{ $isDoc ? 'Document' : 'Text' }}
                        </span>
                    </td>
                    <td>{{ $record->source_language ?? '—' }} → {{ $record->target_language ?? '—' }}</td>
                    <td>{{ $preview }}</td>
                    <td>{{ $record->user->name ?? 'Unknown' }}</td>
                    <td>{{ $dateStr }}</td>
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
        {{ $queue->withQueryString()->links() }}
    </div>

    @endif {{-- queue empty --}}
    @endif {{-- error --}}

</div>
@endsection