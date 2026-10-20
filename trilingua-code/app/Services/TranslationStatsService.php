<?php

namespace App\Services;

use App\Models\TranslationHistory;

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
     * How many rows the PHP word-count pass reads per query.
     *
     * Word totals are the one statistic that cannot be expressed in SQL
     * without changing its meaning (see wordsNeedingPhpCount), so they stream
     * through the table in bounded batches instead of loading every row of a
     * user's history at once.
     */
    private const WORD_SCAN_CHUNK = 500;

    /**
     * Dashboard statistics for one user, aggregated by the database over every
     * row that user owns.
     *
     * The array helpers on this class stay correct for callers that already
     * hold a bounded row set, but they must never be handed a truncated one.
     * They used to be fed the newest 200 history rows, which silently
     * under-reported every lifetime total, word count, language mix and
     * quality average from the moment a user passed 200 translations — the
     * cap looked like real data because the numbers were plausible.
     *
     * @return array<string, mixed>
     */
    public static function forUser(int $userId): array
    {
        $now             = now();
        $thisPeriodStart = $now->copy()->subDays(30)->startOfDay();
        $prevPeriodStart = $now->copy()->subDays(60)->startOfDay();
        $prevPeriodEnd   = $now->copy()->subDays(30)->endOfDay();
        $monthStart      = $now->copy()->startOfMonth();
        $seriesStart     = $now->copy()->subDays(29)->startOfDay();

        $c = TranslationHistory::where('user_id', $userId)
            ->selectRaw('COUNT(*) AS total')
            ->selectRaw("SUM(CASE WHEN translation_type = 'document' THEN 1 ELSE 0 END) AS documents")
            ->selectRaw("SUM(CASE WHEN translation_type = 'text' THEN 1 ELSE 0 END) AS texts")
            ->selectRaw('SUM(CASE WHEN is_bookmarked THEN 1 ELSE 0 END) AS bookmarked')
            ->selectRaw('SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS this_month', [$monthStart])
            ->selectRaw('SUM(CASE WHEN created_at >= ? AND created_at <= ? THEN 1 ELSE 0 END) AS this_period', [$thisPeriodStart, $now])
            ->selectRaw('SUM(CASE WHEN created_at >= ? AND created_at <= ? THEN 1 ELSE 0 END) AS prev_period', [$prevPeriodStart, $prevPeriodEnd])
            ->selectRaw('SUM(CASE WHEN quality_score IS NOT NULL THEN 1 ELSE 0 END) AS scored')
            ->selectRaw('SUM(COALESCE(quality_score, 0)) AS score_sum')
            // Stored document counts are only trusted for document rows, exactly
            // as wordsForRecord() does: a text row always counts its own words.
            ->selectRaw("SUM(CASE WHEN translation_type = 'document' THEN COALESCE(document_word_count, 0) ELSE 0 END) AS stored_words")
            ->selectRaw("SUM(CASE WHEN translation_type = 'document' AND created_at >= ? THEN COALESCE(document_word_count, 0) ELSE 0 END) AS stored_words_this", [$thisPeriodStart])
            ->selectRaw("SUM(CASE WHEN translation_type = 'document' AND created_at >= ? AND created_at <= ? THEN COALESCE(document_word_count, 0) ELSE 0 END) AS stored_words_prev", [$prevPeriodStart, $prevPeriodEnd])
            ->first();

        $total      = (int) $c->total;
        $documents  = (int) $c->documents;
        $texts      = (int) $c->texts;
        $scored     = (int) $c->scored;
        $scoreSum   = (int) $c->score_sum;
        $storedWords = (int) $c->stored_words;

        // Words the database cannot judge: str_word_count() is locale-aware
        // (it returns 0 for scripts without word separators), so reimplementing
        // it as SQL arithmetic would quietly change what "words" means.
        $php = self::wordsNeedingPhpCount($userId, $thisPeriodStart, $prevPeriodStart, $prevPeriodEnd);

        $totalWords = $storedWords + $php['total'];
        $avgQuality = $scored > 0 ? round($scoreSum / $scored, 1) : null;

        $pairs        = self::pairCounts($userId);
        $qualityPairs = self::qualityByPairCounts($userId);

        return [
            'core' => [
                'totalDocs'             => $documents,
                'totalTexts'            => $texts,
                'translationsThisMonth' => (int) $c->this_month,
                'wordsTranslated'       => $totalWords,
                'topLangPair'           => array_key_first($pairs) ?: '—',
            ],
            'totals' => [
                'total'      => $total,
                'documents'  => $documents,
                'texts'      => $texts,
                'words'      => $totalWords,
                'bookmarked' => (int) $c->bookmarked,
            ],
            'deltas' => [
                'translationsDelta' => self::deltaPercent((int) $c->this_period, (int) $c->prev_period),
                'wordsDelta'        => self::deltaPercent(
                    (int) $c->stored_words_this + $php['this'],
                    (int) $c->stored_words_prev + $php['prev']
                ),
            ],
            'sparkline'     => self::dailySeriesSince($userId, $seriesStart),
            'pairMix'       => self::pairMixFromCounts($pairs),
            'qualityByPair' => $qualityPairs,
            'avgQuality'    => $avgQuality,
        ];
    }

    /**
     * Language-pair record counts, already sorted most→least used.
     *
     * @return array<string, int>
     */
    private static function pairCounts(int $userId): array
    {
        $rows = TranslationHistory::where('user_id', $userId)
            ->whereNotNull('source_language')->where('source_language', '<>', '')
            ->whereNotNull('target_language')->where('target_language', '<>', '')
            ->selectRaw('source_language, target_language, COUNT(*) AS n')
            ->groupBy('source_language', 'target_language')
            ->get();

        $counts = [];
        foreach ($rows as $row) {
            $counts[$row->source_language . ' → ' . $row->target_language] = (int) $row->n;
        }
        arsort($counts);

        return $counts;
    }

    /**
     * @param  array<string, int>  $counts
     * @return array<int, array{pair: string, count: int, pct: float}>
     */
    private static function pairMixFromCounts(array $counts): array
    {
        $total = array_sum($counts) ?: 1;

        $mix = [];
        foreach ($counts as $pair => $count) {
            $mix[] = [
                'pair'  => $pair,
                'count' => $count,
                'pct'   => round($count / $total * 100, 1),
            ];
        }

        return $mix;
    }

    /**
     * Average quality per language pair, weakest pair first.
     *
     * @return array<int, array{pair: string, avg: float, count: int}>
     */
    private static function qualityByPairCounts(int $userId): array
    {
        $rows = TranslationHistory::where('user_id', $userId)
            ->whereNotNull('quality_score')
            ->whereNotNull('source_language')->where('source_language', '<>', '')
            ->whereNotNull('target_language')->where('target_language', '<>', '')
            ->selectRaw('source_language, target_language')
            ->selectRaw('AVG(quality_score) AS avg_score')
            ->selectRaw('COUNT(*) AS n')
            ->groupBy('source_language', 'target_language')
            ->get();

        $result = [];
        foreach ($rows as $row) {
            $result[] = [
                'pair'  => $row->source_language . ' → ' . $row->target_language,
                'avg'   => round((float) $row->avg_score, 1),
                'count' => (int) $row->n,
            ];
        }

        usort($result, fn ($a, $b) => $a['avg'] <=> $b['avg']);

        return $result;
    }

    /**
     * Sum words for the rows that only PHP can count, in total and per period.
     *
     * A row qualifies when it is a text translation, or a document row with no
     * stored document_word_count — those are precisely the rows
     * wordsForRecord() falls through to str_word_count() for.
     *
     * @return array{total: int, this: int, prev: int}
     */
    private static function wordsNeedingPhpCount(
        int $userId,
        \DateTimeInterface $thisPeriodStart,
        \DateTimeInterface $prevPeriodStart,
        \DateTimeInterface $prevPeriodEnd
    ): array {
        $sums = ['total' => 0, 'this' => 0, 'prev' => 0];

        TranslationHistory::where('user_id', $userId)
            ->where(function ($q) {
                $q->where('translation_type', '<>', 'document')
                    ->orWhereNull('translation_type')
                    ->orWhereNull('document_word_count');
            })
            ->select(['id', 'created_at', 'source_text'])
            ->chunkById(self::WORD_SCAN_CHUNK, function ($rows) use (&$sums, $thisPeriodStart, $prevPeriodStart, $prevPeriodEnd) {
                foreach ($rows as $row) {
                    $words = str_word_count($row->source_text ?? '');
                    $sums['total'] += $words;

                    $created = $row->created_at;
                    if ($created === null) {
                        continue;
                    }
                    if ($created->gte($thisPeriodStart)) {
                        $sums['this'] += $words;
                    } elseif ($created->gte($prevPeriodStart) && $created->lte($prevPeriodEnd)) {
                        $sums['prev'] += $words;
                    }
                }
            });

        return $sums;
    }

    /**
     * Daily record counts over the trailing window, oldest first.
     *
     * Only created_at crosses the wire: bucketing by calendar day is not
     * portable across SQLite and PostgreSQL date functions, and the column is
     * small enough that reading the window is far cheaper than the history
     * rows the previous code loaded to build the same chart.
     *
     * @return array<int, array{date: string, count: int}>
     */
    private static function dailySeriesSince(int $userId, \DateTimeInterface $start, int $days = 30): array
    {
        $series = [];
        for ($i = 0; $i < $days; $i++) {
            $date = \Illuminate\Support\Carbon::instance($start)->addDays($i)->toDateString();
            $series[$date] = 0;
        }

        TranslationHistory::where('user_id', $userId)
            ->where('created_at', '>=', $start)
            ->select(['id', 'created_at'])
            ->chunkById(self::WORD_SCAN_CHUNK, function ($rows) use (&$series) {
                foreach ($rows as $row) {
                    if ($row->created_at === null) {
                        continue;
                    }
                    $date = $row->created_at->toDateString();
                    if (isset($series[$date])) {
                        $series[$date]++;
                    }
                }
            });

        $out = [];
        foreach ($series as $date => $count) {
            $out[] = ['date' => $date, 'count' => $count];
        }

        return $out;
    }

    /**
     * Aggregate counters for the profile page's "your translations" panel.
     *
     * Aggregated in the database over every row, for the same reason as
     * forUser(): the previous version read the newest 200 rows and reported
     * the truncated set as the user's lifetime totals.
     *
     * @return array{total: int, documents: int, thisMonth: int, languagePairs: int, avgQuality: float|null, statusBreakdown: array<string, int>}
     */
    public static function profileSummary(int $userId): array
    {
        $c = TranslationHistory::where('user_id', $userId)
            ->selectRaw('COUNT(*) AS total')
            ->selectRaw("SUM(CASE WHEN translation_type = 'document' THEN 1 ELSE 0 END) AS documents")
            ->selectRaw('SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS this_month', [now()->copy()->startOfMonth()])
            ->selectRaw("AVG(CASE WHEN quality_score >= 0 THEN quality_score END) AS avg_quality")
            ->selectRaw('SUM(CASE WHEN review_status = ? THEN 1 ELSE 0 END) AS pending', ['pending'])
            ->selectRaw('SUM(CASE WHEN review_status = ? THEN 1 ELSE 0 END) AS verified', ['verified'])
            ->selectRaw('SUM(CASE WHEN review_status = ? THEN 1 ELSE 0 END) AS edited', ['edited'])
            ->selectRaw('SUM(CASE WHEN review_status = ? THEN 1 ELSE 0 END) AS flagged', ['flagged'])
            // A pair counts when either language is set; a missing language is
            // reported as '?', matching the previous in-PHP mapping exactly.
            ->selectRaw(
                "COUNT(DISTINCT COALESCE(source_language, '?') || '|' || COALESCE(target_language, '?')) AS pairs"
            )
            ->where(function ($q) {
                $q->whereNotNull('source_language')->where('source_language', '<>', '')
                    ->orWhere(function ($q2) {
                        $q2->whereNotNull('target_language')->where('target_language', '<>', '');
                    });
            })
            ->first();

        return [
            'total'           => (int) $c->total,
            'documents'       => (int) $c->documents,
            'thisMonth'       => (int) $c->this_month,
            'languagePairs'   => (int) $c->pairs,
            'avgQuality'      => $c->avg_quality === null ? null : round((float) $c->avg_quality, 1),
            'statusBreakdown' => [
                'pending'  => (int) $c->pending,
                'verified' => (int) $c->verified,
                'edited'   => (int) $c->edited,
                'flagged'  => (int) $c->flagged,
            ],
        ];
    }

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