<?php

namespace App\Services;

use App\Models\TranslationJob;
use Illuminate\Support\Facades\DB;

/**
 * The outcome of an intake dispatch attempt.
 *
 * The distinction between REJECTED and UNKNOWN is the whole point. A dispatch
 * that throws may or may not have reached the queue: if the connection dies
 * during COMMIT, neither the queue insert nor the state write is observable.
 * Claiming "accepted" there would promise work that may never run; claiming
 * "rejected" there would refund quota and delete the input of a job a worker
 * has already picked up. UNKNOWN is the honest third answer, and it carries the
 * stable job reference so the caller can check back.
 */
final class DispatchOutcome
{
    /** The work is durably queued, or a worker already has it. */
    public const ACCEPTED = 'accepted';

    /** The work provably never entered the queue. Safe to compensate. */
    public const REJECTED = 'rejected';

    /** The enqueue outcome could not be determined. Claim nothing, compensate nothing. */
    public const UNKNOWN = 'unknown';

    public function __construct(
        public readonly string $status,
        public readonly string $reason,
        public readonly bool $safeToCompensate,
    ) {
    }

    public function isAccepted(): bool
    {
        return $this->status === self::ACCEPTED;
    }

    public function isRejected(): bool
    {
        return $this->status === self::REJECTED;
    }

    public function isUnknown(): bool
    {
        return $this->status === self::UNKNOWN;
    }
}
