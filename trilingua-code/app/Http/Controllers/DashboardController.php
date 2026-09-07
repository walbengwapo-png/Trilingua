<?php

namespace App\Http\Controllers;

use App\Services\HistoryService;
use App\Services\TranslationStatsService;
use Illuminate\Support\Facades\Auth;
use Throwable;

class DashboardController extends Controller
{
    public function __construct(private HistoryService $history) {}

    /**
     * Show the dashboard with real, trended stats and recent records for the
     * current session user.
     */
    public function index()
    {
        $error         = false;
        $stats         = [];
        $recentRecords = [];

        try {
            $records = $this->history->getHistory(Auth::id());

            $stats = [
                'core'        => TranslationStatsService::compute($records),
                'totals'      => $this->totals($records),
                'deltas'      => $this->deltas($records),
                'sparkline'   => TranslationStatsService::dailySeries($records, 30),
                'pairMix'     => TranslationStatsService::languagePairMix($records),
                'qualityByPair' => TranslationStatsService::qualityByPair($records),
                'avgQuality'  => TranslationStatsService::averageQuality($records),
            ];

            $recentRecords = array_slice($records, 0, 6);
        } catch (Throwable) {
            $error = true;
        }

        return view('dashboard', compact('stats', 'recentRecords', 'error'));
    }

    /**
     * Compute dashboard stat values from an array of translation_history records.
     *
     * Delegates to TranslationStatsService so the admin user-detail page can
     * reuse the same logic.
     *
     * @param  array<int, array>  $records  Rows returned by HistoryService::getHistory().
     * @return array{totalDocs: int, totalTexts: int, translationsThisMonth: int, wordsTranslated: int, topLangPair: string}
     */
    public function computeStats(array $records): array
    {
        return TranslationStatsService::compute($records);
    }

    /**
     * Overall totals across the last 200 records.
     */
    private function totals(array $records): array
    {
        return [
            'total'    => count($records),
            'documents' => $records === [] ? 0 : count(array_filter($records, fn ($r) => ($r['translation_type'] ?? '') === 'document')),
            'texts'    => $records === [] ? 0 : count(array_filter($records, fn ($r) => ($r['translation_type'] ?? '') === 'text')),
            'words'    => array_reduce($records, fn ($carry, $r) => $carry + TranslationStatsService::wordsForRecord($r), 0),
            'bookmarked' => $records === [] ? 0 : count(array_filter($records, fn ($r) => !empty($r['is_bookmarked']))),
        ];
    }

    /**
     * Period-over-period deltas for the KPI trend chips.
     *
     * Compares the trailing 30 days against the 30 days before that.
     */
    private function deltas(array $records): array
    {
        $now = now();
        $thisPeriodStart = $now->copy()->subDays(30)->startOfDay();
        $prevPeriodStart = $now->copy()->subDays(60)->startOfDay();
        $prevPeriodEnd   = $now->copy()->subDays(30)->endOfDay();

        $thisCount = TranslationStatsService::countInRange($records, $thisPeriodStart, $now);
        $prevCount = TranslationStatsService::countInRange($records, $prevPeriodStart, $prevPeriodEnd);

        $thisWords = 0;
        $prevWords = 0;
        foreach ($records as $r) {
            $created = $r['created_at'] ?? null;
            if (!$created) {
                continue;
            }
            try {
                $ts = \Carbon\Carbon::parse($created);
            } catch (Throwable) {
                continue;
            }
            $words = TranslationStatsService::wordsForRecord($r);
            if ($ts >= $thisPeriodStart) {
                $thisWords += $words;
            } elseif ($ts >= $prevPeriodStart && $ts <= $prevPeriodEnd) {
                $prevWords += $words;
            }
        }

        return [
            'translationsDelta' => TranslationStatsService::deltaPercent($thisCount, $prevCount),
            'wordsDelta'        => TranslationStatsService::deltaPercent($thisWords, $prevWords),
        ];
    }
}