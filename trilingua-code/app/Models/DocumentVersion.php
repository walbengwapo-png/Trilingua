<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/** Immutable artifact snapshot for a document translation. */
class DocumentVersion extends Model
{
    protected $fillable = [
        'translation_history_id', 'version', 'storage_path', 'translated_filename',
        'artifact_label', 'created_by', 'created_at', 'metadata',
    ];

    public $timestamps = false;

    protected $casts = [
        'version' => 'integer',
        'created_at' => 'datetime',
        'metadata' => 'array',
    ];

    public function translationHistory(): BelongsTo
    {
        return $this->belongsTo(TranslationHistory::class);
    }

    public function creator(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }
}
