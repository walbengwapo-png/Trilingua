@props([
    'label' => '',
    'pct' => 0,
    'value' => '',
    'sub' => '',
    'tone' => 'primary', // primary|good|medium|bad|neutral
])

@php
    $pctClamped = max(0, min(100, (float) $pct));
    $toneClass = match ($tone) {
        'good' => 'bar-row__fill--good',
        'medium' => 'bar-row__fill--medium',
        'bad' => 'bar-row__fill--bad',
        'neutral' => 'bar-row__fill--neutral',
        default => '',
    };
@endphp

<div class="bar-row">
    <span class="bar-row__label" title="{{ $label }}">{{ $label }}</span>
    <div class="bar-row__track">
        <div class="bar-row__fill {{ $toneClass }}" style="width: {{ $pctClamped }}%"></div>
    </div>
    <span class="bar-row__value">
        {{ $value }}
        @if ($sub !== '')
            <span class="bar-row__sub">{{ $sub }}</span>
        @endif
    </span>
</div>