<?php

namespace App\Services;

/**
 * Shared stat computation for translation_history records.
 *
 * Extracted from DashboardController::computeStats() so the admin user-detail
 * page can reuse the same totals for a single user's records.
 *
 * Also hosts reusable aggregations (period-over-period deltas, sparklines,
 * language-pair mix, quality-by-pair) that the user and admin dashboards share.
 */
class TranslationStatsService
{
    /**
     * Compute dashboard stat values from an array of translation_history records.
     *
     * @param  array<int, array>  $records  Rows (arrays) with translation_type,
     *                                      source_text, created_at keys.
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
                // Real source word count where available; fall back for legacy rows.
                $wordsTranslated += (int) ($r['document_word_count'] ?? static::estimateDocumentWords($r));
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

    /**
     * Word count for a legacy document row without a real document_word_count.
     *
     * Backfilled rows won't have per-block source text persisted, so we keep a
     * conservative estimate rather than the old flat 250. New translations are
     * always counted accurately.
     */
    private static function estimateDocumentWords(array $record): int
    {
        $sourceText = $record['source_text'] ?? '';
        if ($sourceText !== '') {
            return str_word_count($sourceText);
        }
        return 0;
    }

    /**
     * Total words for a single record (document or text) using real data.
     */
    public static function wordsForRecord(array $record): int
    {
        $isDocument = ($record['translation_type'] ?? '') === 'document';
        if ($isDocument) {
            return (int) ($record['document_word_count'] ?? static::estimateDocumentWords($record));
        }

        return str_word_count($record['source_text'] ?? '');
    }

    /**
     * Count of records created during a given date range (inclusive).
     *
     * @param  array<int, array>  $records
     * @param  \DateTimeInterface $from
     * @param  \DateTimeInterface $to
     * @return int
     */
    public static function countInRange(array $records, \DateTimeInterface $from, \DateTimeInterface $to): int
    {
        $count = 0;
        foreach ($records as $r) {
            $created = $r['created_at'] ?? null;
            if (!$created) {
                continue;
            }
            try {
                $ts = \Carbon\Carbon::parse($created);
            } catch (\Throwable) {
                continue;
            }
            if ($ts->gte($from) && $ts->lte($to)) {
                $count++;
            }
        }

        return $count;
    }

    /**
     * Bucket a record set into a daily series for sparkline rendering.
     *
     * @param  array<int, array>  $records
     * @param  int                $days  Number of trailing days (default 30).
     * @return array<int, array{date: string, count: int}>
     */
    public static function dailySeries(array $records, int $days = 30): array
    {
        $start = now()->subDays($days - 1)->startOfDay();

        $series = [];
        for ($i = 0; $i < $days; $i++) {
            $date = $start->copy()->addDays($i)->toDateString();
            $series[$date] = ['date' => $date, 'count' => 0];
        }

        foreach ($records as $r) {
            $created = $r['created_at'] ?? null;
            if (!$created) {
                continue;
            }
            try {
                $date = \Carbon\Carbon::parse($created)->toDateString();
            } catch (\Throwable) {
                continue;
            }
            if (isset($series[$date])) {
                $series[$date]['count']++;
            }
        }

        return array_values($series);
    }

    /**
     * Language-pair distribution across all records, sorted most→least used.
     *
     * @param  array<int, array>  $records
     * @return array<int, array{pair: string, count: int, pct: float}>
     */
    public static function languagePairMix(array $records): array
    {
        $counts = [];
        foreach ($records as $r) {
            $src = $r['source_language'] ?? '';
            $tgt = $r['target_language'] ?? '';
            if ($src && $tgt) {
                $pair = $src . ' → ' . $tgt;
                $counts[$pair] = ($counts[$pair] ?? 0) + 1;
            }
        }

        arsort($counts);
        $total = array_sum($counts) ?: 1;

        return array_map(fn ($pair, $count) => [
            'pair' => $pair,
            'count' => $count,
            'pct' => round($count / $total * 100, 1),
        ], array_keys($counts), $counts);
    }

    /**
     * Average AI quality score across records that carry one.
     *
     * @param  array<int, array>  $records
     * @return float|null  Null when no records have a score.
     */
    public static function averageQuality(array $records): ?float
    {
        $scores = [];
        foreach ($records as $r) {
            $score = $r['quality_score'] ?? null;
            if ($score !== null && $score !== '') {
                $scores[] = (int) $score;
            }
        }

        if ($scores === []) {
            return null;
        }

        return round(array_sum($scores) / count($scores), 1);
    }

    /**
     * Average quality score grouped by language pair.
     *
     * @param  array<int, array>  $records
     * @return array<int, array{pair: string, avg: float, count: int}>
     */
    public static function qualityByPair(array $records): array
    {
        $groups = [];
        foreach ($records as $r) {
            $src = $r['source_language'] ?? '';
            $tgt = $r['target_language'] ?? '';
            $score = $r['quality_score'] ?? null;
            if ((!$src || !$tgt) || ($score === null || $score === '')) {
                continue;
            }
            $pair = $src . ' → ' . $tgt;
            $groups[$pair][] = (int) $score;
        }

        $result = [];
        foreach ($groups as $pair => $scores) {
            $result[] = [
                'pair' => $pair,
                'avg' => round(array_sum($scores) / count($scores), 1),
                'count' => count($scores),
            ];
        }

        usort($result, fn ($a, $b) => $a['avg'] <=> $b['avg']);

        return $result;
    }

    /**
     * Soft percentage change between two values, for trend indicators.
     *
     * @return int  e.g. 25 for +25%, -10 for -10%. Returns 0 when baseline is 0.
     */
    public static function deltaPercent(int|float $current, int|float $previous): int
    {
        if ((float) $previous <= 0) {
            return $current > 0 ? 100 : 0;
        }

        return (int) round(($current - $previous) / $previous * 100);
    }
}