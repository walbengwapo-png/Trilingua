@extends('layouts.app')

@section('title', 'Translation Jobs')

@section('styles')
    @vite(['resources/css/views/admin.css'])
@endsection

@section('content')
<div class="stack">

    <div class="review-page-header">
        <div class="review-page-header__title">
            <h2>Translation Jobs</h2>
            <p>Durable state machine for document translations, plus failed queue jobs.</p>
        </div>
    </div>

    @if (session('status') === 'queue-job-retried')
        <p class="notice notice--success" role="status">Job replayed — the worker will reconstruct input from the durable original.</p>
    @elseif (session('status') === 'queue-job-not-recoverable')
        <p class="notice notice--error" role="alert">This failed job cannot be retried: no durable original exists to reconstruct the input.</p>
    @elseif (session('status') === 'queue-job-retry-failed')
        <p class="notice notice--error" role="alert">Retry could not be queued. Check the application logs.</p>
    @elseif (!empty($error))
        <p class="empty-state">Unable to load jobs. Please try again later.</p>
    @endif

    @if (empty($error))

    <div class="review-table-card">
        {{-- Status summary chips --}}
        <div class="review-filters" style="padding:12px 16px; border-bottom:1px solid var(--border-color,#e5e7eb);">
            @forelse ($counts as $status => $total)
                <span class="type-badge type-badge--{{ $status }}">
                    {{ ucfirst($status) }}: {{ $total }}
                </span>
            @empty
                <span class="type-badge">No jobs yet</span>
            @endforelse
        </div>

        <form method="GET" action="{{ route('admin.jobs.index') }}" class="review-filters">
            <div class="review-filters__field review-filters__field--search">
                <label class="review-filters__label" for="j-q">Search</label>
                <input type="search" name="q" id="j-q" class="review-input"
                       placeholder="Search filename or job id…" value="{{ $filters['q'] }}">
            </div>
            <div class="review-filters__field">
                <label class="review-filters__label" for="j-status">Status</label>
                <select name="status" id="j-status" class="review-select">
                    <option value="">All statuses</option>
                    @foreach (['created', 'queued', 'processing', 'completed', 'failed', 'cancelled'] as $s)
                        <option value="{{ $s }}" @selected($filters['status'] === $s)>{{ ucfirst($s) }}</option>
                    @endforeach
                </select>
            </div>
            <div class="review-filters__actions">
                <button type="submit" class="review-btn review-btn--primary">Apply</button>
                <a href="{{ route('admin.jobs.index') }}" class="review-btn">Clear</a>
            </div>
        </form>

        <table class="review-table">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Status</th>
                    <th>File</th>
                    <th>Language Pair</th>
                    <th>User</th>
                    <th>Progress</th>
                    <th>Backend</th>
                    <th>Updated</th>
                    <th>Error</th>
                </tr>
            </thead>
            <tbody>
                @forelse ($jobs as $job)
                <tr>
                    <td><code>{{ $job->uuid }}</code></td>
                    <td>
                        <span class="status-badge status-badge--{{ $job->status }}">{{ ucfirst($job->status) }}</span>
                    </td>
                    <td>{{ $job->original_name }}</td>
                    <td>{{ $job->source_lang }} → {{ $job->target_lang }}</td>
                    <td>{{ $job->user->name ?? '#' . $job->user_id }}</td>
                    <td>{{ $job->progress }}%</td>
                    <td>{{ $job->storage_backend ?? '—' }}</td>
                    <td>{{ optional($job->updated_at)->utc()->format('Y-m-d H:i') }} UTC</td>
                    <td>{{ \Illuminate\Support\Str::limit($job->error, 60) }}</td>
                </tr>
                @empty
                <tr><td colspan="9" class="empty-state">No translation jobs match.</td></tr>
                @endforelse
            </tbody>
        </table>

        <div class="review-pagination">
            {{ $jobs->links() }}
        </div>
    </div>

    <div class="review-table-card">
        <div class="review-page-header">
            <div class="review-page-header__title">
                <h3>Failed Queue Jobs <span class="count-badge">{{ $failed->count() }}</span></h3>
                <p>Jobs that exhausted their attempts. Retry only replays jobs whose input can be reconstructed from a durable original.</p>
            </div>
        </div>
        <table class="review-table">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Job</th>
                    <th>Failed At</th>
                    <th>Exception</th>
                    <th>Input</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                @forelse ($failed as $row)
                @php
                    $payload = json_decode($row->payload, true);
                    $name = $payload['displayName'] ?? class_basename($payload['job'] ?? 'unknown');
                @endphp
                <tr>
                    <td>{{ $row->id }}</td>
                    <td>{{ class_basename($name) }}</td>
                    <td>{{ \Carbon\Carbon::parse($row->failed_at)->utc()->format('Y-m-d H:i') }} UTC</td>
                    <td title="{{ $row->exception }}">{{ \Illuminate\Support\Str::limit($row->exception, 80) }}</td>
                    <td>
                        @if (!empty($row->recoverable))
                            <span class="type-badge">Recoverable</span>
                        @else
                            <span class="type-badge">Unavailable</span>
                        @endif
                    </td>
                    <td>
                        @if (!empty($row->recoverable))
                            <form method="POST" action="{{ route('admin.jobs.retry', $row->id) }}">
                                @csrf
                                <button type="submit" class="review-btn">Retry</button>
                            </form>
                        @else
                            <span title="No durable original exists; this job cannot be reconstructed.">—</span>
                        @endif
                    </td>
                </tr>
                @empty
                <tr><td colspan="6" class="empty-state">No failed jobs.</td></tr>
                @endforelse
            </tbody>
        </table>
    </div>

    @endif

</div>
@endsection