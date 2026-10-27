<?php

namespace App\Services\Translation\DTO;

use App\Support\MeasurementProvenance;

/**
 * DTO for translation responses.
 * 
 * Normalized response from the Python AI Engine.
 * Laravel never knows which AI provider was used internally.
 */
class TranslationResponse
{
    public function __construct(
        public readonly string $translatedText,
        public readonly string $provider = '',
        public readonly string $model = '',
        public readonly array $tokenUsage = [],
        public readonly float $executionTimeMs = 0.0,
        public readonly string $mode = 'balanced',
        public readonly ?float $qualityScore = null,
        public readonly array $qualityIssues = [],
        public readonly array $warnings = [],
        public readonly bool $success = true,
        public readonly string $errorMessage = '',
        public readonly array $measurementMetadata = [],
    ) {}

    /**
     * Create from Python API response array.
     */
    public static function fromArray(array $data): self
    {
        $metadata = is_array($data['measurement_metadata'] ?? null)
            ? $data['measurement_metadata'] : (isset($data['measurement_metadata']) ? ['schema_version' => 1, 'invalid' => true] : []);
        $usage = [];
        $rawUsage = $data['token_usage'] ?? [];
        if (!is_array($rawUsage)) {
            $metadata['invalid'] = true;
            $rawUsage = [];
        }
        foreach (['input', 'output'] as $direction) {
            $value = $rawUsage[$direction] ?? null;
            if (is_int($value) && $value >= 0) {
                $usage[$direction] = $value;
            } elseif ($value !== null) {
                $metadata['invalid'] = true;
            }
        }
        return new self(
            translatedText: $data['translated'] ?? $data['translated_text'] ?? '',
            provider: $data['provider'] ?? '',
            model: $data['model'] ?? '',
            tokenUsage: $usage,
            executionTimeMs: $data['execution_time_ms'] ?? 0.0,
            mode: $data['mode'] ?? 'balanced',
            qualityScore: isset($data['quality_score'])
                ? (float) $data['quality_score']
                : null,
            qualityIssues: $data['quality_issues'] ?? [],
            warnings: $data['warnings'] ?? [],
            success: $data['success'] ?? true,
            errorMessage: $data['error_message'] ?? $data['error'] ?? '',
            measurementMetadata: $metadata,
        );
    }

    /**
     * Convert to array for JSON response.
     */
    public function toArray(): array
    {
        return [
            'translated' => $this->translatedText,
            'provider' => $this->provider,
            'model' => $this->model,
            'token_usage' => $this->tokenUsage,
            'execution_time_ms' => $this->executionTimeMs,
            'mode' => $this->mode,
            'quality_score' => $this->qualityScore,
            'quality_issues' => $this->qualityIssues,
            'warnings' => $this->warnings,
            'success' => $this->success,
            'measurement_metadata' => $this->publicMetadata(),
        ];
    }

    private function publicMetadata(): array
    {
        $raw = $this->measurementMetadata;
        $versioned = ($raw['schema_version'] ?? null) === 1;
        $scope = in_array($raw['calls_scope'] ?? null, ['translation', 'operation'], true) ? $raw['calls_scope'] : null;
        $complete = $versioned && ($raw['calls_complete'] ?? false) === true && $scope !== null
            && ($raw['calls_provenance'] ?? null) === 'measured locally'
            && is_int($raw['llm_calls'] ?? null) && $raw['llm_calls'] >= 0 && $raw['llm_calls'] <= 4294967295;
        $metadata = [
            'schema_version' => $versioned ? 1 : null,
            'cache_served' => $versioned && ($raw['cache_served'] ?? false) === true,
            'llm_calls' => $complete ? $raw['llm_calls'] : null,
            'calls_complete' => $complete, 'calls_scope' => $scope,
            'calls_provenance' => $complete ? 'measured locally' : 'unknown',
            'usage_scope' => 'retained_translation_result',
            'timing_scope' => in_array($raw['timing_scope'] ?? null, ['translation_result_elapsed', 'document_pipeline_elapsed'], true) ? $raw['timing_scope'] : null,
        ];
        foreach (['input', 'output'] as $direction) {
            $provenance = $raw['usage_provenance'][$direction] ?? 'unknown';
            $metadata['usage_provenance'][$direction] = $versioned && isset($this->tokenUsage[$direction])
                && in_array($provenance, MeasurementProvenance::CATEGORIES, true) ? $provenance : 'unknown';
            $method = $raw['usage_method'][$direction] ?? null;
            $metadata['usage_method'][$direction] = is_string($method) && strlen($method) <= 128 ? $method : null;
        }
        return $metadata;
    }
}
