<?php

namespace App\Services;

use App\Models\TranslationHistory;
use App\Models\TranslationMetric;
use App\Support\MeasurementProvenance;
use Illuminate\Support\Facades\Log;

/** Best-effort history-linked measurements; this is not a run/attempt ledger. */
class MetricsService
{
    public const PROVENANCE = MeasurementProvenance::CATEGORIES;

    private const COUNTERS = ['total_blocks', 'blocks_translated', 'blocks_cached',
        'blocks_passthrough', 'retranslated_chunks', 'cache_hits', 'cache_misses'];

    public function persistDocumentMetrics(TranslationHistory $history, array $metrics): bool
    {
        return $this->persist($history, $metrics, 'document');
    }

    public function persistTextMetrics(TranslationHistory $history, array $engineMetrics): bool
    {
        return $this->persist($history, $engineMetrics, 'text');
    }

    private function persist(TranslationHistory $history, array $input, string $type): bool
    {
        if ($input === []) {
            Log::notice('Processing measurements missing', ['translation_history_id' => $history->id]);
            return false;
        }

        try {
            $invalid = false;
            $raw = $input['measurement_metadata'] ?? [];
            if (!is_array($raw)) {
                $raw = [];
                $invalid = true;
            }
            foreach (['usage_provenance', 'usage_method', 'observed_providers'] as $field) {
                if (isset($raw[$field]) && !is_array($raw[$field])) {
                    $invalid = true;
                    unset($raw[$field]);
                }
            }
            if (isset($input['token_usage']) && !is_array($input['token_usage'])) {
                $invalid = true;
                $input['token_usage'] = [];
            }
            $invalid = $invalid || ($raw['invalid'] ?? false) === true;
            $versioned = ($raw['schema_version'] ?? null) === 1;
            $metadata = [
                'schema_version' => 1, 'field_provenance' => [], 'estimated_usage' => [],
                'observed_providers' => [], 'cache_served' => ($raw['cache_served'] ?? false) === true,
                'calls_scope' => in_array($raw['calls_scope'] ?? null, ['translation', 'operation'], true) ? $raw['calls_scope'] : null,
                'usage_scope' => 'retained_translation_result',
                'timing_scope' => in_array($raw['timing_scope'] ?? null, ['translation_result_elapsed', 'document_pipeline_elapsed'], true) ? $raw['timing_scope'] : null,
                'cache_complete' => $versioned && ($raw['cache_complete'] ?? false) === true,
                'cache_unit' => ($raw['cache_unit'] ?? null) === 'lookup' ? 'lookup' : null,
                'rework_complete' => $versioned && ($raw['rework_complete'] ?? false) === true,
                'rework_unit' => ($raw['rework_unit'] ?? null) === 'block' ? 'block' : null,
                'attribution_complete' => false,
            ];
            if (isset($raw['schema_version']) && !$versioned) {
                $invalid = true;
            }

            $values = [
                'translation_history_id' => $history->id, 'translation_type' => $type,
                'provider' => $this->text($input['provider'] ?? null, $invalid),
                'model' => $this->text($input['model'] ?? null, $invalid),
                'mode' => $this->text($input['mode'] ?? null, $invalid),
                'document_type' => $this->text($input['document_type'] ?? null, $invalid),
                'created_at' => now(),
            ];
            foreach (self::COUNTERS as $field) {
                $values[$field] = $this->integer($input[$field] ?? null, $invalid, 4294967295);
                $metadata['field_provenance'][$field] = $values[$field] === null ? 'unknown' : ($versioned ? 'measured locally' : 'legacy');
            }

            $calls = $this->integer($raw['llm_calls'] ?? null, $invalid, 4294967295);
            $values['llm_calls'] = $versioned && ($raw['calls_complete'] ?? false) === true
                && ($raw['calls_provenance'] ?? null) === 'measured locally'
                && $metadata['calls_scope'] !== null ? $calls : null;
            $metadata['field_provenance']['llm_calls'] = $values['llm_calls'] === null ? 'unknown' : 'measured locally';
            // Existing profiler calls can count wrappers/units, not outbound requests.
            $metadata['logical_llm_operations'] = $this->integer($input['llm_calls'] ?? null, $invalid, 4294967295);

            $time = $this->duration($input['execution_time_ms'] ?? $input['total_time_ms'] ?? null, $invalid);
            $values['total_time_ms'] = $versioned && ($raw['timing_observed'] ?? false) === true
                && $metadata['timing_scope'] !== null ? $time : null;
            $values['llm_total_time_ms'] = null;
            $metadata['field_provenance']['total_time_ms'] = $values['total_time_ms'] === null ? 'unknown' : 'measured locally';
            $metadata['field_provenance']['llm_total_time_ms'] = 'unknown';

            foreach (['input', 'output'] as $direction) {
                $field = $direction.'_tokens';
                $value = $this->integer($input['token_usage'][$direction] ?? null, $invalid);
                $provenance = $raw['usage_provenance'][$direction] ?? 'unknown';
                if (!in_array($provenance, self::PROVENANCE, true)) {
                    $invalid = true;
                    $provenance = 'unknown';
                }
                $values[$field] = $versioned && $provenance === 'provider-reported' ? $value : null;
                if ($value === null || !$versioned) {
                    $provenance = 'unknown';
                }
                if ($provenance === 'estimated') {
                    $metadata['estimated_usage'][$direction] = [
                        'value' => $value,
                        'method' => $this->text($raw['usage_method'][$direction] ?? null, $invalid),
                    ];
                }
                $metadata['field_provenance'][$field] = $provenance;
            }

            $pairs = $versioned ? ($raw['observed_providers'] ?? []) : [];
            if (!is_array($pairs)) {
                $pairs = [];
                $invalid = true;
            }
            foreach ($pairs as $pair) {
                if (!is_array($pair)) {
                    $invalid = true;
                    continue;
                }
                $provider = $this->text($pair['provider'] ?? null, $invalid);
                $model = $this->text($pair['model'] ?? null, $invalid);
                if ($provider === null || $provider === 'cache' || $model === null) {
                    continue;
                }
                $entry = ['provider' => $provider, 'model' => $model];
                if (!in_array($entry, $metadata['observed_providers'], true)) {
                    if (count($metadata['observed_providers']) >= 16) {
                        $invalid = true;
                        break;
                    }
                    $metadata['observed_providers'][] = $entry;
                }
            }
            $format = strtolower(pathinfo($history->original_filename ?? '', PATHINFO_EXTENSION));
            $metadata['document_format'] = in_array($format, ['pdf','docx','xlsx','pptx','csv','txt','md'], true) ? $format : null;
            $metadata['completeness'] = $invalid ? 'invalid' : 'partial';
            $metadata['reason'] = $invalid ? 'invalid_measurement_fields' : 'complete_operation_accounting_not_available';

            // Never retain arbitrary response fields, content, prompts or raw errors.
            if (strlen(json_encode($metadata, JSON_INVALID_UTF8_SUBSTITUTE | JSON_THROW_ON_ERROR)) > 8192) {
                $metadata['observed_providers'] = [];
                $metadata['completeness'] = 'invalid';
                $metadata['reason'] = 'metadata_limit_exceeded';
            }
            $values['measurement_metadata'] = $metadata;
            TranslationMetric::create($values);
            return true;
        } catch (\Throwable $error) {
            Log::warning('Processing measurements not recorded (non-fatal)', [
                'translation_history_id' => $history->id, 'exception_class' => $error::class,
            ]);
            return false;
        }
    }

    private function integer(mixed $value, bool &$invalid, int $maximum = PHP_INT_MAX): ?int
    {
        if ($value === null) {
            return null;
        }
        if (!is_int($value) || $value < 0 || $value > $maximum) {
            $invalid = true;
            return null;
        }
        return $value;
    }

    private function duration(mixed $value, bool &$invalid): ?float
    {
        if ($value === null) {
            return null;
        }
        if ((!is_int($value) && !is_float($value)) || !is_finite((float) $value) || $value < 0 || $value > 99999999999.9) {
            $invalid = true;
            return null;
        }
        return (float) $value;
    }

    private function text(mixed $value, bool &$invalid): ?string
    {
        if ($value === null || $value === '') {
            return null;
        }
        if (!is_string($value) || strlen($value) > 128 || preg_match('//u', $value) !== 1) {
            $invalid = true;
            return null;
        }
        return $value;
    }
}
