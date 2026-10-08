<?php

namespace App\Services;

use App\Models\StorageCleanupOutbox;
use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use Illuminate\Support\Facades\Log;

/**
 * The storage-cleanup outbox: durable, idempotent, retryable deletion of
 * objects whose owning history row has been removed.
 *
 * Roles:
 *  - KIND_ORPHAN: an object is no longer referenced by any live row and should
 *    be deleted. The worker re-checks live references immediately before
 *    deleting so a shared or re-referenced object is never removed.
 *  - KIND_CANDIDATE: a regenerated object uploaded before its commit. It is
 *    deleted (atomically, in the publish transaction) once committed; any
 *    surviving candidate is unambiguously never-committed and may be reclaimed
 *    by the stale-candidate pass.
 *
 * key properties:
 *  - Intent + unique backend/path pairs are committed in the same transaction
 *    that removes the row (see HistoryService::deleteRecord), so a storage
 *    outage cannot strand data that is no longer discoverable.
 *  - Deletes are idempotent; a missing object is already success (the
 *    backend 404s and removed local files are both treated as done).
 *  - A shared original is never deleted while another surviving history row
 *    still references it. `firstOrCreate` re-arms a DONE row so a repeated
 *    intent can never be silently left 'done'.
 */
class StorageCleanupService
{
    public const KIND_ORPHAN = 'orphan';
    public const KIND_CANDIDATE = 'candidate';

    public function __construct(
        private StorageService $storage,
    ) {}

    /**
     * A row deleted in the current batch is skipped while checking live
     * references, but any OTHER surviving row - a retranslated child of a
     * deleted parent, a nested document - still protects the shared object.
     *
     * A `translation_jobs` row is a live reference too, and it holds objects that
     * NO history row points at. Two independent reasons:
     *
     *  - `original_storage_path` / `original_storage_backend` is the durable
     *    source copy a worker rebuilds its scratch file from
     *    (TranslateDocumentJob::resolveInputPath) and the only input an admin
     *    replay can use (Admin\JobController::retry).
     *  - `translated_storage_path` / `translated_storage_backend` is written
     *    BEFORE the history insert so a partially persisted attempt reuses the
     *    object instead of re-uploading (durableTranslatedUpload). A retry that
     *    depends on that object must not have it reclaimed underneath it.
     *
     * Only ACTIVE_STATUSES and `failed` rows flagged recoverable are treated as
     * live, because those are exactly the rows a worker or an admin replay can
     * still consume. A `completed` or `cancelled` row owns nothing further:
     * its objects belong to its history row, and deleting that history row must
     * really delete them.
     *
     * $excludeJobIds exists so the WORKER'S OWN release path
     * (TranslateDocumentJob::releaseUnreferencedObject) can ask the same
     * question while excluding the row doing the asking. Without it, the job row
     * that just recorded `translated_storage_path` would protect the very object
     * its refused completion is required to release, and the object would leak
     * forever instead of being cleaned up on the next attempt.
     */
    public function hasLiveReference(
        string $backend,
        string $path,
        array $excludeHistoryIds = [],
        array $excludeJobIds = []
    ): bool {
        if ($path === '') {
            return false;
        }

        if (TranslationHistory::query()
            ->whereNotIn('id', $excludeHistoryIds ?: [0])
            ->where(function ($q) use ($backend, $path) {
                $q->where(function ($x) use ($backend, $path) {
                    $x->where('storage_path', $path)
                        ->where(fn ($b) => $b->whereNull('storage_backend')->orWhere('storage_backend', $backend));
                })->orWhere(function ($x) use ($backend, $path) {
                    $x->where('original_storage_path', $path)
                        ->where(fn ($b) => $b->whereNull('original_storage_backend')->orWhere('original_storage_backend', $backend));
                });
            })
            ->exists()) {
            return true;
        }

        return $this->hasLiveJobReference($backend, $path, $excludeJobIds);
    }

    /**
     * The `translation_jobs` half of hasLiveReference: is any job that can still
     * be executed or replayed holding this object?
     *
     * Kept separate so the active/recoverable predicate is stated exactly once.
     */
    public function hasLiveJobReference(string $backend, string $path, array $excludeJobIds = []): bool
    {
        if ($path === '') {
            return false;
        }

        return TranslationJob::query()
            ->whereNotIn('id', $excludeJobIds ?: [0])
            ->where(function ($q) {
                $q->whereIn('status', TranslationJob::ACTIVE_STATUSES)
                    ->orWhere(function ($f) {
                        $f->where('status', TranslationJob::STATUS_FAILED)
                            ->where('recoverable', true);
                    });
            })
            ->where(function ($q) use ($backend, $path) {
                $q->where(function ($x) use ($backend, $path) {
                    $x->where('original_storage_path', $path)
                        ->where(fn ($b) => $b->whereNull('original_storage_backend')->orWhere('original_storage_backend', $backend));
                })->orWhere(function ($x) use ($backend, $path) {
                    $x->where('translated_storage_path', $path)
                        ->where(fn ($b) => $b->whereNull('translated_storage_backend')->orWhere('translated_storage_backend', $backend));
                });
            })
            ->exists();
    }

    /**
     * Record (or re-arm) a durable orphan deletion intent. Re-arming closes the
     * gap where firstOrCreate would silently keep a previously-DONE row done.
     */
    public function recordPending(string $backend, string $path, ?int $historyId = null): void
    {
        $row = StorageCleanupOutbox::where('backend', $backend)->where('path', $path)->first();

        if ($row === null) {
            StorageCleanupOutbox::create([
                'backend' => $backend,
                'path' => $path,
                'history_id' => $historyId,
                'kind' => self::KIND_ORPHAN,
                'status' => StorageCleanupOutbox::STATUS_PENDING,
            ]);
            return;
        }

        if ($row->kind !== self::KIND_ORPHAN || $row->status !== StorageCleanupOutbox::STATUS_PENDING) {
            $row->kind = self::KIND_ORPHAN;
            $row->status = StorageCleanupOutbox::STATUS_PENDING;
            $row->attempts = 0;
            $row->last_error = 're-armed'; // a new cleanup intent supersedes the old one
            $row->history_id = $historyId ?? $row->history_id;
            $row->save();
        }
    }

    /**
     * Durably record a publish-candidate BEFORE the object is uploaded. A hidden
     * crash between upload and commit leaves this row behind so the reclaimer
     * can remove the orphan instead of stranding it.
     */
    public function recordPublishCandidate(string $backend, string $path, ?int $historyId = null): void
    {
        $row = StorageCleanupOutbox::where('backend', $backend)->where('path', $path)->first();

        if ($row === null) {
            StorageCleanupOutbox::create([
                'backend' => $backend,
                'path' => $path,
                'history_id' => $historyId,
                'kind' => self::KIND_CANDIDATE,
                'status' => StorageCleanupOutbox::STATUS_PENDING,
            ]);
            return;
        }

        if ($row->status !== StorageCleanupOutbox::STATUS_PENDING || $row->kind !== self::KIND_CANDIDATE) {
            $row->kind = self::KIND_CANDIDATE;
            $row->status = StorageCleanupOutbox::STATUS_PENDING;
            $row->attempts = 0;
            $row->save();
        }
    }

    /**
     * Clear candidate rows for objects that were successfully committed. Called
     * from inside the publish transaction so it is atomic with the pointer write
     * - a surviving candidate therefore always means never-committed.
     *
     * @param  array<int, array{0: string, 1: string}>  $pairs  [backend, path][]
     */
    public function markCandidatesCommitted(array $pairs): void
    {
        foreach ($pairs as [$backend, $path]) {
            StorageCleanupOutbox::where('kind', self::KIND_CANDIDATE)
                ->where('backend', $backend)
                ->where('path', $path)
                ->delete();
        }
    }

    /**
     * Process pending ORPHAN cleanups. Before deleting, re-checks live
     * references: a path that is referenced again is never deleted - the intent
     * is cancelled (marked done) and a fresh intent will be recorded if it later
     * becomes orphaned again. Missing objects resolve to done; real failures
     * (network, permissions) bump attempts and keep the row pending.
     *
     * @return array{processed: int, remaining: int}
     */
    public function processPending(int $limit = 50): array
    {
        $pending = StorageCleanupOutbox::where('kind', self::KIND_ORPHAN)
            ->where('status', StorageCleanupOutbox::STATUS_PENDING)
            ->orderBy('id')
            ->limit($limit)
            ->get();

        $processed = 0;

        foreach ($pending as $entry) {
            // Immediate re-check: NEVER delete a path a surviving history row or a
            // recoverable job still references.
            if ($this->hasLiveReference((string) $entry->backend, (string) $entry->path)) {
                $entry->status = StorageCleanupOutbox::STATUS_DONE;
                $entry->last_error = 'skipped: path has a live reference';
                $entry->save();
                $processed++;
                continue;
            }

            try {
                $this->storage->delete((string) $entry->backend, (string) $entry->path);
                $entry->status = StorageCleanupOutbox::STATUS_DONE;
                $entry->save();
                $processed++;
            } catch (\Throwable $e) {
                // Clamp so an endlessly failing backend can keep the entry
                // pending forever WITHOUT the retry counter overflowing either
                // supported engine; the visible count is informational only.
                $entry->attempts = min((int) $entry->attempts + 1, 1000000);
                $entry->last_error = mb_substr($e->getMessage(), 0, 500);
                $entry->save();

                Log::warning('Storage cleanup deferred to a later pass', [
                    'backend' => $entry->backend,
                    'path' => $entry->path,
                    'attempts' => $entry->attempts,
                    'exception' => $e->getMessage(),
                ]);
            }
        }

        $remaining = StorageCleanupOutbox::where('kind', self::KIND_ORPHAN)
            ->where('status', StorageCleanupOutbox::STATUS_PENDING)
            ->count();

        return ['processed' => $processed, 'remaining' => $remaining];
    }

    /**
     * Reclaim publish-candidates that are older than the grace period AND are
     * not live-referenced. A candidate that survives the grace period was never
     * committed (the publish transaction would have deleted it), so its object
     * is safe to remove. This is idempotent and safe to run repeatedly.
     *
     * @return array{reclaimed: int, remaining: int}
     */
    public function reclaimStalePublishCandidates(int $graceSeconds = 3600, int $limit = 50): array
    {
        $cutoff = now()->subSeconds(max(1, $graceSeconds));

        $candidates = StorageCleanupOutbox::where('kind', self::KIND_CANDIDATE)
            ->where('status', StorageCleanupOutbox::STATUS_PENDING)
            ->where('created_at', '<=', $cutoff)
            ->orderBy('id')
            ->limit($limit)
            ->get();

        $reclaimed = 0;

        foreach ($candidates as $entry) {
            if ($this->hasLiveReference((string) $entry->backend, (string) $entry->path)) {
                continue; // never delete anything a live row references
            }

            try {
                $this->storage->delete((string) $entry->backend, (string) $entry->path);
                $entry->status = StorageCleanupOutbox::STATUS_DONE;
                $entry->save();
                $reclaimed++;
            } catch (\Throwable $e) {
                $entry->attempts = min((int) $entry->attempts + 1, 1000000);
                $entry->last_error = mb_substr($e->getMessage(), 0, 500);
                $entry->save();
                Log::warning('Publish-candidate reclamation deferred to a later pass', [
                    'backend' => $entry->backend,
                    'path' => $entry->path,
                    'exception' => $e->getMessage(),
                ]);
            }
        }

        $remaining = StorageCleanupOutbox::where('kind', self::KIND_CANDIDATE)
            ->where('status', StorageCleanupOutbox::STATUS_PENDING)
            ->count();

        return ['reclaimed' => $reclaimed, 'remaining' => $remaining];
    }
}