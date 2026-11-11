<?php

namespace App\Support;

class TranslationQuality
{
    public static function score(mixed $value): ?int
    {
        if (!is_numeric($value) || !is_finite((float) $value) || $value < 0 || $value > 100) {
            return null;
        }

        return (int) round((float) $value);
    }

    public static function describe(array $record): array
    {
        $score = self::score($record['quality_score'] ?? null);
        $review = is_array($record['sidecar']['quality_review'] ?? null) ? $record['sidecar']['quality_review'] : [];
        $status = $review['status'] ?? null;
        $label = $score !== null ? $score.'/100' : match ($status) {
            'unavailable' => 'Review unavailable',
            'not_reviewed' => 'Not reviewed',
            default => 'Review not recorded',
        };
        $eligible = $review['eligible_blocks'] ?? null;
        $scored = $review['scored_blocks'] ?? null;
        $coverage = is_int($eligible) && is_int($scored) && $eligible > 0 && $scored >= 0 && $scored <= $eligible
            ? "$scored of $eligible text sections checked; unchanged or unreadable areas may be excluded" : null;

        return [
            'label' => $label,
            'level' => $score === null ? 'unknown' : ($score < 60 ? 'low' : ($score < 80 ? 'medium' : 'high')),
            'coverage' => $coverage,
            'explanation' => $score === null
                ? match ($review['reason'] ?? null) {
                    'review_disabled' => 'Quality review was disabled for this translation.',
                    'review_failed' => 'The reviewer could not provide a valid score. The translation remains accessible.',
                    'no_eligible_blocks' => 'No translated text was available for this check.',
                    default => 'No review result was retained for this translation.',
                }
                : 'Automated review of the original AI output; not human-verified accuracy. Later edits are not scored.',
        ];
    }
}
