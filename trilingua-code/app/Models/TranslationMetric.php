<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Engine metrics for a single translation run, captured from the Python
 * FastAPI engine's DocumentContext.summary().
 */
class TranslationMetric extends Model
{
    public $timestamps = false;

    protected $table = 'translation_metrics';

    protected $fillable = [
        'translation_history_id',
        'translation_type',
        'provider',
        'model',
        'mode',
        'total_time_ms',
        'llm_calls',
        'llm_total_time_ms',
        'total_blocks',
        'blocks_translated',
        'blocks_cached',
        'blocks_passthrough',
        'retranslated_chunks',
        'cache_hits',
        'cache_misses',
        'provider_usage',
        'input_tokens',
        'output_tokens',
        'document_type',
        'created_at',
    ];

    protected $casts = [
        'total_time_ms' => 'float',
        'llm_calls' => 'integer',
        'llm_total_time_ms' => 'float',
        'total_blocks' => 'integer',
        'blocks_translated' => 'integer',
        'blocks_cached' => 'integer',
        'blocks_passthrough' => 'integer',
        'retranslated_chunks' => 'integer',
        'cache_hits' => 'integer',
        'cache_misses' => 'integer',
        'provider_usage' => 'array',
        'input_tokens' => 'integer',
        'output_tokens' => 'integer',
        'created_at' => 'datetime',
    ];

    public function translation(): BelongsTo
    {
        return $this->belongsTo(TranslationHistory::class, 'translation_history_id');
    }
}