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
     * Show the dashboard with real stats and recent records for the current session.
     */
    public function index()
    {
        $error         = false;
        $stats         = ['totalDocs' => 0, 'translationsThisMonth' => 0, 'wordsTranslated' => 0];
        $recentRecords = [];

        try {
            $records       = $this->history->getHistory(Auth::id());
            $stats         = $this->computeStats($records);
            // Records are already ordered newest-first by HistoryService; take the first 5.
            $recentRecords = array_slice($records, 0, 5);
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
     * @return array{totalDocs: int, translationsThisMonth: int, wordsTranslated: int}
     */
    public function computeStats(array $records): array
    {
        return TranslationStatsService::compute($records);
    }
}
