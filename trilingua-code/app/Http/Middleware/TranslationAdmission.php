<?php

namespace App\Http\Middleware;

use App\Models\TranslationJob;
use App\Services\TranslationAdmission as Admission;
use App\Support\TranslationQueueMetadata;
use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

final class TranslationAdmission
{
    public function handle(Request $request, Closure $next)
    {
        $admission = app(Admission::class);
        if (!$admission->enabled()) { return $next($request); }
        $userId = (int) $request->user()->id;
        if ($request->routeIs('admin.translation-jobs.retry')) {
            $job = $request->route('translationJob');
            $job = $job instanceof TranslationJob ? $job : TranslationJob::findOrFail($job);
            $userId = (int) $job->user_id;
        } elseif ($request->routeIs('admin.jobs.retry')) {
            $failed = DB::table('failed_jobs')->where('id', $request->route('failedJobId'))->first();
            $job = $failed ? TranslationQueueMetadata::resolve($failed->payload) : null;
            if (!$job) { return $next($request); }
            $userId = (int) $job->user_id;
        }
        $lease = $admission->acquire($userId);
        if ($lease['owner'] === null) {
            if ($request->routeIs('admin.*')) {
                return redirect()->route('admin.jobs.index')->with('status', 'queue-user-already-active');
            }
            return response()->json(['error' => $lease['status'] === 'recovery_required'
                    ? 'Your previous translation has an uncertain outcome. An operator must reconcile it before you can translate again.'
                    : 'You already have a translation queued or processing. Wait for it to finish.',
                'job_id' => $lease['job_id'], 'status' => $lease['status']], 409);
        }
        $request->attributes->set('translation_admission_owner', $lease['owner']);
        try {
            return $next($request);
        } finally {
            try {
                $admission->finishRequest($userId, $lease['owner'], $request->attributes->get('translation_text_terminal') === true);
            } catch (\Throwable $error) {
                // Fail closed: a lost reservation is worse than requiring operator reconciliation.
                Log::warning('Translation admission release unavailable', ['user_id' => $userId, 'exception_type' => $error::class]);
            }
        }
    }
}
