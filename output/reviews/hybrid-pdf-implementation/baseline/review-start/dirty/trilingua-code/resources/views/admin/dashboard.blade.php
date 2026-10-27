@extends('layouts.app')

@section('title', 'Admin Dashboard')

@section('styles')
    @vite(['resources/css/views/admin.css', 'resources/css/views/dashboard-common.css'])
@endsection

@section('content')
<div class="stack">

    {{-- Page header --}}
    <div class="review-page-header">
        <div class="review-page-header__title">
            <h2>Admin Dashboard</h2>
            <p>Review throughput, quality health and AI engine performance.</p>
        </div>
        <div class="review-page-header__controls">
            <a href="{{ route('admin.dashboard.export.review-trends') }}" class="review-btn">Export Review Trends</a>
            <a href="{{ route('admin.dashboard.export.flags') }}" class="review-btn">Export Flag Report</a>
            <a href="{{ route('admin.dashboard.export.users') }}" class="review-btn">Export Users</a>
            <a href="{{ route('admin.review.index') }}" class="review-btn">Open Review Queue</a>
        </div>
    </div>

    {{-- Trended KPI cards --}}
    <div class="kpi-grid">
        <x-kpi-card
            label="Pending Review"
            :value="$stats['pending']"
            :delta="$stats['pendingDelta'] ?? null"
            sub="7-day submission trend"
            link="{{ route('admin.review.index') }}"
            linkText="Open queue" />

        <x-kpi-card
            label="Review Completion"
            value="{{ $stats['completionRate'] }}%"
            sub="Reviewed of all submitted"
            link="{{ route('admin.review.index') }}"
            linkText="Review stack" />

        <x-kpi-card
            label="Avg AI Review Signal"
            :value="$avgQuality === null ? '—' : $avgQuality"
            sub="Automated AI review signal, not human-verified"
            size="sm" />

        <x-kpi-card
            label="Avg Turnaround"
            :value="$turnaround === null ? '—' : $turnaround['mean'] . 'h'"
            :sub="$turnaround === null ? 'n/a until first review' : 'p50 ' . $turnaround['p50'] . 'h · p90 ' . $turnaround['p90'] . 'h'"
            size="sm" />
    </div>

    <div class="admin-grid-2">
        {{-- Submission volume sparkline --}}
        <div class="review-table-card">
            <h3 class="card-title">Submission Volume (30 days)</h3>
            @if (empty($reviewSparkline))
                <p class="empty-state">No submissions yet.</p>
            @else
                <x-sparkline :series="$reviewSparkline" />
                <p class="kpi-card__sub">
                    {{ count($reviewSparkline) }} days · peak {{ max(array_column($reviewSparkline, 'count')) }} / day
                </p>
            @endif
        </div>

        {{-- Review Activity trend --}}
        <div class="review-table-card">
            <h3 class="card-title">Review Activity Trend
                <a href="{{ route('admin.dashboard.export.review-trends') }}" class="review-btn" style="float:right;font-size:0.78rem">Export CSV</a>
            </h3>
            @if ($activityOverTime->isEmpty())
                <p class="empty-state">No review activity in the last 30 days. Reviews (verify/edit/flag) are recorded in the queue — open it to start reviewing.</p>
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

    {{-- Flag root-cause report --}}
    <div class="review-table-card">
        <h3 class="card-title">Flagged Translations — Root Causes
            <a href="{{ route('admin.dashboard.export.flags') }}" class="review-btn" style="float:right;font-size:0.78rem">Export CSV</a>
        </h3>
        @if (empty($flagReasonBreakdown))
            <p class="empty-state">No flagged translations yet. Items get flagged from the review queue — open it to flag when a translation needs attention.</p>
        @else
            @php
                $flagMax = max($flagReasonBreakdown);
            @endphp
            <div class="panel-grid panel-grid--2">
                <div>
                    @foreach ($flagReasonBreakdown as $reason => $count)
                        <x-bar-meter
                            label="{{ $reason }}"
                            :pct="($count / $flagMax) * 100"
                            :value="$count"
                            tone="bad" />
                    @endforeach
                </div>
                <div>
                    <h4 class="kpi-card__sub" style="margin:0 0 8px;text-transform:uppercase;letter-spacing:.03em">Flagged by Language Pair</h4>
                    @forelse ($langPairFlags as $pair)
                        <x-bar-meter
                            label="{{ $pair['pair'] }}"
                            :pct="($pair['count'] / max(1, max(array_column($langPairFlags, 'count')))) * 100"
                            :value="$pair['count']"
                            tone="neutral" />
                    @empty
                        <p class="empty-state">None.</p>
                    @endforelse

                    <h4 class="kpi-card__sub" style="margin:16px 0 8px;text-transform:uppercase;letter-spacing:.03em">Flagged by Type</h4>
                    @forelse ($typeBreakdown as $type => $count)
                        <x-bar-meter
                            label="{{ $type }}"
                            :pct="($count / max(1, max($typeBreakdown))) * 100"
                            :value="$count"
                            tone="neutral" />
                    @empty
                        <p class="empty-state">None.</p>
                    @endforelse
                </div>
            </div>
        @endif
    </div>

    <div class="admin-grid-2">
        {{-- Operational Health --}}
        <div class="review-table-card">
            <h3 class="card-title">Operational Health</h3>
            <div class="panel-grid panel-grid--2">
                <div class="stat-card stat-card--compact">
                    <div class="stat-card__label">Database</div>
                    <div class="stat-card__value" style="font-size:.95rem">
                        @if ($systemHealth['db_ok'])
                            <span class="status-dot status-dot--ok"></span> Connected
                        @else
                            <span class="status-dot status-dot--error"></span> Down
                        @endif
                    </div>
                </div>
                <div class="stat-card stat-card--compact">
                    <div class="stat-card__label">Storage</div>
                    <div class="stat-card__value" style="font-size:.95rem">
                        @if ($systemHealth['storage_ok'])
                            <span class="status-dot status-dot--ok"></span> Available
                        @else
                            <span class="status-dot status-dot--error"></span> Unavailable
                        @endif
                    </div>
                </div>
                <div class="stat-card stat-card--compact">
                    <div class="stat-card__label">Queue Pending</div>
                    <div class="stat-card__value">{{ $systemHealth['queue_pending'] }}</div>
                </div>
                <div class="stat-card stat-card--compact">
                    <div class="stat-card__label">Queue Failed</div>
                    <div class="stat-card__value">
                        @if ($systemHealth['queue_failed'] > 0)
                            <span class="stat-card__value--error">{{ $systemHealth['queue_failed'] }}</span>
                        @else
                            0
                        @endif
                    </div>
                </div>
            </div>
        </div>

        {{-- Translation Health Scorecard --}}
        <div class="review-table-card">
            <h3 class="card-title">Translation Health Scorecard</h3>
            @if (empty($healthScorecard['scored']))
                <p class="empty-state">No scored translations yet.</p>
            @else
                <x-bar-meter
                    label="Below threshold (&lt; 70)"
                    :pct="$healthScorecard['below_pct']"
                    :value="$healthScorecard['below_threshold'] . ' of ' . $healthScorecard['scored']"
                    :sub="$healthScorecard['below_pct'] . '%'"
                    tone="bad" />
                <h4 class="kpi-card__sub" style="margin:18px 0 8px;text-transform:uppercase;letter-spacing:.03em">Dominant Issue</h4>
                @if ($healthScorecard['dominant_issue'])
                    <p style="margin:0 0 10px;font-size:.9rem">
                        <span class="quality-badge quality-badge--medium">{{ $healthScorecard['dominant_issue']['category'] }}</span>
                        <span class="text-muted">{{ $healthScorecard['dominant_issue']['count'] }} occurrences</span>
                    </p>
                @else
                    <p class="empty-state">None.</p>
                @endif
                @foreach ($healthScorecard['issue_distribution'] as $issue)
                    <x-bar-meter
                        label="{{ $issue['category'] }}"
                        :pct="$issue['pct']"
                        :value="$issue['count']"
                        :sub="$issue['pct'] . '%'"
                        tone="medium" />
                @endforeach
            @endif
        </div>
    </div>

    @if ($engineHealth['samples'] > 0)
        <div class="review-table-card">
            <h3 class="card-title">AI Engine Performance
                <span class="text-muted" style="font-weight:400;text-transform:none;letter-spacing:0;font-size:.8rem">across {{ $engineHealth['samples'] }} recorded metric samples; {{ $engineHealth['legacy_samples'] }} legacy</span>
            </h3>
            <div class="panel-grid panel-grid--4">
                <div class="stat-card stat-card--compact">
                    <div class="stat-card__label">Comparable recorded elapsed time</div>
                    <div class="stat-card__value">{{ $engineHealth['avg_latency_ms'] === null ? 'Unavailable' : $engineHealth['avg_latency_ms'] . ' ms' }}</div>
                    <p class="text-muted">{{ $engineHealth['latency_scope'] ?? 'Unknown or incompatible scopes' }} · {{ $engineHealth['latency_samples'] }} of {{ $engineHealth['samples'] }} samples</p>
                </div>
                <div class="stat-card stat-card--compact">
                    <div class="stat-card__label">Cache Hit Rate</div>
                    <div class="stat-card__value">{{ $engineHealth['cache_hit_rate'] === null ? 'Unavailable' : $engineHealth['cache_hit_rate'] . '%' }}</div>
                    <p class="text-muted">Known lookup units · {{ $engineHealth['cache_samples'] }} of {{ $engineHealth['samples'] }} samples</p>
                </div>
                <div class="stat-card stat-card--compact">
                    <div class="stat-card__label">Block rework rate</div>
                    <div class="stat-card__value">{{ $engineHealth['retranslation_rate'] === null ? 'Unavailable' : $engineHealth['retranslation_rate'] . '%' }}</div>
                    <p class="text-muted">Operational count, not quality · {{ $engineHealth['rework_samples'] }} of {{ $engineHealth['samples'] }} samples</p>
                </div>
                <div class="stat-card stat-card--compact">
                    <div class="stat-card__label">Last observed provider/model</div>
                    <div class="stat-card__value" style="font-size:.8rem">
                        @if ($engineHealth['last_observed_providers'] !== [])
                            @foreach ($engineHealth['last_observed_providers'] as $observed)
                                <div>{{ $observed['provider'] }} / {{ $observed['model'] }}</div>
                            @endforeach
                        @else
                            <span class="text-muted">Unavailable</span>
                        @endif
                    </div>
                    <p class="text-muted">Recorded: {{ $engineHealth['last_observed_at'] ?? 'Observation time unavailable' }} · {{ $engineHealth['attribution_samples'] }} of {{ $engineHealth['samples'] }} samples</p>
                </div>
            </div>
            <p class="text-muted">Latest recorded usage — retained translation result; full operation accounting unavailable:</p>
            @foreach (['input', 'output'] as $direction)
                @php $usage = $engineHealth['latest_usage'][$direction] ?? ['value' => null, 'provenance' => 'unknown', 'method' => null]; @endphp
                <p class="text-muted">{{ ucfirst($direction) }}: {{ $usage['value'] === null ? 'Unavailable' : $usage['value'] }} ({{ $usage['provenance'] }}{{ $usage['method'] ? ', ' . $usage['method'] : '' }})</p>
            @endforeach
        </div>
    @endif

    {{-- Reviewer Leaderboard --}}
    <div class="review-table-card">
        <h3 class="card-title">Reviewer Leaderboard</h3>
        @if ($topReviewers->isEmpty())
            <p class="empty-state">No review actions recorded yet. Verify/edit/flag in the review queue to populate this leaderboard.</p>
        @else
            <table class="review-table">
                <thead><tr><th>Reviewer</th><th>Actions</th><th></th></tr></thead>
                <tbody>
                    @foreach ($topReviewers as $row)
                    <tr>
                        <td>{{ $row['name'] }}</td>
                        <td><span class="count-badge">{{ $row['count'] }}</span></td>
                        <td></td>
                    </tr>
                    @endforeach
                </tbody>
            </table>
        @endif
    </div>

    {{-- User activity table --}}
    <div class="review-table-card">
        <h3 class="card-title">User Activity (Last 30 Days)
            <a href="{{ route('admin.dashboard.export.users') }}" class="review-btn" style="float:right;font-size:0.78rem">Export CSV</a>
        </h3>
        @if (empty($userActivity))
            <p class="empty-state">No user activity in the last 30 days.</p>
        @else
            <table class="review-table">
                <thead>
                    <tr>
                        <th>User</th>
                        <th>Email</th>
                        <th>Translations</th>
                        <th>Documents</th>
                        <th>Text</th>
                        <th>Last Active</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    @foreach ($userActivity as $row)
                    <tr>
                        <td>{{ $row['name'] }}</td>
                        <td>{{ $row['email'] }}</td>
                        <td><span class="count-badge">{{ $row['translation_count'] }}</span></td>
                        <td>{{ $row['doc_count'] }}</td>
                        <td>{{ $row['text_count'] }}</td>
                        <td>{{ \Carbon\Carbon::parse($row['last_active'])->diffForHumans() }}</td>
                        <td><a href="{{ route('admin.users.show', $row['user_id']) }}" class="review-btn" style="font-size:0.78rem">View</a></td>
                    </tr>
                    @endforeach
                </tbody>
            </table>
        @endif
    </div>

    {{-- System Activity --}}
    <div class="review-table-card">
        <h3 class="card-title">System Activity</h3>
        @if (empty($recentActivity))
            <p class="empty-state">No system activity recorded yet. Appearances here include review actions and account events (logins/logouts).</p>
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

</div>
@endsection
