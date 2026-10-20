<?php

namespace App\Services;

use App\Models\TranslationJob;
use Illuminate\Support\Facades\DB;

/**
 * Decides what actually happened to an intake dispatch.
 *
 * An ABSENT `jobs` row proves nothing on its own. There is no completed_jobs
 * table, so a worker that finished successfully leaves no queue trace at all â€”
 * absence is equally consistent with "never enqueued", "reserved, run, and
 * removed", and "enqueued then failed". The durable translation_jobs row is
 * therefore the primary signal, and the queue tables only disambiguate.
 */
class DispatchOutcomeClassifier
{
    /**
     * Classify the outcome of an intake dispatch.
     *
     * Note on why a successful read-back is decisive: once the connection has
     * recovered, a read observes everything previously committed on that
     * database. So "read-back succeeded and shows no evidence" is definitive
     * absence, not an unknown â€” including the case where the connection died
     * during COMMIT. The genuinely unknown outcome is the one where read-back
     * ITSELF fails, because then we cannot see either the commit or its
     * absence. That asymmetry is the entire reason UNKNOWN is its own value
     * rather than being folded into REJECTED.
     *
     * @param  TranslationJob|null  $row        The authoritative state row.
     * @param  string  $uuid                The stable job reference.
     * @param  string|null  $statusBeforeDispatch  State the row held before the
     *                                             dispatch was attempted, so a
     *                                             rolled-back transition can be
     *                                             recognised.
     * @param  int|null  $excludeFailedJobId  A failed_jobs row that already
     *                                         existed before this dispatch. It
     *                                         must not be read as evidence that
     *                                         *this* dispatch was accepted —
     *                                         admin Retry legitimately operates
     *                                         while the prior failure record is
     *                                         still present.
     * @param  bool  $dispatchAttempted  Whether the enqueue call was actually
     *                                  reached. This is stated explicitly rather
     *                                  than inferred from an empty uuid, because
     *                                  the two cases have opposite meanings: a
     *                                  failure before the enqueue call provably
     *                                  never touched the queue, while a failure
     *                                  after it with no reference to classify is
     *                                  genuinely unresolvable.
     */
    public function classify(
        ?TranslationJob $row,
        string $uuid,
        ?string $statusBeforeDispatch = null,
        ?int $excludeFailedJobId = null,
        bool $dispatchAttempted = true,
    ): DispatchOutcome {
        if (! $dispatchAttempted) {
            // The enqueue call was never reached, so nothing can be in the
            // queue for this reference — no matter what the state row says. The
            // failure was in persistence, not dispatch.
            return new DispatchOutcome(
                DispatchOutcome::REJECTED,
                'The failure occurred before the enqueue call, so no job entered the queue.',
                true,
            );
        }

        if ($uuid === '') {
            return new DispatchOutcome(
                DispatchOutcome::UNKNOWN,
                'The enqueue was attempted but no job reference was established, so its outcome cannot be determined.',
                false,
            );
        }

        // A worker that received the work owns the outcome from here on. This
        // holds whether or not a queue row still exists â€” there is no
        // completed_jobs table, so a finished job leaves no queue trace at all.
        if ($row !== null && in_array($row->status, [TranslationJob::STATUS_PROCESSING, TranslationJob::STATUS_COMPLETED], true)) {
            return new DispatchOutcome(
                DispatchOutcome::ACCEPTED,
                'A worker already has this job ('.$row->status.').',
                false,
            );
        }

        try {
            $queueRow = $this->queueRow($uuid);
            $failedJob = $this->hasFailedJobEvidence($uuid, $excludeFailedJobId);
        } catch (\Throwable $e) {
            // Read-back itself failed. We cannot distinguish committed from
            // absent, so we must not compensate.
            return new DispatchOutcome(
                DispatchOutcome::UNKNOWN,
                'The enqueue outcome could not be read back: '.$e->getMessage(),
                false,
            );
        }

        if ($queueRow !== null) {
            $reserved = $queueRow->reserved_at !== null;

            return new DispatchOutcome(
                DispatchOutcome::ACCEPTED,
                $reserved
                    ? 'A worker holds a reservation for this job'
                        .($this->isReservationFresh((int) $queueRow->reserved_at) ? '' : ' (older than retry_after)').'.'
                    : 'The job is enqueued and waiting for a worker.',
                false,
            );
        }

        if ($failedJob) {
            // A worker received it and exhausted its retries. This is NOT an
            // intake failure: refunding quota or deleting the input here would
            // destroy the recovery handle a retry needs.
            return new DispatchOutcome(
                DispatchOutcome::ACCEPTED,
                'A worker received this job and it is recorded in failed_jobs; the failure path owns the outcome.',
                false,
            );
        }

        $status = $row?->status;

        if ($status === null) {
            return new DispatchOutcome(
                DispatchOutcome::REJECTED,
                'The state transaction rolled back: no row, no queue entry, and no worker evidence.',
                true,
            );
        }

        if ($status === TranslationJob::STATUS_CREATED) {
            return new DispatchOutcome(
                DispatchOutcome::REJECTED,
                'The queued transition rolled back; the row is still created and nothing was enqueued.',
                true,
            );
        }

        if ($status === TranslationJob::STATUS_QUEUED) {
            return new DispatchOutcome(
                DispatchOutcome::REJECTED,
                'The row is queued but no queue entry or worker evidence exists, so no worker can receive it.',
                true,
            );
        }

        if ($statusBeforeDispatch !== null && $status === $statusBeforeDispatch) {
            // Admin Retry on a failed job: the failed -> queued write rolled
            // back, so the row truthfully retains its prior terminal state.
            return new DispatchOutcome(
                DispatchOutcome::REJECTED,
                'The transition to queued rolled back; the row retains its prior state ('.$status.').',
                true,
            );
        }

        // Some other terminal state written by a different actor. Not our
        // failure, and not ours to overwrite.
        return new DispatchOutcome(
            DispatchOutcome::ACCEPTED,
            'The row is in a state owned by another actor ('.$status.').',
            false,
        );
    }

    /**
     * The raw queue row for this job, or null when absent.
     *
     * The payload match is a plain string search over the serialized wrapper â€”
     * the payload is never unserialized here, matching the same discipline the
     * admin job index uses for failed_jobs.
     */
    public function queueRow(string $uuid): ?object
    {
        return DB::table('jobs')
            ->where('payload', 'like', '%'.$uuid.'%')
            ->first(['id', 'reserved_at', 'available_at', 'attempts']);
    }

    public function hasFailedJobEvidence(string $uuid, ?int $excludeFailedJobId = null): bool
    {
        if ($uuid === '') {
            return false;
        }

        $query = DB::table('failed_jobs')
            ->where(function ($q) use ($uuid) {
                $q->where('uuid', $uuid)
                    ->orWhere('payload', 'like', '%'.$uuid.'%');
            });

        if ($excludeFailedJobId !== null) {
            $query->where('id', '!=', $excludeFailedJobId);
        }

        return $query->exists();
    }

    /**
     * Does a worker still hold this job within the queue's retry_after window?
     * A stale reservation is not live evidence â€” the job will be retried.
     */
    public function hasLiveWorkerEvidence(string $uuid, ?int $retryAfter = null): bool
    {
        $row = $this->queueRow($uuid);

        if ($row === null || $row->reserved_at === null) {
            return false;
        }

        return $this->isReservationFresh((int) $row->reserved_at, $retryAfter);
    }

    private function isReservationFresh(int $reservedAt, ?int $retryAfter = null): bool
    {
        $retryAfter ??= (int) (config('queue.connections.database.retry_after') ?? 1800);

        return (time() - $reservedAt) < $retryAfter;
    }
}
