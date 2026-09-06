<?php

namespace App\Services\Translation\DTO;

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
        public readonly ?int $qualityScore = null,
        public readonly array $qualityIssues = [],
        public readonly string $mode = 'balanced',
        public readonly array $warnings = [],
        public readonly bool $success = true,
        public readonly string $errorMessage = '',
    ) {}

    /**
     * Create from Python API response array.
     */
    public static function fromArray(array $data): self
    {
        return new self(
            translatedText: $data['translated'] ?? $data['translated_text'] ?? '',
            provider: $data['provider'] ?? '',
            model: $data['model'] ?? '',
            tokenUsage: $data['token_usage'] ?? [],
            executionTimeMs: $data['execution_time_ms'] ?? 0.0,
            qualityScore: isset($data['quality_score']) ? (int) $data['quality_score'] : null,
            qualityIssues: $data['quality_issues'] ?? [],
            mode: $data['mode'] ?? 'balanced',
            warnings: $data['warnings'] ?? [],
            success: $data['success'] ?? true,
            errorMessage: $data['error_message'] ?? $data['error'] ?? '',
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
            'quality_score' => $this->qualityScore,
            'quality_issues' => $this->qualityIssues,
            'mode' => $this->mode,
            'warnings' => $this->warnings,
            'success' => $this->success,
        ];
    }
}
