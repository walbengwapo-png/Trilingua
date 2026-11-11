@props(['record', 'details' => false])
@php($quality = \App\Support\TranslationQuality::describe($record instanceof \Illuminate\Database\Eloquent\Model ? $record->toArray() : $record))
<div class="translation-quality" title="{{ $quality['explanation'] }}">
    <span class="quality-score">
        <span class="quality-score__dot quality-score__dot--{{ $quality['level'] }}" aria-hidden="true"></span>
        {{ $quality['label'] }}
    </span>
    @if ($quality['coverage'])
        <span class="translation-quality__note">{{ $quality['coverage'] }}</span>
    @endif
    @if ($details)
        <p class="translation-quality__note">{{ $quality['explanation'] }}</p>
    @endif
</div>
