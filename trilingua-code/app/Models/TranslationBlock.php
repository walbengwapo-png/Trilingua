<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

/**
 * One row per extracted block of a document translation.
 *
 * ai_translated_text is immutable — the original AI output is preserved for
 * audit purposes. Admin edits are applied to current_text.
 */
class TranslationBlock extends Model
{
    public $timestamps = false;

    protected $table = 'translation_blocks';

    protected $fillable = [
        'translation_history_id',
        'block_index',
        'block_type',
        'source_text',
        'ai_translated_text',
        'current_text',
        'quality_score',
        'quality_issues',
        'status',
        'flag_reason',
        'flag_note',
        'edited_by',
        'edited_at',
    ];

    protected $casts = [
        'block_index' => 'integer',
        'quality_score' => 'integer',
        'quality_issues' => 'array',
        'edited_at' => 'datetime',
        'created_at' => 'datetime',
    ];

    public function translationHistory(): BelongsTo
    {
        return $this->belongsTo(TranslationHistory::class);
    }

    public function editor(): BelongsTo
    {
        return $this->belongsTo(User::class, 'edited_by');
    }

    /**
     * Audit entries for this block's edits/flags/verifications.
     */
    public function editLog(): HasMany
    {
        return $this->hasMany(TranslationEditLog::class);
    }
}
