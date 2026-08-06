@extends('layouts.app')

@section('title','Dashboard')

@section('styles')
    @vite(['resources/css/views/dashboard.css'])
@endsection

@section('content')
<div class="stack">

    {{-- Error banner --}}
    @if ($error ?? false)
    <div class="alert-banner" role="alert">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        Unable to load your translation data. Please try refreshing the page.
    </div>
    @endif

    {{-- Greeting --}}
    <div class="greeting-row">
        <div>
            <h1 class="welcome-greeting">Welcome back, {{ auth()->user()->name ?? 'User' }}</h1>
            <p class="welcome-sub">Here's an overview of your translation activity.</p>
        </div>
        <a href="{{ route('translate') }}" class="btn primary" style="white-space:nowrap">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="margin-right:6px;vertical-align:middle"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            New Translation
        </a>
    </div>

    {{-- Stat cards --}}
    <div class="cards-grid">
        <div class="stat-card">
            <div class="stat-card__icon stat-card__icon--blue">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                </svg>
            </div>
            <div class="stat-card__label">Total Documents</div>
            <div class="stat-card__value">{{ $stats['totalDocs'] }}</div>
        </div>

        <div class="stat-card">
            <div class="stat-card__icon stat-card__icon--green">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>
                    <polyline points="17 6 23 6 23 12"/>
                </svg>
            </div>
            <div class="stat-card__label">Translations This Month</div>
            <div class="stat-card__value">{{ $stats['translationsThisMonth'] }}</div>
        </div>

        <div class="stat-card">
            <div class="stat-card__icon stat-card__icon--purple">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                </svg>
            </div>
            <div class="stat-card__label">Words Translated</div>
            <div class="stat-card__value">{{ number_format($stats['wordsTranslated']) }}</div>
        </div>
    </div>

    {{-- Quick Actions --}}
    <div class="section-header">
        <h2 class="section-title">Quick Actions</h2>
    </div>
    <div class="quick-actions">
        <a href="{{ route('translate') }}" class="quick-action-card">
            <div class="quick-action-card__icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M5 8l6 6"/><path d="M4 14l6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/>
                    <path d="M22 22l-5-10-5 10"/><path d="M14 18h6"/>
                </svg>
            </div>
            <div>
                <div class="quick-action-card__label">New Translation</div>
                <div class="quick-action-card__desc">Translate text instantly</div>
            </div>
        </a>

        <a href="{{ route('translate') }}" class="quick-action-card">
            <div class="quick-action-card__icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="17 8 12 3 7 8"/>
                    <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
            </div>
            <div>
                <div class="quick-action-card__label">Upload Document</div>
                <div class="quick-action-card__desc">Translate DOCX, PDF, TXT</div>
            </div>
        </a>

        <a href="{{ route('history') }}" class="quick-action-card">
            <div class="quick-action-card__icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <circle cx="12" cy="12" r="10"/>
                    <polyline points="12 6 12 12 16 14"/>
                </svg>
            </div>
            <div>
                <div class="quick-action-card__label">View History</div>
                <div class="quick-action-card__desc">Browse past translations</div>
            </div>
        </a>
    </div>

    {{-- Recent Translations --}}
    <div class="table-card">
        <div class="table-card__header">
            <h2 class="card-title">Recent Translations</h2>
            <a href="{{ route('history') }}" class="view-all-link">
                View all
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6"/></svg>
            </a>
        </div>
        <div style="overflow-x:auto">
            <table class="table">
                <thead>
                    <tr>
                        <th>Document / Text</th>
                        <th>Languages</th>
                        <th>Date</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    @forelse ($recentRecords as $record)
                    <tr>
                        <td class="table-cell-main">
                            <div class="table-cell-icon">
                                @if (($record['translation_type'] ?? 'document') === 'document')
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                                @else
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                                @endif
                            </div>
                            <span class="table-cell-text">
                                @if (($record['translation_type'] ?? 'document') === 'document')
                                    {{ $record['original_filename'] ?? 'Untitled Document' }}
                                @else
                                    {{ \Illuminate\Support\Str::limit($record['source_text'] ?? '', 45) }}
                                @endif
                            </span>
                        </td>
                        <td>
                            <span class="lang-pair">
                                {{ $record['source_language'] ?? '?' }}
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                                {{ $record['target_language'] ?? '?' }}
                            </span>
                        </td>
                        <td class="table-cell-muted">
                            {{ isset($record['created_at']) ? \Carbon\Carbon::parse($record['created_at'])->format('M j, Y') : '—' }}
                        </td>
                        <td>
                            <span class="status-pill status-pill--{{ $record['review_status'] ?? 'pending' }}">{{ ucfirst($record['review_status'] ?? 'pending') }}</span>
                        </td>
                    </tr>
                    @empty
                    <tr>
                        <td colspan="4" class="table-empty">
                            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="margin-bottom:8px;color:var(--border)"><path d="M5 8l6 6"/><path d="M4 14l6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="M22 22l-5-10-5 10"/><path d="M14 18h6"/></svg>
                            <p>No translations yet. <a href="{{ route('translate') }}" class="link">Start your first one</a>.</p>
                        </td>
                    </tr>
                    @endforelse
                </tbody>
            </table>
        </div>
    </div>

</div>
@endsection

@section('scripts')
<script>
    // Real-time dashboard: refresh stats every 30 seconds
    (function () {
        var INTERVAL = 30000; // 30 seconds
        var timer;

        function refreshDashboard() {
            fetch(window.location.href, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(function (res) { return res.text(); })
            .then(function (html) {
                var parser = new DOMParser();
                var doc = parser.parseFromString(html, 'text/html');

                // Update stat cards
                document.querySelectorAll('.stat-card__value').forEach(function (el, i) {
                    var newEl = doc.querySelectorAll('.stat-card__value')[i];
                    if (newEl && el.textContent !== newEl.textContent) {
                        el.textContent = newEl.textContent;
                        el.style.transition = 'color 0.4s';
                        el.style.color = 'var(--primary)';
                        setTimeout(function () { el.style.color = ''; }, 800);
                    }
                });

                // Update recent translations table body
                var oldTbody = document.querySelector('.table tbody');
                var newTbody = doc.querySelector('.table tbody');
                if (oldTbody && newTbody) {
                    oldTbody.innerHTML = newTbody.innerHTML;
                }
            })
            .catch(function () { /* silent fail — no broken UI */ });
        }

        // Start polling
        timer = setInterval(refreshDashboard, INTERVAL);

        // Stop polling when tab is hidden, resume when visible
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                clearInterval(timer);
            } else {
                refreshDashboard();
                timer = setInterval(refreshDashboard, INTERVAL);
            }
        });
    })();
</script>
@endsection
