<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Append-only audit trail for admin review actions.
 *
 * translation_block_id is null for text-translation edits.
 */
class TranslationEditLog extends Model
{
    public $timestamps = false;

    protected $table = 'translation_edit_log';

    protected $fillable = [
        'translation_history_id',
        'translation_block_id',
        'admin_id',
        'action',
        'previous_text',
        'new_text',
        'note',
        'created_at',
    ];

    protected $casts = [
        'created_at' => 'datetime',
    ];

    public function translationHistory(): BelongsTo
    {
        return $this->belongsTo(TranslationHistory::class);
    }

    public function translationBlock(): BelongsTo
    {
        return $this->belongsTo(TranslationBlock::class);
    }

    public function admin(): BelongsTo
    {
        return $this->belongsTo(User::class, 'admin_id');
    }
}
