@props(['record'])
@php
    $analysis = $record['sidecar']['analysis'] ?? [];
    $state = $analysis['status'] ?? 'legacy';
    $type = $analysis['document_type'] ?? ($state === 'legacy' ? ($record['sidecar']['document_type'] ?? null) : null);
    $words = $analysis['extracted_words'] ?? $record['source_word_metadata']['known_words'] ?? $record['document_word_count'] ?? null;
    $incomplete = in_array($record['sidecar']['content_summary']['status'] ?? null, ['partial', 'untranslated'], true)
        || in_array($record['source_word_metadata']['completeness'] ?? null, ['partial', 'missing'], true);
@endphp
<section class="translation-analysis" aria-label="Document analysis">
    <h4 class="detail-modal__section-title">Document analysis</h4>
    @if ($state !== 'analyzed')
        <p class="translation-quality__note">
            {{ match ($state) {
                'unavailable' => 'A document summary could not be prepared. Saved document information is shown below.',
                'not_run' => 'A document summary was not prepared for this translation.',
                default => 'A document summary was not saved for this older translation.',
            } }}
        </p>
    @endif
    <dl class="translation-analysis__facts">
        <div><dt>Domain</dt><dd>{{ $analysis['domain'] ?? '' ?: 'Not detected' }}</dd></div>
        <div><dt>Document type</dt><dd>{{ $type ? ucwords(str_replace('_', ' ', $type)) : 'Not recorded' }}</dd></div>
        <div><dt>Words read{{ $incomplete ? ' (incomplete count)' : '' }}</dt><dd>{{ $words ?? 'Not recorded' }}</dd></div>
    </dl>
    <p class="translation-quality__note">This counts the words the system could read, not the words successfully translated. Unreadable areas may be excluded.</p>
    @if (!empty($analysis['summary']))
        <p class="translation-analysis__summary">{{ $analysis['summary'] }}</p>
    @endif
    @if ($state === 'analyzed')
        <details>
            <summary>More analysis details</summary>
            <dl class="translation-analysis__facts">
                <div><dt>Writing style</dt><dd>{{ $analysis['writing_style'] ?? 'Not recorded' }}</dd></div>
                <div><dt>Detected language</dt><dd>{{ $analysis['language'] ?? 'Not recorded' }}</dd></div>
            </dl>
            <p class="translation-quality__note">This is an automated description of the document, not a check of translation accuracy. Each list shows up to 50 items.</p>
            @if (!empty($analysis['sections']))
                <h5>Sections</h5>
                <ul>@foreach ($analysis['sections'] as $section)<li>{{ $section['title'] }}</li>@endforeach</ul>
            @endif
            @foreach (['terminology' => 'Terminology', 'entities' => 'Entities', 'repeated_phrases' => 'Repeated phrases'] as $key => $label)
                @if (!empty($analysis[$key]))
                    <h5>{{ $label }}</h5>
                    <p>{{ implode(', ', $analysis[$key]) }}</p>
                @endif
            @endforeach
            @if (!empty($analysis['abbreviations']))
                <h5>Abbreviations</h5>
                <ul>@foreach ($analysis['abbreviations'] as $item)<li>{{ $item['abbreviation'] }} — {{ $item['full_form'] }}</li>@endforeach</ul>
            @endif
            @if (!empty($analysis['translation_terms']))
                <h5>Suggested translation terms</h5>
                <ul>@foreach ($analysis['translation_terms'] as $term)<li>{{ $term['source'] }} → {{ $term['target'] }}</li>@endforeach</ul>
            @endif
        </details>
    @endif
</section>
