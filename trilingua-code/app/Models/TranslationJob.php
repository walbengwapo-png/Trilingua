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

    protected $guarded = [];

    protected $casts = [
        'file_size'          => 'integer',
        'progress'           => 'integer',
        'attempts'           => 'integer',
        'last_heartbeat_at'  => 'datetime',
        'started_at'         => 'datetime',
        'completed_at'       => 'datetime',
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

    public function markQueued(): void
    {
        $this->status = self::STATUS_QUEUED;
        $this->save();
    }

    public function markProcessing(): void
    {
        $this->status = self::STATUS_PROCESSING;
        $this->attempts = ($this->attempts ?? 0) + 1;
        $this->started_at = $this->started_at ?? now();
        $this->last_heartbeat_at = now();
        $this->error = null;
        $this->save();
    }

    public function noteProgress(int $progress): void
    {
        $this->progress = max((int) $this->progress, $progress);
        $this->last_heartbeat_at = now();
        $this->save();
    }

    public function noteError(\Throwable $e): void
    {
        $this->status = self::STATUS_FAILED;
        $this->error = Str::limit($e->getMessage(), 2000);
        $this->completed_at = $this->completed_at ?? now();
        $this->save();
    }

    public function markCompleted(string $storageBackend, string $storagePath, ?int $translationHistoryId = null): void
    {
        $this->status = self::STATUS_COMPLETED;
        $this->progress = 100;
        $this->storage_backend = $storageBackend;
        $this->storage_path = $storagePath;
        $this->translation_history_id = $translationHistoryId;
        $this->error = null;
        $this->last_heartbeat_at = now();
        $this->completed_at = now();
        $this->save();
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