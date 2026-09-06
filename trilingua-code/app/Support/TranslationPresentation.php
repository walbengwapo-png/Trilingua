<?php

namespace App\Support;

use Carbon\Carbon;
use Carbon\CarbonInterface;

/**
 * A single, intentionally small view-model for a translation record.
 *
 * Keeping display decisions here prevents pages from disagreeing about an
 * item's lifecycle (translation processing) versus its review state, or from
 * calling a completed output an "original" just because it has no parent.
 */
final class TranslationPresentation
{
    /** @param array<string, mixed>|object $record */
    public static function for(array|object $record, ?array $preferences = null): array
    {
        $value = static fn (string $key, mixed $default = null): mixed => is_array($record)
            ? ($record[$key] ?? $default)
            : ($record->{$key} ?? $default);

        $status = strtolower((string) $value('status', 'completed'));
        $review = strtolower((string) $value('review_status', ReviewStatus::PENDING));
        $isDocument = $value('translation_type', 'document') === 'document';
        $hasOutput = filled($value('translated_filename')) || filled($value('storage_path'));
        $isReviewedFinal = in_array($review, [ReviewStatus::VERIFIED, ReviewStatus::EDITED], true);

        $asset = match (true) {
            ! $isDocument => ['key' => 'text_translation', 'label' => 'Text translation'],
            $isReviewedFinal => ['key' => 'reviewed_final', 'label' => 'Reviewed final'],
            $hasOutput || filled($value('parent_document_id')) => ['key' => 'translation_output', 'label' => 'Translation output'],
            default => ['key' => 'original', 'label' => 'Original'],
        };

        $lifecycleLabel = match ($status) {
            'queued' => 'Translation queued',
            'processing', 'in_progress' => 'Translation in progress',
            'failed' => 'Translation failed',
            default => 'Translation complete',
        };

        $reviewLabel = match ($review) {
            ReviewStatus::VERIFIED => 'Review verified',
            ReviewStatus::EDITED => 'Review edited',
            ReviewStatus::FLAGGED => 'Review flagged',
            default => 'Review pending',
        };

        $score = $value('quality_score');
        $quality = self::quality($score === null ? null : (int) $score);
        $name = $isDocument
            ? ($value('translated_filename') ?: $value('original_filename') ?: 'Untitled document')
            : self::textTitle((string) $value('source_text', ''), (string) $value('source_language', ''), (string) $value('target_language', ''));

        return [
            'asset' => $asset,
            'title' => $name,
            'file_icon' => self::fileIcon((string) ($value('translated_filename') ?: $value('original_filename') ?: '')),
            'lifecycle' => [
                'status' => $status,
                'review_status' => $review,
                'label' => $lifecycleLabel . ' · ' . $reviewLabel,
                'translation_label' => $lifecycleLabel,
                'review_label' => $reviewLabel,
            ],
            'quality' => $quality,
            'version' => max(1, (int) ($value('current_version_number') ?: optional($value('currentVersion'))->version ?: 1)),
            'date' => self::date($value('created_at'), $preferences ?? []),
        ];
    }

    public static function quality(?int $score): array
    {
        if ($score === null) {
            return ['score' => null, 'label' => 'Not scored', 'risk' => 'unknown', 'text' => 'Not scored'];
        }

        $score = max(0, min(100, $score));
        // Scores are confidence/quality: a lower score needs more attention.
        $risk = $score < 60 ? 'high' : ($score < 80 ? 'medium' : 'low');
        $label = match ($risk) {
            'high' => 'High risk',
            'medium' => 'Needs review',
            default => 'Low risk',
        };

        return ['score' => $score, 'label' => $label, 'risk' => $risk, 'text' => "{$score}/100 · {$label}"];
    }

    /** @param array<string, mixed> $preferences */
    public static function date(mixed $value, array $preferences = []): array
    {
        if (! $value) {
            return ['relative' => '—', 'exact' => '—'];
        }

        $timezone = $preferences['timezone'] ?? config('app.timezone', 'UTC');
        $format = $preferences['date_format'] ?? 'M j, Y g:i A T';
        try {
            $date = $value instanceof CarbonInterface ? $value : Carbon::parse($value);
            $date = $date->copy()->timezone($timezone);

            $exact = $date->format($format);
            // PHP's time-zone database still labels Asia/Manila as PST in
            // some builds, which is easily confused with Pacific Standard
            // Time. The product is explicitly Philippines-facing, so present
            // its unambiguous, locally used abbreviation instead.
            if ($timezone === 'Asia/Manila') {
                $exact = preg_replace('/\\bPST\\b/', 'PHT', $exact) ?? $exact;
            }

            return ['relative' => $date->diffForHumans(), 'exact' => $exact];
        } catch (\Throwable) {
            return ['relative' => '—', 'exact' => '—'];
        }
    }

    private static function fileIcon(string $filename): string
    {
        return match (strtolower(pathinfo($filename, PATHINFO_EXTENSION))) {
            'pdf' => 'pdf', 'doc', 'docx', 'odt', 'rtf' => 'document',
            'xls', 'xlsx', 'csv' => 'spreadsheet', 'ppt', 'pptx' => 'slides',
            'txt', 'md' => 'text', default => 'file',
        };
    }

    private static function textTitle(string $source, string $from, string $to): string
    {
        $pair = trim($from . ' → ' . $to, ' →');
        $snippet = trim(preg_replace('/\s+/', ' ', $source) ?: '');

        return $snippet !== '' ? str($snippet)->limit(56) . ($pair ? " ({$pair})" : '') : ($pair ? "Text translation ({$pair})" : 'Text translation');
    }
}
