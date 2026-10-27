<?php

namespace App\Services;

use App\Models\TranslationMetric;

/** Aggregates recorded samples; these rows do not establish distinct runs. */
class EngineMetricsSummary
{
    public function summarize(): array
    {
        $result = [
            'samples' => 0, 'measured_samples' => 0, 'legacy_samples' => 0,
            'avg_latency_ms' => null, 'latency_scope' => null, 'latency_samples' => 0,
            'cache_hit_rate' => null, 'cache_samples' => 0,
            'retranslation_rate' => null, 'rework_samples' => 0,
            'last_observed_providers' => [], 'last_observed_at' => null,
            'attribution_samples' => 0, 'latest_usage' => [],
        ];
        $timings = [];
        $cache = ['hits' => 0, 'misses' => 0];
        $rework = ['repaired' => 0, 'translated' => 0];

        TranslationMetric::query()->chunkById(500, function ($rows) use (&$result, &$timings, &$cache, &$rework): void {
            foreach ($rows as $row) {
                $result['samples']++;
                $metadata = $row->getAttribute('measurement_metadata');
                if (!is_array($metadata) || ($metadata['schema_version'] ?? null) !== 1) {
                    $result['legacy_samples']++;
                    $result['latest_usage'] = [];
                    continue;
                }
                $result['measured_samples']++;
                $result['latest_usage'] = [];
                foreach (['input', 'output'] as $direction) {
                    $field = $direction.'_tokens';
                    $estimate = $metadata['estimated_usage'][$direction] ?? null;
                    $result['latest_usage'][$direction] = [
                        'value' => $estimate['value'] ?? $row->$field,
                        'provenance' => $metadata['field_provenance'][$field] ?? 'unknown',
                        'method' => $estimate['method'] ?? null,
                    ];
                }

                if (($metadata['observed_providers'] ?? []) !== []) {
                    $result['attribution_samples']++;
                    $result['last_observed_providers'] = $metadata['observed_providers'];
                    $result['last_observed_at'] = $row->created_at?->toIso8601String();
                }

                $scope = $metadata['timing_scope'] ?? null;
                $format = $metadata['document_format'] ?? null;
                if ($row->total_time_ms !== null && $scope !== null
                    && ($row->translation_type === 'text' || $format !== null)) {
                    $cohort = json_encode([$row->translation_type, $row->mode, $format, $scope]);
                    $timings[$cohort] ??= ['sum' => 0, 'count' => 0, 'scope' => $scope];
                    $timings[$cohort]['sum'] += $row->total_time_ms;
                    $timings[$cohort]['count']++;
                }

                if (($metadata['cache_complete'] ?? false) === true
                    && ($metadata['cache_unit'] ?? null) === 'lookup'
                    && $row->cache_hits !== null && $row->cache_misses !== null) {
                    $cache['hits'] += $row->cache_hits;
                    $cache['misses'] += $row->cache_misses;
                    $result['cache_samples']++;
                }
                if (($metadata['rework_complete'] ?? false) === true
                    && ($metadata['rework_unit'] ?? null) === 'block'
                    && $row->retranslated_chunks !== null && $row->blocks_translated !== null
                    && $row->retranslated_chunks <= $row->blocks_translated) {
                    $rework['repaired'] += $row->retranslated_chunks;
                    $rework['translated'] += $row->blocks_translated;
                    $result['rework_samples']++;
                }
            }
        });

        // An average spanning different scopes/modes/formats would imply comparability.
        if (count($timings) === 1) {
            $timing = reset($timings);
            $result['avg_latency_ms'] = round($timing['sum'] / $timing['count'], 1);
            $result['latency_scope'] = $timing['scope'];
            $result['latency_samples'] = $timing['count'];
        }
        $denominator = $cache['hits'] + $cache['misses'];
        if ($denominator > 0) {
            $result['cache_hit_rate'] = round($cache['hits'] / $denominator * 100, 1);
        }
        if ($rework['translated'] > 0) {
            $result['retranslation_rate'] = round($rework['repaired'] / $rework['translated'] * 100, 1);
        }

        return $result;
    }
}
