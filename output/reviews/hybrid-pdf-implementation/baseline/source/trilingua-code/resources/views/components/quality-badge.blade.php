@props([
    'score' => null, // int|null
])

@php
    $unavailable = $score === null || $score === '' || (int) $score < 0;
    $label = $unavailable ? 'Unavailable' : (string) (int) $score;
@endphp

<span class="quality-badge quality-badge--empty"
      title="Automated AI review signal for triage only — not human-verified accuracy."
      role="img"
      aria-label="Automated AI review signal, not human-verified accuracy: {{ $unavailable ? 'unavailable' : $label . ' of 100' }}">
    <span class="quality-badge__dot" aria-hidden="true"></span>{{ $label }}
</span>
