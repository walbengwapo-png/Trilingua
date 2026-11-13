<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationJob;
use App\Services\DispatchOutcomeClassifier;
use App\Support\TranslationJobFilters;
use App\Support\TranslationQueueMetadata;
use Illuminate\Contracts\View\View;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class JobController extends Controller
{
    public function __construct(
        private DispatchOutcomeClassifier $dispatchOutcome,
    ) {}

    /**
     * GET /admin/jobs — inspect translation jobs and failed queue jobs.
     */
    public function index(Request $request): View
    {
        $filters = TranslationJobFilters::validated($request);
        $jobs = TranslationJobFilters::apply(TranslationJob::with('user')->orderByDesc('id'), $filters)
            ->paginate(50)
            ->withQueryString();

        $failed = DB::table('failed_jobs')
            ->orderByDesc('failed_at')
            ->limit(100)
            ->get();

        $failed = $failed->map(function ($row) {
            $state = TranslationQueueMetadata::resolve($row->payload);
            $row->translation_job_id = $state?->id;
            $row->translation_status = $state?->status;
            $row->input_available = $state && filled($state->original_storage_path) && filled($state->original_storage_backend);
            $row->recoverable = $state?->isTerminalFailedRecoverable() ?? false;
            return $row;
        });

        $counts = TranslationJob::selectRaw('status, count(*) as total')
            ->groupBy('status')
            ->pluck('total', 'status');

        return view('admin.jobs', [
            'jobs'   => $jobs,
            'failed' => $failed,
            'counts' => $counts,
            'filters' => $filters,
            'error' => false,
        ]);
    }

    /** Compatibility entry: historical queue IDs resolve as inert data. */
    public function retry(Request $request, string $failedJobId): RedirectResponse
    {
        abort_unless(ctype_digit($failedJobId), 404);
        $failed = DB::table('failed_jobs')->where('id', (int) $failedJobId)->first();
        abort_unless($failed, 404);
        $state = TranslationQueueMetadata::resolve($failed->payload);
        if (!$state) {
            return redirect()->route('admin.jobs.index')->with('status', 'queue-job-not-recoverable');
        }
        return $this->retryState($request, $state, (int) $failedJobId);
    }

    public function retryTranslation(Request $request, TranslationJob $translationJob): RedirectResponse
    {
        return $this->retryState($request, $translationJob);
    }

    private function retryState(Request $request, TranslationJob $state, ?int $failedJobId = null): RedirectResponse
    {
        $request->validate(['provider_request_budget' => ['nullable', 'integer', 'min:1', 'max:8']]);
        $providerBudget = $request->filled('provider_request_budget') ? (int) $request->input('provider_request_budget') : null;
        if (!$state->isTerminalFailedRecoverable()) {
            return redirect()->route('admin.jobs.index')->with('status',
                $state->isActive() ? 'queue-job-already-active' : 'queue-job-not-recoverable');
        }
        $ocrMode = $state->ocr_mode;
        if (!$ocrMode) {
            // Legacy options remain in historical payloads. Read, validate, never execute them.
            $modes = [];
            foreach (DB::table('failed_jobs')->where('payload', 'like', '%'.$state->uuid.'%')->get(['payload']) as $row) {
                $metadata = TranslationQueueMetadata::extract($row->payload);
                if ($metadata && TranslationQueueMetadata::matches($metadata, $state->getAttributes())) {
                    $modes[] = $metadata['ocr_mode'];
                }
            }
            $modes = array_unique($modes);
            if (count($modes) !== 1) {
                return redirect()->route('admin.jobs.index')->with('status', 'queue-job-options-unavailable');
            }
            $ocrMode = reset($modes);
        }
        $uuid = $state->uuid;
        $expectedAttempt = (int) $state->attempts + 1;
        $dispatchAttempted = false;
        try {
            $this->dispatchOutcome->assertTransactionalQueue();
            DB::transaction(function () use ($state, $uuid, $ocrMode, $expectedAttempt, $providerBudget, &$dispatchAttempted): void {
                if (!$state->markQueued(recovered: true)) {
                    throw new \RuntimeException('Retry already claimed or generation changed.');
                }
                app(\App\Services\TranslationAdmission::class)->bindDocument($state);
                $state->ocr_mode = $ocrMode;
                $state->save();
                $job = new TranslateDocumentJob(
                    $state->original_name, $state->original_ext, (int) $state->file_size,
                    $state->source_lang, $state->target_lang, $state->pdf_column_mode, '', (int) $state->user_id,
                    $state->original_storage_path, $state->mode, $state->parent_document_id,
                    $state->original_storage_backend, (int) $state->id, $uuid, $ocrMode, $expectedAttempt, $providerBudget,
                );
                $dispatchAttempted = true;
                dispatch($job);
                // Historical failed_jobs evidence is deliberately retained.
            });
        } catch (\Throwable $error) {
            try { $authoritative = TranslationJob::find($state->id); }
            catch (\Throwable) { $authoritative = null; }
            $outcome = $this->dispatchOutcome->classify($authoritative, $uuid, TranslationJob::STATUS_FAILED,
                $failedJobId, $dispatchAttempted, $expectedAttempt);
            Log::warning('Translation retry dispatch outcome', ['translation_job_id' => $state->id,
                'expected_attempt' => $expectedAttempt, 'outcome' => $outcome->status]);
            return redirect()->route('admin.jobs.index')->with('status', $outcome->isAccepted() ? 'queue-job-retried'
                : ($outcome->isUnknown() ? 'queue-job-retry-unconfirmed' : 'queue-job-retry-failed'));
        }
        try { Cache::forget('translation_job_'.$uuid); }
        catch (\Throwable) { Log::warning('Retry cache invalidation unavailable', ['translation_job_id' => $state->id]); }
        return redirect()->route('admin.jobs.index')->with('status', 'queue-job-retried');
    }
}
