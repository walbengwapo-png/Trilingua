<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Str;

class TranslationJob extends Model
{
    public const STATUS_CREATED = 'created';
    public const STATUS_QUEUED = 'queued';
    public const STATUS_PROCESSING = 'processing';
    public const STATUS_COMPLETED = 'completed';
    public const STATUS_FAILED = 'failed';
    public const STATUS_CANCELLED = 'cancelled';

    public const ACTIVE_STATUSES = [
        self::STATUS_CREATED,
        self::STATUS_QUEUED,
        self::STATUS_PROCESSING,
    ];

    public const TERMINAL_STATUSES = [
        self::STATUS_COMPLETED,
        self::STATUS_FAILED,
        self::STATUS_CANCELLED,
    ];

    protected $guarded = [];

    protected $casts = [
        'file_size'          => 'integer',
        'progress'           => 'integer',
        'attempts'           => 'integer',
        'recoverable'        => 'boolean',
        'last_heartbeat_at'  => 'datetime',
        'started_at'         => 'datetime',
        'completed_at'       => 'datetime',
        'terminal_failed_at' => 'datetime',
        'created_at'         => 'datetime',
        'updated_at'         => 'datetime',
    ];

    protected static function booted(): void
    {
        static::creating(function (self $job): void {
            $job->uuid = $job->uuid ?? (string) Str::uuid();
        });
    }

    public function user()
    {
        return $this->belongsTo(User::class);
    }

    public function parentDocument()
    {
        return $this->belongsTo(TranslationHistory::class, 'parent_document_id');
    }

    public function isActive(): bool
    {
        return in_array($this->status, self::ACTIVE_STATUSES, true);
    }

    public function isTerminal(): bool
    {
        return in_array($this->status, self::TERMINAL_STATUSES, true);
    }

    /**
     * A job is safe to replay from the admin Retry flow only when it failed
     * terminally AND a durable original is recorded for reconstruction.
     */
    public function isTerminalFailedRecoverable(): bool
    {
        return $this->status === self::STATUS_FAILED
            && $this->recoverable === true
            && filled($this->original_storage_path)
            && filled($this->original_storage_backend);
    }

    /**
     * Transition helpers are MTM-safe: every write is conditional on the row
     * still being in an active state at the database layer, so an old worker or
     * a reconciler can never overwrite an already completed/failed/cancelled row
     * without an explicit recovery. They return false when the transition was a
     * no-op.
     */

    public function markQueued(bool $recovered = false): bool
    {
        if (!$recovered && !$this->isActive()) {
            return false;
        }

        $updated = static::query()
            ->whereKey($this->getKey())
            ->where(function ($q) use ($recovered) {
                $q->whereIn('status', self::ACTIVE_STATUSES);
                if ($recovered) {
                    // An explicit operator recovery may revive a failed job only.
                    $q->orWhere('status', self::STATUS_FAILED);
                }
            })
            ->update([
                'status'            => self::STATUS_QUEUED,
                'error'             => null,
                'completed_at'      => null,
                'terminal_failed_at' => null,
                'last_heartbeat_at' => now(),
            ]);

        if ($updated) {
            $this->refresh();
        }

        return (bool) $updated;
    }

    public function markProcessing(): bool
    {
        if (!$this->isActive()) {
            return false;
        }

        $updated = static::query()
            ->whereKey($this->getKey())
            ->whereIn('status', self::ACTIVE_STATUSES)
            ->update([
                'status'            => self::STATUS_PROCESSING,
                'attempts'          => ($this->attempts ?? 0) + 1,
                'started_at'        => $this->started_at ?? now(),
                'last_heartbeat_at' => now(),
                'error'             => null,
                'terminal_failed_at' => null,
            ]);

        if ($updated) {
            $this->refresh();
        }

        return (bool) $updated;
    }

    public function noteProgress(int $progress): bool
    {
        if (!$this->isActive()) {
            return false;
        }

        $progress = max((int) $this->progress, $progress);

        $updated = static::query()
            ->whereKey($this->getKey())
            ->whereIn('status', self::ACTIVE_STATUSES)
            ->update([
                'progress'          => $progress,
                'last_heartbeat_at' => now(),
            ]);

        if ($updated) {
            $this->progress = $progress;
            $this->last_heartbeat_at = now();
        }

        return (bool) $updated;
    }

    public function markCompleted(string $storageBackend, string $storagePath, ?int $translationHistoryId = null): bool
    {
        if (!$this->isActive()) {
            return false;
        }

        $updated = static::query()
            ->whereKey($this->getKey())
            ->whereIn('status', self::ACTIVE_STATUSES)
            ->update([
                'status'                => self::STATUS_COMPLETED,
                'progress'              => 100,
                'storage_backend'       => $storageBackend,
                'storage_path'          => $storagePath,
                'translation_history_id' => $translationHistoryId,
                'error'                 => null,
                'last_heartbeat_at'     => now(),
                'completed_at'          => now(),
                'terminal_failed_at'    => null,
                'recoverable'           => null,
            ]);

        if ($updated) {
            $this->refresh();
        }

        return (bool) $updated;
    }

    /**
     * Regular (mid-attempt) failure note. Kept for backwards compatibility with
     * code that just records an error; terminal failures should prefer
     * markTerminallyFailed.
     */
    public function noteError(\Throwable $e): bool
    {
        if (!$this->isActive()) {
            return false;
        }

        $updated = static::query()
            ->whereKey($this->getKey())
            ->whereIn('status', self::ACTIVE_STATUSES)
            ->update([
                'status'       => self::STATUS_FAILED,
                'error'        => Str::limit($e->getMessage(), 2000),
                'completed_at' => $this->completed_at ?? now(),
            ]);

        if ($updated) {
            $this->refresh();
        }

        return (bool) $updated;
    }

    /**
     * Terminal failure with recoverability evidence used by the admin Retry
     * flow. $recoverable is true only when a durable original exists that a
     * replayed job can reconstruct the worker-local input from.
     */
    public function markTerminallyFailed(\Throwable $e, bool $recoverable): bool
    {
        if (!$this->isActive()) {
            return false;
        }

        $now = now();

        $updated = static::query()
            ->whereKey($this->getKey())
            ->whereIn('status', self::ACTIVE_STATUSES)
            ->update([
                'status'            => self::STATUS_FAILED,
                'error'             => Str::limit($e->getMessage(), 2000),
                'completed_at'      => $this->completed_at ?? $now,
                'terminal_failed_at' => $now,
                'recoverable'       => $recoverable,
            ]);

        if ($updated) {
            $this->refresh();
        }

        return (bool) $updated;
    }

    /**
     * Reconciler path: only another active row may become failed, and the write
     * is conditional at the database layer so a concurrent completion is never
     * clobbered.
     */
    public function reconcileMarkFailed(string $reason): bool
    {
        if (!$this->isActive()) {
            return false;
        }

        $now = now();

        $updated = static::query()
            ->whereKey($this->getKey())
            ->whereIn('status', self::ACTIVE_STATUSES)
            ->update([
                'status'            => self::STATUS_FAILED,
                'error'             => Str::limit($reason, 2000),
                'completed_at'      => $this->completed_at ?? $now,
                'terminal_failed_at' => $now,
                'recoverable'       => filled($this->original_storage_path) && filled($this->original_storage_backend),
            ]);

        if ($updated) {
            $this->refresh();
        }

        return (bool) $updated;
    }

    /**
     * Canonical payload hash for a document translation submission.
     *
     * Two submissions are "the same work" iff the owning user, the exact file
     * bytes, the language pair, the engine mode and the PDF column mode are all
     * identical. Content-based (not name/size based), so renames do not create
     * duplicate work and same-bytes submissions always dedup.
     *
     * @param  int  $userId            Owner id.
     * @param  string  $fileContentHash sha256 of the original file bytes.
     * @param  string  $sourceLang
     * @param  string  $targetLang
     * @param  string  $mode            fast|balanced|thorough.
     * @param  string  $pdfColumnMode   auto|single|left|right.
     * @param  int|null  $parentDocumentId Re-translation parent, if any.
     */
    public static function payloadHash(
        int $userId,
        string $fileContentHash,
        string $sourceLang,
        string $targetLang,
        string $mode = 'balanced',
        string $pdfColumnMode = 'auto',
        ?int $parentDocumentId = null,
    ): string {
        return hash('sha256', implode('|', [
            (string) $userId,
            $fileContentHash,
            $sourceLang,
            $targetLang,
            $mode,
            $pdfColumnMode,
            (string) ($parentDocumentId ?? ''),
        ]));
    }
}