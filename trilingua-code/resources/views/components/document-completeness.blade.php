@props(['record', 'details' => false])
@php
    $summary = $record['sidecar']['content_summary'] ?? [];
    $message = \App\Support\DocumentPresentation::STATUS_MESSAGES[$summary['status'] ?? ''] ?? null;
    $incomplete = in_array($summary['status'] ?? null, ['partial', 'untranslated'], true);
@endphp
@if ($message)
    <div class="document-completeness" role="note">
        <p>{{ $message }}</p>
        @if (($summary['ocr_mode'] ?? null) === 'preview')
            <p>{{ \App\Support\DocumentPresentation::PREVIEW_MESSAGE }}</p>
        @endif
        @if ($details && $incomplete)
            @php($areas = \App\Support\DocumentPresentation::unchangedAreas($record))
            <p>Compare the affected pages with the original before using this file.</p>
            @if ($areas)
                <details>
                    <summary>Where and why areas were left unchanged</summary>
                    <ul>
                        @foreach ($areas as $area)
                            <li><strong>{{ $area['page'] !== null ? 'Page '.$area['page'] : 'Page not recorded' }}:</strong> {{ $area['message'] }}</li>
                        @endforeach
                    </ul>
                </details>
            @else
                <p>Page details were not saved for this translation. Compare the downloaded file with the original.</p>
            @endif
        @endif
    </div>
@endif
