@props([
    'score' => null, // int|null
])

@php
    if ($score === null || $score === '' || (int) $score < 0) {
        $cls = 'quality-badge--empty';
        $label = '—';
    } elseif ((int) $score >= 70) {
        $cls = 'quality-badge--good';
        $label = (string) (int) $score;
    } elseif ((int) $score >= 40) {
        $cls = 'quality-badge--medium';
        $label = (string) (int) $score;
    } else {
        $cls = 'quality-badge--poor';
        $label = (string) (int) $score;
    }
@endphp

<span class="quality-badge {{ $cls }}">
    <span class="quality-badge__dot"></span>{{ $label }}
</span>