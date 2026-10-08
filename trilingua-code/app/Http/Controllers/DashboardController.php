<?php

namespace App\Http\Controllers;

use App\Models\TranslationHistory;
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
            // Aggregated in the database over every row the user owns. This
            // used to run the statistics over the newest 200 history rows,
            // so every total silently stopped growing past 200 translations.
            $stats = TranslationStatsService::forUser((int) Auth::id());

            $recentRecords = TranslationHistory::where('user_id', Auth::id())
                ->orderByDesc('created_at')
                ->orderByDesc('id')
                ->limit(6)
                ->get()
                ->toArray();
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
}
