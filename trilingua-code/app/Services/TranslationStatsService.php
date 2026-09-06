<?php

namespace App\Services;

/**
 * Shared stat computation for translation_history records.
 *
 * Extracted from DashboardController::computeStats() so the admin user-detail
 * page can reuse the same totals for a single user's records.
 */
class TranslationStatsService
{
    /**
     * Compute dashboard stat values from an array of translation_history records.
     *
     * @param  array<int, array>  $records  Rows (arrays) with translation_type,
     *                                      source_text and created_at keys.
     * @return array{totalDocs: int, translationsThisMonth: int, wordsTranslated: int}
     */
    public static function compute(array $records): array
    {
        $currentMonthPrefix = date('Y-m');

        $totalDocs             = 0;
        $translationsThisMonth = 0;
        $wordsTranslated       = 0;

        foreach ($records as $r) {
            $isDocument = ($r['translation_type'] ?? '') === 'document';

            if ($isDocument) {
                $totalDocs++;
                // Document records have no stored word count; use a fixed estimate of
                // 250 words per document as a reasonable default.
                $wordsTranslated += 250;
            } else {
                // Text record — count actual words in the source text.
                $wordsTranslated += str_word_count($r['source_text'] ?? '');
            }

            // Count records created in the current calendar month.
            if (str_starts_with($r['created_at'] ?? '', $currentMonthPrefix)) {
                $translationsThisMonth++;
            }
        }

        return [
            'totalDocs'             => $totalDocs,
            'translationsThisMonth' => $translationsThisMonth,
            'wordsTranslated'       => $wordsTranslated,
        ];
    }
}