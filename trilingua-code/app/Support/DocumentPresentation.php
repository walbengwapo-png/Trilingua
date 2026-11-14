<?php

namespace App\Support;

class DocumentPresentation
{
    public const STATUS_MESSAGES = [
        'complete' => 'Translation complete.',
        'partial' => 'Some parts remain in the original language. Review the result before using it.',
        'untranslated' => 'No translated result was created. The document still contains the original content.',
    ];

    public const PREVIEW_MESSAGE = 'Text was read from images using an experimental option. Check the wording and page layout before using the result.';

    public const UNKNOWN_REASON_MESSAGE = 'This area could not be translated or placed reliably and was left unchanged.';

    public const REASON_MESSAGES = [
        'ocr_acceptance_hold' => 'The text in this image could not be read reliably enough to translate.',
        'hidden_or_occluded_native' => 'The text is hidden or covered by other content.',
        'low_confidence_or_neighbor_overlap' => 'The text could not be read reliably or separated from nearby content.',
        'ambiguous_native_ocr_overlap' => 'The system could not reliably separate image text from overlapping document text.',
        'native_fit_hold' => 'The translated text would not fit in this space, so the original text was kept.',
        'Target does not fit at the 10 pt/bounded shrink minimum' => 'The translated text would not fit in this space, so the original text was kept.',
        'outlined_text_excluded' => 'This artwork may contain text that could not be read as ordinary document text.',
        'filtered_or_unextracted_native' => 'Some document text could not be read for translation.',
        'aggregate_decoded_pixel_budget_exceeded' => 'The images exceeded the processing limit for one translation.',
        'image_safety_hold' => 'This image could not be changed reliably while preserving the surrounding content.',
    ];

    public static function unchangedAreas(array $record): array
    {
        $areas = [];
        foreach ($record['sidecar']['render_plan']['regions'] ?? [] as $region) {
            if (($region['status'] ?? null) !== 'held') {
                continue;
            }
            $page = isset($region['page']) && is_int($region['page']) && $region['page'] >= 0
                ? $region['page'] + 1 : null;
            $message = self::REASON_MESSAGES[$region['reason'] ?? ''] ?? self::UNKNOWN_REASON_MESSAGE;
            $areas[($page ?? 'unknown').'|'.$message] = ['page' => $page, 'message' => $message];
        }

        return array_values($areas);
    }
}
