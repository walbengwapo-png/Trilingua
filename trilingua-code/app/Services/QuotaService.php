<?php

namespace App\Services;

use App\Models\TranslationQuota;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Daily per-user upload quota, charged at acceptance.
 *
 * The reservation is a single conditional UPDATE whose WHERE clauses are
 * re-evaluated under the DB row lock, so concurrent requests serialize at the
 * boundary line: once the ledger row is at the cap, exactly one winner is
 * admitted and every later contender is refused — no shared read-then-write
 * gap. Only the ledger row for the current day is touched, so a new calendar
 * day starts with a fresh counter with no cleanup step.
 */
class QuotaService
{
    /**
     * @param string|null $forDay Y-m-d day to charge. Callers capture the day
     *        BEFORE a possible midnight crossing so a refund always returns to
     *        the exact ledger that was charged.
     */
    public function reserve(int $userId, int $bytes, ?string $forDay = null): bool
    {
        $maxFiles = (int) config('translation.upload.max_daily_files', 25);
        $maxBytes = (int) config('translation.upload.max_daily_bytes', 262144000);
        $quotaDay = $forDay ?? now()->toDateString();

        $row = TranslationQuota::firstOrCreate(
            ['user_id' => $userId, 'quota_day' => $quotaDay],
            ['files' => 0, 'bytes' => 0],
        );

        $effect = TranslationQuota::whereKey($row->id)
            ->where('files', '<', $maxFiles)
            ->where('bytes', '<=', $maxBytes - $bytes)
            ->update([
                'files' => DB::raw('files + 1'),
                'bytes' => DB::raw('bytes + ' . (int) $bytes),
            ]);

        if ($effect === 1) {
            return true;
        }

        Log::warning('Document upload quota exceeded (atomic reservation refused)', [
            'user_id' => $userId,
            'file_size' => $bytes,
            'max_files' => $maxFiles,
            'max_bytes' => $maxBytes,
        ]);

        return false;
    }

    /**
     * Give back a reservation whose acceptance was voided (e.g. the loser of
     * an exact-duplicate race whose job row is deleted, or an acceptance that
     * failed before any accepted job existed).
     *
     * The refund is a single atomic conditional UPDATE: the WHERE clauses are
     * re-evaluated under the DB row lock, so it can never refund more than the
     * recorded charge (files > 0), can never overwrite a concurrent
     * reservation made in between (each refund decrements exactly one charged
     * file), and the byte clamp prevents a negative ledger. The day is the
     * caller-captured charge day, so a refund that straddles midnight still
     * lands on the ledger that was actually charged.
     */
    public function refund(int $userId, int $bytes, ?string $quotaDay = null): void
    {
        $quotaDay = $quotaDay ?? now()->toDateString();
        $bytes = (int) $bytes;

        $effect = TranslationQuota::where('user_id', $userId)
            ->where('quota_day', $quotaDay)
            ->where('files', '>', 0)
            ->update([
                'files' => DB::raw('files - 1'),
                'bytes' => DB::raw('CASE WHEN bytes >= ' . $bytes . ' THEN bytes - ' . $bytes . ' ELSE 0 END'),
            ]);

        if ($effect !== 1) {
            Log::warning('Quota refund matched no charged reservation', [
                'user_id' => $userId,
                'quota_day' => $quotaDay,
                'refund_bytes' => $bytes,
            ]);
        }
    }
}