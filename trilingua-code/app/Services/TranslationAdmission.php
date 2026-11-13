<?php

namespace App\Services;

use App\Models\TranslationJob;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

/** Owner-fenced per-user admission; expiry is evidence for review, never permission to replay. */
final class TranslationAdmission
{
    public function enabled(): bool { return (bool) config('translation.admission_enabled', false); }

    /** Null owner means busy. References are returned only to the caller owning this user scope. */
    public function acquire(int $userId): array
    {
        return DB::transaction(function () use ($userId): array {
            DB::table('translation_admissions')->insertOrIgnore(['user_id' => $userId]);
            $row = DB::table('translation_admissions')->where('user_id', $userId)->lockForUpdate()->first();
            if ($row->owner !== null && $row->translation_job_id !== null) {
                $this->finishDocument((int) $row->translation_job_id, (int) $row->expected_attempt);
                $row = DB::table('translation_admissions')->where('user_id', $userId)->first();
            }
            $active = TranslationJob::where('user_id', $userId)->whereIn('status', TranslationJob::ACTIVE_STATUSES)->first();
            if ($row->owner !== null || $active) {
                $job = $active ?: ($row->translation_job_id ? TranslationJob::find($row->translation_job_id) : null);
                return ['owner' => null, 'job_id' => $job?->uuid,
                    'status' => $row->phase === 'uncertain' ? 'recovery_required' : ($active?->publicStatus() ?? 'processing')];
            }
            $owner = (string) Str::uuid();
            DB::table('translation_admissions')->where('user_id', $userId)->update([
                'owner' => $owner, 'phase' => 'intake', 'translation_job_id' => null, 'expected_attempt' => null,
                'heartbeat_at' => now(), 'deadline_at' => now()->addSeconds((int) config('timeouts.job', 1300)),
            ]);
            return ['owner' => $owner];
        });
    }

    public function bindDocument(TranslationJob $job): void
    {
        if (!$this->enabled()) { return; }
        $owner = request()->attributes->get('translation_admission_owner');
        if (!$owner || DB::transactionLevel() === 0) {
            throw new \RuntimeException('Document acceptance requires transactional user admission.');
        }
        $changed = DB::table('translation_admissions')->where('user_id', $job->user_id)->where('owner', $owner)
            ->where('phase', 'intake')->update(['phase' => 'document', 'translation_job_id' => $job->id,
                'expected_attempt' => (int) $job->attempts + 1, 'heartbeat_at' => now()]);
        if ($changed !== 1) { throw new \RuntimeException('User admission owner changed.'); }
    }

    public function beginText(): void
    {
        if (!$this->enabled()) { return; }
        $changed = DB::table('translation_admissions')->where('user_id', request()->user()->id)
            ->where('owner', request()->attributes->get('translation_admission_owner'))->where('phase', 'intake')
            ->update(['phase' => 'text', 'heartbeat_at' => now()]);
        if ($changed !== 1) { throw new \RuntimeException('Text admission owner changed.'); }
    }

    public function finishRequest(int $userId, string $owner, bool $textTerminal): void
    {
        $query = DB::table('translation_admissions')->where('user_id', $userId)->where('owner', $owner);
        if ($textTerminal) {
            (clone $query)->whereIn('phase', ['intake', 'text'])->update($this->idle());
        } else {
            (clone $query)->where('phase', 'intake')->update($this->idle());
            (clone $query)->where('phase', 'text')->update(['phase' => 'uncertain']);
        }
    }

    public function finishDocument(int $jobId, int $attempt): void
    {
        if (!$this->enabled()) { return; }
        DB::transaction(function () use ($jobId, $attempt): void {
            $query = DB::table('translation_admissions')->where('translation_job_id', $jobId)->where('expected_attempt', $attempt);
            $lease = (clone $query)->lockForUpdate()->first();
            if (!$lease || !$lease->owner) { return; }
            // Lock admission BEFORE reading terminal state. A never-started retry
            // can reuse the next attempt number, but must have a different owner.
            $query->where('owner', $lease->owner);
            $job = TranslationJob::find($jobId);
            if (!$job || !$job->isTerminal()) { return; }
            $claimed = (int) $job->attempts === $attempt;
            $neverClaimed = (int) $job->attempts + 1 === $attempt
                && in_array($job->status, [TranslationJob::STATUS_FAILED, TranslationJob::STATUS_CANCELLED], true);
            if (!$claimed && !$neverClaimed) { return; }
            if ($job->status !== TranslationJob::STATUS_COMPLETED && $job->engine_job_uuid) {
                $engine = DB::table('python_document_jobs')->where('id', $job->engine_job_uuid)->first();
                if (!$engine || !in_array($engine->status, ['failed', 'completed'], true)
                    || ((int) $engine->error_status === 408 && (!$engine->lease_until || now()->lt(\Illuminate\Support\Carbon::parse($engine->lease_until)->addSeconds(60))))) {
                    $query->update(['phase' => 'uncertain']);
                    return;
                }
            }
            $query->update($this->idle());
        });
    }

    private function idle(): array
    {
        return ['owner' => null, 'phase' => 'idle', 'translation_job_id' => null,
            'expected_attempt' => null, 'heartbeat_at' => null, 'deadline_at' => null];
    }
}
