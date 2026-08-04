<?php

namespace App\Services;

use App\Models\TranslationBlock;
use App\Models\TranslationHistory;
use App\Support\ReviewStatus;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Persists per-block document translation data into translation_blocks and
 * rolls the aggregate quality score up onto the parent translation_history row.
 *
 * Invariants enforced here:
 *  - ai_translated_text is IMMUTABLE: it is written exactly once at persist
 *    time and never touched by admin edits.
 *  - current_text starts equal to ai_translated_text and is the ONLY field
 *    admin edits may change.
 */
class BlockService
{
    /**
     * Persist the Python-envelope blocks for a completed document translation.
     *
     * Runs inside a transaction so a failure never leaves partial blocks or a
     * quality score that references blocks that don't exist.
     *
     * @param  TranslationHistory $history  The freshly-created history row.
     * @param  array<int, array>  $blocks   From the Python envelope ('blocks').
     * @param  array|null         $sidecar  Full sidecar JSON (regeneration).
     * @return int  Number of blocks persisted.
     */
    public function persistBlocks(TranslationHistory $history, array $blocks, ?array $sidecar = null): int
    {
        if ($blocks === []) {
            return 0;
        }

        $count = DB::transaction(function () use ($history, $blocks, $sidecar) {
            $created = 0;
            $scores = [];

            foreach ($blocks as $index => $block) {
                $sourceText = (string) ($block['source_text'] ?? $block['text'] ?? '');
                $aiText = (string) ($block['ai_translated_text']
                    ?? $block['current_text']
                    ?? $block['text'] ?? '');

                $score = $this->normalizeScore($block['quality_score'] ?? null);
                if ($score !== null) {
                    $scores[] = $score;
                }

                TranslationBlock::create([
                    'translation_history_id' => $history->id,
                    'block_index'            => (int) ($block['block_index'] ?? $index),
                    'block_type'             => (string) ($block['block_type'] ?? $block['type'] ?? 'paragraph'),
                    'source_text'            => $sourceText,
                    'ai_translated_text'     => $aiText,
                    'current_text'           => $aiText,
                    'quality_score'          => $score,
                    'quality_issues'         => $this->normalizeIssues($block['quality_issues'] ?? null),
                    'status'                 => ReviewStatus::PENDING,
                    'created_at'             => now(),
                ]);

                $created++;
            }

            // Roll the aggregate quality score up onto the history row.
            if ($scores !== []) {
                $average = (int) round(array_sum($scores) / count($scores));
                $history->quality_score = $average;
            }

            if ($sidecar !== null) {
                $history->sidecar = $sidecar;
            }

            $history->save();

            return $created;
        });

        Log::info('BlockService: Persisted document translation blocks', [
            'translation_history_id' => $history->id,
            'blocks' => $count,
            'quality_score' => $history->quality_score,
        ]);

        return $count;
    }

    /**
     * Convert a quality score (float|int|string|null) to a nullable int.
     */
    private function normalizeScore(mixed $score): ?int
    {
        if ($score === null || $score === '') {
            return null;
        }
        if (is_numeric($score)) {
            return (int) round((float) $score);
        }
        return null;
    }

    /**
     * Convert quality issues (array|json-string|null) to a plain array.
     */
    private function normalizeIssues(mixed $issues): ?array
    {
        if ($issues === null || $issues === '') {
            return null;
        }
        if (is_array($issues)) {
            return $issues;
        }
        if (is_string($issues)) {
            $decoded = json_decode($issues, true);
            return is_array($decoded) ? $decoded : null;
        }
        return null;
    }
}
