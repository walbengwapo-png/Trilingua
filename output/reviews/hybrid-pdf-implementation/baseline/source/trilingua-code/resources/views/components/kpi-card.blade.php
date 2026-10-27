@props([
    'label' => '',
    'value' => '',
    'sub' => '',
    'delta' => null,  // int|null: % change vs previous period
    'link' => null,   // string URL or null
    'linkText' => 'View all',
    'size' => 'lg',   // lg|sm
])

@php
    $deltaCss = '';
    $arrow = '';
    if ($delta !== null) {
        if ($delta > 0) {
            $deltaCss = 'delta--up';
            $arrow = '▲';
        } elseif ($delta < 0) {
            $deltaCss = 'delta--down';
            $arrow = '▼';
        } else {
            $deltaCss = 'delta--flat';
            $arrow = '–';
        }
    }
@endphp

<div class="kpi-card">
    <div class="kpi-card__row">
        <span class="kpi-card__label">{{ $label }}</span>
        @if ($delta !== null)
            <span class="delta {{ $deltaCss }}"><span class="delta__arrow">{{ $arrow }}</span> {{ abs($delta) }}%</span>
        @endif
    </div>
    <div class="kpi-card__value {{ $size === 'sm' ? 'kpi-card__value--sm' : '' }}">{{ $value }}</div>
    @if ($sub !== '')
        <p class="kpi-card__sub">{{ $sub }}</p>
    @endif
    @if ($link)
        <a href="{{ $link }}" class="kpi-card__link">{{ $linkText }} &rarr;</a>
    @endif
</div>