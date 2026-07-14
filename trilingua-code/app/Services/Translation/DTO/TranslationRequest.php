<?php

namespace App\Services\Translation\DTO;

/**
 * DTO for translation requests.
 * 
 * Laravel knows nothing about AI — this is purely a data transfer object
 * that gets sent to the Python AI Engine.
 */
class TranslationRequest
{
    public function __construct(
        public readonly string $text,
        public readonly string $sourceLang,
        public readonly string $targetLang,
    ) {}

    /**
     * Convert to array for JSON serialization.
     */
    public function toArray(): array
    {
        return [
            'text' => $this->text,
            'source_lang' => $this->sourceLang,
            'target_lang' => $this->targetLang,
        ];
    }
}