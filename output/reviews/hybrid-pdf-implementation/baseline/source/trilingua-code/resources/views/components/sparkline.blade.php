@props([
    'series' => [],   // array<int, array{date: string, count: int}>
])

@php
    $max = 0;
    foreach ($series as $point) {
        $max = max($max, (int) ($point['count'] ?? 0));
    }
    $max = max(1, $max);
@endphp

<div class="sparkline" role="img" aria-label="Activity over time">
    @foreach ($series as $point)
        @php
            $h = round(((int) ($point['count'] ?? 0)) / $max * 100, 1);
        @endphp
        <div class="sparkline__bar"
             style="height: {{ max(2, $h) }}%"
             title="{{ $point['date'] ?? '' }}: {{ $point['count'] ?? 0 }}"></div>
    @endforeach
</div>