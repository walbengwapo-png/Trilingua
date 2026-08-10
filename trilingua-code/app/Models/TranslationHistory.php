<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class TranslationHistory extends Model
{
    public $timestamps = false;

    protected $table = 'translation_history';

    protected $fillable = [
        'user_id',
        'translation_type',
        'original_filename',
        'translated_filename',
        'source_language',
        'target_language',
        'storage_path',
        'original_storage_path',
        'parent_document_id',
        'file_size',
        'status',
        'signed_url_expires_at',
        'source_text',
        'translated_text',
        'sidecar',
        'review_status',
        'quality_score',
        'reviewed_by',
        'reviewed_at',
        'flag_reason',
        'flag_note',
        'is_priority',
        'priority_at',
        'is_bookmarked',
        'bookmarked_at',
    ];

    protected $casts = [
        'signed_url_expires_at' => 'datetime',
        'created_at' => 'datetime',
        'updated_at' => 'datetime',
        'reviewed_at' => 'datetime',
        'quality_score' => 'integer',
        'sidecar' => 'array',
        'is_priority' => 'boolean',
        'priority_at' => 'datetime',
        'is_bookmarked' => 'boolean',
        'bookmarked_at' => 'datetime',
    ];

    public function user()
    {
        return $this->belongsTo(User::class);
    }

    /**
     * The original document that this translation was generated from.
     */
    public function parentDocument()
    {
        return $this->belongsTo(TranslationHistory::class, 'parent_document_id');
    }

    /**
     * All translations generated from this original document.
     */
    public function translations()
    {
        return $this->hasMany(TranslationHistory::class, 'parent_document_id');
    }

    /**
     * The admin who last reviewed this translation.
     */
    public function reviewer(): BelongsTo
    {
        return $this->belongsTo(User::class, 'reviewed_by');
    }

    /**
     * Individual blocks (document translations only).
     */
    public function blocks(): HasMany
    {
        return $this->hasMany(TranslationBlock::class);
    }

    /**
     * Append-only audit trail of admin review actions.
     */
    public function editLog(): HasMany
    {
        return $this->hasMany(TranslationEditLog::class);
    }
}