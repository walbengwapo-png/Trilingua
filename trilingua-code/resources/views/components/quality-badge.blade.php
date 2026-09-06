@props([
    'score' => null, // int|null
])

@php
    $quality = \App\Support\TranslationPresentation::quality($score === null || $score === '' ? null : (int) $score);
    if ($quality['score'] === null) {
        $cls = 'quality-badge--empty';
        $label = 'Not scored';
    } elseif ($quality['risk'] === 'low') {
        $cls = 'quality-badge--good';
        $label = $quality['text'];
    } elseif ($quality['risk'] === 'medium') {
        $cls = 'quality-badge--medium';
        $label = $quality['text'];
    } else {
        $cls = 'quality-badge--poor';
        $label = $quality['text'];
    }
@endphp

<span class="quality-badge {{ $cls }}" title="Quality confidence score from 0 to 100. Lower scores need more human review.">
    <span class="quality-badge__dot"></span>{{ $label }}
</span>
