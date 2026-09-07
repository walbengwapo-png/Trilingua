@extends('layouts.app')

@section('title','Dashboard')

@section('styles')
    @vite(['resources/css/views/dashboard.css', 'resources/css/views/dashboard-common.css'])
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

    {{-- KPI stat cards (trended) --}}
    <div class="cards-grid">
        @php
            $totals = $stats['totals'] ?? ['total' => 0, 'documents' => 0, 'texts' => 0, 'words' => 0, 'bookmarked' => 0];
            $deltas = $stats['deltas'] ?? ['translationsDelta' => 0, 'wordsDelta' => 0];
            $avgQuality = $stats['avgQuality'] ?? null;
        @endphp

        <div class="kpi-card">
            <div class="kpi-card__row">
                <span class="kpi-card__label">Total Translations</span>
                <span class="delta {{ ($deltas['translationsDelta'] ?? 0) > 0 ? 'delta--up' : (($deltas['translationsDelta'] ?? 0) < 0 ? 'delta--down' : 'delta--flat') }}">
                    <span class="delta__arrow">{{ ($deltas['translationsDelta'] ?? 0) > 0 ? '▲' : (($deltas['translationsDelta'] ?? 0) < 0 ? '▼' : '–') }}</span>
                    {{ abs($deltas['translationsDelta'] ?? 0) }}%
                </span>
            </div>
            <div class="kpi-card__value">{{ number_format($totals['total']) }}</div>
            <p class="kpi-card__sub">{{ $totals['documents'] }} documents &middot; {{ $totals['texts'] }} text translations</p>
        </div>

        <div class="kpi-card">
            <div class="kpi-card__row">
                <span class="kpi-card__label">Words Translated</span>
                <span class="delta {{ ($deltas['wordsDelta'] ?? 0) > 0 ? 'delta--up' : (($deltas['wordsDelta'] ?? 0) < 0 ? 'delta--down' : 'delta--flat') }}">
                    <span class="delta__arrow">{{ ($deltas['wordsDelta'] ?? 0) > 0 ? '▲' : (($deltas['wordsDelta'] ?? 0) < 0 ? '▼' : '–') }}</span>
                    {{ abs($deltas['wordsDelta'] ?? 0) }}%
                </span>
            </div>
            <div class="kpi-card__value">{{ number_format($totals['words']) }}</div>
            <p class="kpi-card__sub">Across {{ $totals['total'] }} translation{{ $totals['total'] === 1 ? '' : 's' }}</p>
        </div>

        <div class="kpi-card">
            <span class="kpi-card__label">Avg Quality Score</span>
            <div class="kpi-card__row">
                <div class="kpi-card__value">{{ $avgQuality === null ? '—' : number_format($avgQuality, 0) }}</div>
                @if ($avgQuality !== null)
                    <x-quality-badge :score="$avgQuality" />
                @endif
            </div>
            <p class="kpi-card__sub">AI-assessed across your recent translations</p>
        </div>

        <div class="kpi-card">
            <span class="kpi-card__label">Most Used Pair</span>
            <div class="kpi-card__value kpi-card__value--sm">{{ $stats['core']['topLangPair'] ?? '—' }}</div>
            @php $topPair = $stats['pairMix'][0] ?? null; @endphp
            @if ($topPair)
                <p class="kpi-card__sub">{{ $topPair['count'] }} translation{{ $topPair['count'] === 1 ? '' : 's' }} ({{ number_format($topPair['pct'], 1) }}% of usage)</p>
            @else
                <p class="kpi-card__sub">No translations yet</p>
            @endif
        </div>
    </div>

    {{-- Activity + Language mix --}}
    <div class="grid-2">
        <div class="panel">
            <div class="panel__header">
                <h2 class="panel__title">Activity (Last 30 Days)</h2>
                <span class="panel__hint">{{ array_sum(array_column($stats['sparkline'] ?? [], 'count')) }} translations</span>
            </div>
            @if (empty($stats['sparkline'] ?? []))
                <p class="panel-empty">No activity yet.</p>
            @else
                <x-sparkline :series="$stats['sparkline']" />
            @endif
        </div>

        <div class="panel">
            <h2 class="panel__title">Language Pair Mix</h2>
            @if (empty($stats['pairMix'] ?? []))
                <p class="panel-empty">No translations yet.</p>
            @else
                @foreach (array_slice($stats['pairMix'], 0, 6) as $mix)
                    <x-bar-meter :label="$mix['pair']" :pct="$mix['pct']" :value="$mix['count']" :sub="number_format($mix['pct'], 0) . '%'" />
                @endforeach
            @endif
        </div>
    </div>

    {{-- Quality by language pair --}}
    <div class="panel">
        <h2 class="panel__title">Quality by Language Pair</h2>
        @if (empty($stats['qualityByPair'] ?? []))
            <p class="panel-empty">No quality data available yet.</p>
        @else
            @foreach (array_slice($stats['qualityByPair'], 0, 8) as $qp)
                @php
                    $tone = $qp['avg'] >= 70 ? 'good' : ($qp['avg'] >= 40 ? 'medium' : 'bad');
                @endphp
                <x-bar-meter
                    :label="$qp['pair']"
                    :pct="$qp['avg']"
                    :value="number_format($qp['avg'], 0)"
                    :sub="'(' . $qp['count'] . ')'"
                    :tone="$tone"
                />
            @endforeach
        @endif
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
                        <th>Quality</th>
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
                                <a href="{{ route('history.detail', $record['id']) }}" style="color:var(--text);text-decoration:none">
                                @if (($record['translation_type'] ?? 'document') === 'document')
                                    {{ $record['original_filename'] ?? 'Untitled Document' }}
                                @else
                                    {{ \Illuminate\Support\Str::limit($record['source_text'] ?? '', 45) }}
                                @endif
                                </a>
                            </span>
                        </td>
                        <td>
                            <span class="lang-pair">
                                {{ $record['source_language'] ?? '?' }}
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                                {{ $record['target_language'] ?? '?' }}
                            </span>
                        </td>
                        <td>
                            <x-quality-badge :score="$record['quality_score'] ?? null" />
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
                        <td colspan="5" class="table-empty">
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

                // Update the KPI value elements
                document.querySelectorAll('.kpi-card__value').forEach(function (el, i) {
                    var newEl = doc.querySelectorAll('.kpi-card__value')[i];
                    if (newEl && el.textContent.trim() !== newEl.textContent.trim()) {
                        el.innerHTML = newEl.innerHTML;
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