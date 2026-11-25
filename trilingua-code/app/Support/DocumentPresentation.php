<?php

namespace App\Support;

class DocumentPresentation
{
    public const STATUS_MESSAGES = [
        'complete' => 'Translation complete.',
        'partial' => 'Partly translated. Some areas were left unchanged from the original document.',
        'untranslated' => 'No translated content was produced. The document remains unchanged.',
    ];

    public const PREVIEW_MESSAGE = 'Experimental image-text translation was used. Check the wording and layout carefully.';

    public const UNKNOWN_REASON_MESSAGE = 'This area could not be translated or placed reliably and was left unchanged.';

    public const REASON_MESSAGES = [
        'source_text_unchanged' => 'The wording remained in the original language and needs review.',
        'translation_missing' => 'No reliable translation was available for this area, so the original was kept.',
        'ocr_acceptance_hold' => 'Image-text reading has not passed the required checks for this content.',
        'ocr_disabled' => 'Text in images and scanned pages was skipped.',
        'hidden_or_occluded_native' => 'The text is hidden or covered by other content.',
        'low_confidence_or_neighbor_overlap' => 'The text could not be read reliably or separated from nearby content.',
        'ambiguous_native_ocr_overlap' => 'The system could not reliably separate image text from overlapping document text.',
        'native_fit_hold' => 'The translated text could not fit without affecting the layout.',
        'Target does not fit at the 10 pt/bounded shrink minimum' => 'The translated text could not fit without affecting the layout.',
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

    public static function additionalWarnings(array $record): array
    {
        $areas = self::unchangedAreas($record);
        $summary = $record['sidecar']['content_summary'] ?? [];
        $warnings = [];
        foreach ($record['sidecar']['extraction']['warnings'] ?? [] as $warning) {
            if (preg_match('/^Page (\d+): original region retained \((.+)\)\.$/', $warning, $match)) {
                $message = self::REASON_MESSAGES[$match[2]] ?? self::UNKNOWN_REASON_MESSAGE;
                if (! in_array(['page' => (int) $match[1], 'message' => $message], $areas, true)) {
                    $warnings[] = 'Page '.$match[1].': '.$message;
                }
            } elseif (str_starts_with($warning, 'Original region retained:')) {
                if (! $areas) {
                    $warnings[] = self::UNKNOWN_REASON_MESSAGE;
                }
            } elseif (preg_match('/^(Partial|Untranslated): \d+ translated,/', $warning)) {
                if (! isset($summary['status'])) {
                    $warnings[] = self::STATUS_MESSAGES[str_starts_with($warning, 'Partial') ? 'partial' : 'untranslated'];
                }
            } elseif (str_starts_with($warning, 'Unverified OCR preview:')) {
                if (($summary['ocr_mode'] ?? null) !== 'preview') {
                    $warnings[] = self::PREVIEW_MESSAGE;
                }
            } else {
                $warnings[] = $warning;
            }
        }

        return array_unique($warnings);
    }
}
