<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\TranslationJob;
use Illuminate\Contracts\View\View;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class JobController extends Controller
{
    /**
     * GET /admin/jobs — inspect translation jobs and failed queue jobs.
     */
    public function index(Request $request): View
    {
        $jobs = TranslationJob::with('user')
            ->orderByDesc('id')
            ->when($request->string('status'), fn ($q, $status) => $q->where('status', $status))
            ->when($request->string('q'), function ($q, $search) {
                $q->where(function ($inner) use ($search) {
                    $inner->where('original_name', 'like', "%{$search}%")
                        ->orWhere('uuid', 'like', "%{$search}%");
                });
            })
            ->paginate(50)
            ->withQueryString();

        $failed = DB::table('failed_jobs')
            ->orderByDesc('failed_at')
            ->limit(100)
            ->get();

        $counts = TranslationJob::selectRaw('status, count(*) as total')
            ->groupBy('status')
            ->pluck('total', 'status');

        return view('admin.jobs', [
            'jobs'   => $jobs,
            'failed' => $failed,
            'counts' => $counts,
            'filters' => [
                'status' => (string) $request->string('status'),
                'q'      => (string) $request->string('q'),
            ],
            'error' => false,
        ]);
    }

    /**
     * POST /admin/jobs/retry/{failedJobId} — replay a failed queue job.
     */
    public function retry(Request $request, string $failedJobId): RedirectResponse
    {
        if (!ctype_digit($failedJobId)) {
            abort(404, 'Invalid job id.');
        }

        $exists = DB::table('failed_jobs')->where('id', (int) $failedJobId)->exists();
        if (!$exists) {
            abort(404, 'Failed job not found.');
        }

        try {
            Artisan::call('queue:retry', ['id' => (string) (int) $failedJobId]);
            Log::info('Admin retried a failed queue job', [
                'failed_job_id' => (int) $failedJobId,
                'admin_id' => $request->user()?->id,
            ]);
        } catch (\Throwable $e) {
            Log::error('Admin failed to retry queue job', [
                'failed_job_id' => (int) $failedJobId,
                'exception' => $e->getMessage(),
            ]);
        }

        return redirect()->route('admin.jobs.index')->with('status', 'queue-job-retried');
    }
}