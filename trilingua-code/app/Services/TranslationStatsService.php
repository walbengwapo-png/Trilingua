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
        $totalTexts            = 0;
        $translationsThisMonth = 0;
        $wordsTranslated       = 0;
        $langPairCounts        = [];

        foreach ($records as $r) {
            $isDocument = ($r['translation_type'] ?? '') === 'document';

            if ($isDocument) {
                $totalDocs++;
                $wordsTranslated += 250;
            } else {
                $totalTexts++;
                $wordsTranslated += str_word_count($r['source_text'] ?? '');
            }

            if (str_starts_with($r['created_at'] ?? '', $currentMonthPrefix)) {
                $translationsThisMonth++;
            }

            $src = $r['source_language'] ?? '';
            $tgt = $r['target_language'] ?? '';
            if ($src && $tgt) {
                $pair = $src . ' → ' . $tgt;
                $langPairCounts[$pair] = ($langPairCounts[$pair] ?? 0) + 1;
            }
        }

        arsort($langPairCounts);
        $topLangPair = array_key_first($langPairCounts);

        return [
            'totalDocs'             => $totalDocs,
            'totalTexts'            => $totalTexts,
            'translationsThisMonth' => $translationsThisMonth,
            'wordsTranslated'       => $wordsTranslated,
            'topLangPair'           => $topLangPair ?: '—',
        ];
    }
}