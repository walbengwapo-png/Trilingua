<?php

namespace App\Http\Controllers;

use App\Services\HistoryService;
use Illuminate\Contracts\View\View;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;

class BookmarksController extends Controller
{
    public function __construct(private HistoryService $history) {}

    /**
     * GET /bookmarks — render the Bookmarked page.
     *
     * Shows every record the current user bookmarked (persisted via the
     * is_bookmarked flag), newest first.
     */
    public function index(): View
    {
        try {
            $records = $this->history->getBookmarked(Auth::id());

            return view('bookmarks', [
                'records' => $records,
                'error'   => false,
            ]);
        } catch (\Throwable $e) {
            Log::error('BookmarksController::index failed to load bookmarks', [
                'user_id'   => Auth::id(),
                'exception' => $e->getMessage(),
            ]);

            return view('bookmarks', [
                'records' => [],
                'error'   => true,
            ]);
        }
    }
}
