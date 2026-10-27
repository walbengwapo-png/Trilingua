<?php

namespace App\Support;

use Illuminate\Support\Facades\DB;

/**
 * Evidence-based backfill of translation_blocks.published_text for legacy rows.
 *
 * A row is UNAMBIGUOUS - and therefore safe to populate - only when there is no
 * evidence that the published downloadable file ever diverged from the original
 * AI output:
 *   - it is a document with a downloadable storage_path
 *   - draft_revision = published_revision = 0 (never edited or republished)
 *   - no 'edit' or 'publish' row exists in translation_edit_log
 *   - every block is still 'pending' (never edited)
 *
 * In that case published_text = current_text (which equals ai_translated_text,
 * the text the file was generated from). EVERY other row is left NULL
 * (unknown): the file's contents cannot be reconstructed from block data, so
 * the downloadable file is preserved and the UI shows an honest
 * "published text preview unavailable" state until reconciled. We never fill an
 * unknown published value from a draft merely to make a Final preview render.
 */
class LegacyPublishedTextBackfill
{
    /**
     * History ids whose published block text can be reconstructed unambiguously.
     *
     * @return array<int, int>
     */
    public static function qualifyingHistoryIds(): array
    {
        return DB::table('translation_history as h')
            ->where('h.translation_type', 'document')
            ->whereNotNull('h.storage_path')
            ->where('h.draft_revision', 0)
            ->where('h.published_revision', 0)
            ->whereNotExists(function ($q) {
                $q->selectRaw('1')
                    ->from('translation_edit_log as el')
                    ->whereColumn('el.translation_history_id', 'h.id')
                    ->whereIn('el.action', ['edit', 'publish']);
            })
            ->whereNotExists(function ($q) {
                $q->selectRaw('1')
                    ->from('translation_blocks as b')
                    ->whereColumn('b.translation_history_id', 'h.id')
                    ->where('b.status', '<>', 'pending');
            })
            ->pluck('h.id')
            ->map(fn ($id) => (int) $id)
            ->all();
    }

    /**
     * Apply the backfill. Returns the number of blocks populated.
     */
    public static function apply(): int
    {
        $ids = self::qualifyingHistoryIds();

        if ($ids === []) {
            return 0;
        }

        return DB::table('translation_blocks')
            ->whereIn('translation_history_id', $ids)
            ->where('status', 'pending')
            ->update(['published_text' => DB::raw('current_text')]);
    }
}