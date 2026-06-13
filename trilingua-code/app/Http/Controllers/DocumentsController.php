<?php

namespace App\Http\Controllers;

use App\Services\HistoryService;
use Illuminate\Contracts\View\View;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;

class DocumentsController extends Controller
{
    public function __construct(private HistoryService $history) {}

    /**
     * GET /documents — render the My Documents page.
     *
     * Shows original documents with their translations grouped together.
     * Also includes standalone translations (those without a parent) for backward compatibility.
     */
    public function index(Request $request): View
    {
        try {
            // Get originals with their translations
            $originalsWithTranslations = $this->history->getOriginalsWithTranslations(Auth::id());

            // Also get all document records for backward compatibility (includes translations without parent)
            $all = $this->history->getHistory(Auth::id());
            $documents = array_values(array_filter(
                $all,
                fn($r) => ($r['translation_type'] ?? 'document') === 'document'
            ));

            return view('my-documents', [
                'documents' => $documents,
                'originals' => $originalsWithTranslations,
                'error'     => false,
            ]);
        } catch (\Throwable $e) {
            Log::error('DocumentsController::index failed', [
                'user_id'   => Auth::id(),
                'exception'  => $e->getMessage(),
            ]);

            return view('my-documents', [
                'documents' => [],
                'originals' => [],
                'error'     => true,
            ]);
        }
    }
}