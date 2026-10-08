<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationJob;
use App\Services\DispatchOutcomeClassifier;
use Illuminate\Contracts\View\View;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
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

        // Enrich each failed queue job with the recoverability of the matching
        // durable translation_jobs row (keyed by the shared uuid). This is a
        // pure identifier join — failed_jobs.payload is never unserialized.
        $recoverableByUuid = $failed->pluck('uuid')
            ->filter()
            ->map(fn (string $uuid): string => (string) $uuid)
            ->all();

        $recoverableMap = [];
        if ($recoverableByUuid !== []) {
            $recoverableMap = TranslationJob::whereIn('uuid', $recoverableByUuid)
                ->where('status', TranslationJob::STATUS_FAILED)
                ->where('recoverable', true)
                ->pluck('recoverable', 'uuid')
                ->map(fn () => true)
                ->all();
        }

        $failed = $failed->map(function ($row) use ($recoverableMap) {
            $row->recoverable = isset($recoverableMap[$row->uuid]);
            return $row;
        });

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
     * POST /admin/jobs/retry/{failedJobId} — replay a failed document job.
     *
     * The original scratch upload is gone by the time a job fails, so retrying
     * the serialized payload via queue:retry would only reproduce the same
     * "input file not found" failure. Instead we reconstruct the worker-local
     * input from the durable original at the start of the replayed job and
     * never unserialize failed_jobs.payload: the failed row is matched to its
     * translation_jobs state machine through the shared uuid only.
     */
    public function retry(Request $request, string $failedJobId): RedirectResponse
    {
        if (!ctype_digit($failedJobId)) {
            abort(404, 'Invalid job id.');
        }

        $failed = DB::table('failed_jobs')->where('id', (int) $failedJobId)->first();
        if ($failed === null) {
            abort(404, 'Failed job not found.');
        }

        $uuid = (string) ($failed->uuid ?? '');
        $state = $uuid !== ''
            ? TranslationJob::where('uuid', $uuid)->first()
            : null;

        if ($state === null || !$state->isTerminalFailedRecoverable()) {
            Log::warning('Admin retry refused: failed job has no recoverable durable original', [
                'failed_job_id' => (int) $failedJobId,
                'uuid'          => $uuid,
                'admin_id'      => $request->user()?->id,
            ]);

            return redirect()
                ->route('admin.jobs.index')
                ->with('status', 'queue-job-not-recoverable');
        }

        $original = $state?->original_storage_path ?? null;
        $backend = $state?->original_storage_backend ?? null;
        if (blank($original) || blank($backend)) {
            abort(500, 'Failed job matched but durable original metadata is missing.');
        }

        $job = new TranslateDocumentJob(
            $state->original_name ?? 'document',
            $state->original_ext ?? '.bin',
            (int) ($state->file_size ?? 0),
            $state->source_lang ?? '',
            $state->target_lang ?? '',
            $state->pdf_column_mode ?? 'auto',
            '', // worker-local scratch from the failed attempt is gone; reconstructed in-handle
            (int) $state->user_id,
            $original,
            $state->mode ?? 'balanced',
            $state->parent_document_id,
            $backend,
            (int) $state->id,
            $uuid,
        );

        $priorStatus = (string) $state->status;
        $failedJobRowId = (int) $failedJobId;

        try {
            // Same acceptance boundary as intake: the failed -> queued write and
            // the queue insert share ONE commit, so a rollback leaves the job
            // recoverable and no receivable queue row behind.
            DB::transaction(function () use ($state, $job, $failedJobRowId) {
                $queued = $state->markQueued(recovered: true);
                if (!$queued) {
                    throw new \RuntimeException('Job could not be moved back to queued; it may already be active again.');
                }

                dispatch($job);

                // A successful replay supersedes the historical failure entry so
                // the admin retry control disappears and statuses stay coherent.
                // Inside the transaction: a rollback restores the failure record
                // along with the failed status it describes.
                DB::table('failed_jobs')->where('id', $failedJobRowId)->delete();
            });

            Log::info('Admin replayed a failed translation job from its durable original', [
                'failed_job_id' => $failedJobRowId,
                'uuid'          => $uuid,
                'translation_job_id' => (int) $state->id,
                'admin_id'      => $request->user()?->id,
            ]);
        } catch (\Throwable $e) {
            // The prior failure record is the only recovery handle for this
            // job, so it is never deleted on a failed replay — whether the new
            // dispatch was rejected or is merely unresolved.
            $authoritative = null;
            try {
                $authoritative = TranslationJob::find($state->id);
            } catch (\Throwable $readBackFailure) {
                $authoritative = null;
            }

            $outcome = $this->dispatchOutcome->classify(
                $authoritative,
                $uuid,
                $priorStatus,
                $failedJobRowId,
            );

            Log::error('Admin failed to retry queue job', [
                'failed_job_id' => $failedJobRowId,
                'uuid'          => $uuid,
                'exception'     => $e->getMessage(),
                'outcome'       => $outcome->status,
                'reason'        => $outcome->reason,
            ]);

            return redirect()
                ->route('admin.jobs.index')
                ->with('status', $outcome->isUnknown() ? 'queue-job-retry-unconfirmed' : 'queue-job-retry-failed');
        }

        return redirect()
            ->route('admin.jobs.index')
            ->with('status', 'queue-job-retried');
    }
}