<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

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
        'job_id',
    ];

    protected $casts = [
        'signed_url_expires_at' => 'datetime',
        'created_at' => 'datetime',
        'updated_at' => 'datetime',
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
}
