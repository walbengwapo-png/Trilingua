<?php

namespace App\Services;

use App\Models\TranslationHistory;
use App\Models\TranslationMetric;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Persists per-run AI engine metrics and document word counts.
 *
 * Metrics come from the Python FastAPI engine's DocumentContext.summary(),
 * surfaced to Laravel in the translation response envelope. Storing them lets
 * the dashboards surface real operational stats: engine latency, LLM call
 * counts, cache hit rate, retranslation rate, and active provider/model.
 *
 * Persistence is best-effort and non-fatal — a metrics write failure must
 * never break an otherwise-successful translation.
 */
class MetricsService
{
    /**
     * Persist metrics captured during a document translation.
     *
     * @param  TranslationHistory $history  The owning history row.
     * @param  array              $metrics  The 'metrics' key from the Python envelope.
     * @return bool  True on success (or when there is nothing to store).
     */
    public function persistDocumentMetrics(TranslationHistory $history, array $metrics): bool
    {
        if ($metrics === []) {
            return true;
        }

        try {
            TranslationMetric::create([
                'translation_history_id' => $history->id,
                'translation_type'       => 'document',
                'provider'               => $this->stringable($metrics['provider'] ?? null),
                'model'                  => $this->stringable($metrics['model'] ?? null),
                'mode'                   => $this->stringable($metrics['mode'] ?? null),
                'total_time_ms'          => $this->nullableFloat($metrics['total_time_ms'] ?? null),
                'llm_calls'              => $metrics['provider_usage']['request_count'] ?? null,
                'llm_total_time_ms'      => $this->nullableFloat($metrics['provider_usage']['latency_ms'] ?? null),
                'total_blocks'           => (int) ($metrics['total_blocks'] ?? 0),
                'blocks_translated'      => (int) ($metrics['blocks_translated'] ?? 0),
                'blocks_cached'          => (int) ($metrics['blocks_cached'] ?? 0),
                'blocks_passthrough'     => (int) ($metrics['blocks_passthrough'] ?? 0),
                'retranslated_chunks'    => (int) ($metrics['retranslated_chunks'] ?? 0),
                'cache_hits'             => (int) ($metrics['cache_hits'] ?? 0),
                'cache_misses'           => (int) ($metrics['cache_misses'] ?? 0),
                'provider_usage'         => $metrics['provider_usage'] ?? null,
                'input_tokens'           => $metrics['provider_usage']['input_tokens'] ?? null,
                'output_tokens'          => $metrics['provider_usage']['output_tokens'] ?? null,
                'document_type'          => $this->stringable($metrics['document_type'] ?? null),
                'created_at'             => now(),
            ]);

            return true;
        } catch (\Throwable $e) {
            Log::warning('MetricsService: Failed to persist document metrics (non-fatal)', [
                'exception' => $e->getMessage(),
                'translation_history_id' => $history->id,
            ]);

            return false;
        }
    }

    /**
     * Persist metrics captured during a text translation.
     *
     * @param  TranslationHistory $history       The owning history row.
     * @param  array              $engineMetrics Array with provider/model/token_usage/execution_time_ms.
     * @return bool  True on success.
     */
    public function persistTextMetrics(TranslationHistory $history, array $engineMetrics): bool
    {
        try {
            TranslationMetric::create([
                'translation_history_id' => $history->id,
                'translation_type'       => 'text',
                'provider'               => $this->stringable($engineMetrics['provider'] ?? null),
                'model'                  => $this->stringable($engineMetrics['model'] ?? null),
                'mode'                   => null,
                'total_time_ms'          => $this->nullableFloat($engineMetrics['execution_time_ms'] ?? $engineMetrics['total_time_ms'] ?? null),
                'llm_calls'              => $engineMetrics['provider_usage']['request_count'] ?? null,
                'llm_total_time_ms'      => $this->nullableFloat($engineMetrics['provider_usage']['latency_ms'] ?? null),
                'provider_usage'         => $engineMetrics['provider_usage'] ?? null,
                'input_tokens'           => $engineMetrics['provider_usage']['input_tokens'] ?? null,
                'output_tokens'          => $engineMetrics['provider_usage']['output_tokens'] ?? null,
                'created_at'             => now(),
            ]);

            return true;
        } catch (\Throwable $e) {
            Log::warning('MetricsService: Failed to persist text metrics (non-fatal)', [
                'exception' => $e->getMessage(),
                'translation_history_id' => $history->id,
            ]);

            return false;
        }
    }

    private function stringable(mixed $value): ?string
    {
        if ($value === null || $value === '') {
            return null;
        }
        return (string) $value;
    }

    private function nullableFloat(mixed $value): ?float
    {
        if ($value === null || $value === '') {
            return null;
        }
        return (float) $value;
    }
}