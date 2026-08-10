<?php

namespace App\Services\Admin;

use App\Exceptions\TranslationException;
use App\Models\TranslationBlock;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use App\Support\FlagReason;
use App\Support\ReviewStatus;
use Illuminate\Support\Str;

/**
 * Admin document review orchestration.
 *
 * Handles the full "admin reviews a translation" lifecycle:
 *   - status transitions (pending → verified | edited | flagged)
 *   - append-only audit trail in translation_edit_log
 *   - block-level editing with regeneration ("Save & Regenerate")
 *
 * IMPORTANT immutable-data invariant:
 *   `translation_blocks.ai_translated_text` and
 *   `translation_history.translated_text` are NEVER overwritten in place.
 *   Admin edits only touch `translation_blocks.current_text`, and every
 *   change writes the PREVIOUS value to translation_edit_log first.
 */
class ReviewService
{
    public function __construct(
        private TranslationManager $translationManager,
        private StorageService $storage,
    ) {}

    /**
     * Mark a translation as verified (pending → verified).
     *
     * @param  int  $historyId  translation_history.id
     * @param  int  $adminId    authenticated admin user id
     * @param  string|null  $note  Optional audit note.
     * @return TranslationHistory
     */
    public function verify(int $historyId, int $adminId, ?string $note = null): TranslationHistory
    {
        $history = $this->findHistory($historyId);

        $history->review_status = ReviewStatus::VERIFIED;
        $history->reviewed_by = $adminId;
        $history->reviewed_at = now();
        $history->save();

        $this->log($history->id, null, $adminId, 'verify', null, null, $note);

        return $history;
    }

    /**
     * Flag a translation for follow-up (pending → flagged).
     *
     * @param  int  $historyId
     * @param  int  $adminId
     * @param  string  $reason  One of FlagReason::ALL.
     * @param  string|null  $note  Required context for the flag.
     * @return TranslationHistory
     */
    public function flag(int $historyId, int $adminId, string $reason, ?string $note = null): TranslationHistory
    {
        if (!in_array($reason, FlagReason::ALL, true)) {
            throw new \InvalidArgumentException(
                "Invalid flag reason '{$reason}'. Must be one of: " . implode(', ', FlagReason::ALL)
            );
        }

        $history = $this->findHistory($historyId);

        $history->review_status = ReviewStatus::FLAGGED;
        $history->reviewed_by = $adminId;
        $history->reviewed_at = now();
        $history->flag_reason = $reason;
        $history->flag_note = $note;
        $history->save();

        $this->log($history->id, null, $adminId, 'flag', null, null, $note ?: "Flagged: {$reason}");

        return $history;
    }

    /**
     * Edit a text translation's translated_text (pending/verified/flagged → edited).
     *
     * Implements the same immutable-data + audit invariant as document blocks:
     * the PREVIOUS translated_text is logged to translation_edit_log BEFORE it
     * is overwritten. No batch update of translation_history here.
     *
     * @param  int  $historyId
     * @param  int  $adminId
     * @param  string  $newText
     * @param  string|null  $note
     * @return TranslationHistory
     */
    public function editText(int $historyId, int $adminId, string $newText, ?string $note = null): TranslationHistory
    {
        $history = $this->findHistory($historyId);

        if ($history->translation_type === 'document') {
            throw new \InvalidArgumentException(
                'Text edit action cannot be applied to a document translation.'
            );
        }

        if ($history->translated_text === $newText) {
            return $history;
        }

        $previousText = $history->translated_text;

        // Append-only audit: record the value about to be replaced.
        $this->log($history->id, null, $adminId, 'edit', $previousText, $newText, $note);

        $history->translated_text = $newText;
        $history->review_status = ReviewStatus::EDITED;
        $history->reviewed_by = $adminId;
        $history->reviewed_at = now();
        $history->save();

        return $history;
    }

    /**
     * Mark an entire document translation as verified (pending → verified).
     *
     * The history row is updated first, then every block is cascaded to
     * 'verified' so the block list stays consistent with the document status.
     * A single history-level audit entry is written (no per-block rows).
     *
     * @param  int  $historyId
     * @param  int  $adminId
     * @param  string|null  $note
     * @return TranslationHistory
     */
    public function verifyDocument(int $historyId, int $adminId, ?string $note = null): TranslationHistory
    {
        $history = $this->verify($historyId, $adminId, $note);

        $history->blocks()->update([
            'status' => ReviewStatus::VERIFIED,
            'edited_by' => $adminId,
            'edited_at' => now(),
            'flag_reason' => null,
            'flag_note' => null,
        ]);

        return $history;
    }

    /**
     * Edit a single document block's current_text (→ edited).
     *
     * ai_translated_text is NEVER touched. The PREVIOUS current_text is logged
     * to translation_edit_log before being overwritten. When a block actually
     * changes, the parent document's review_status is also flipped to 'edited'
     * so the document-level status stays consistent for the submitting user.
     *
     * @param  int  $historyId
     * @param  int  $blockId
     * @param  int  $adminId
     * @param  string  $newText
     * @param  string|null  $note
     * @return TranslationBlock
     */
    public function updateBlock(int $historyId, int $blockId, int $adminId, string $newText, ?string $note = null): TranslationBlock
    {
        $block = $this->findBlock($historyId, $blockId);

        if ($block->current_text === $newText) {
            return $block;
        }

        $previousText = $block->current_text;

        $this->log($historyId, $block->id, $adminId, 'edit', $previousText, $newText, $note);

        $block->current_text = $newText;
        $block->status = ReviewStatus::EDITED;
        $block->edited_by = $adminId;
        $block->edited_at = now();
        $block->save();

        // Propagate the change up to the document row so users see 'edited'.
        $history = $this->findHistory($historyId);
        $history->review_status = ReviewStatus::EDITED;
        $history->reviewed_by = $adminId;
        $history->reviewed_at = now();
        $history->save();

        return $block;
    }

    /**
     * Persist admin edits for several blocks at once, keyed by block id
     * ({block_id: new_text}). Blocks outside this history, or whose text is
     * unchanged, are skipped — no audit row is written for a no-op. When any
     * block actually changes, the history row is flipped to 'edited'.
     *
     * Same invariant as updateBlock(): the PREVIOUS current_text is audited
     * first and ai_translated_text is never touched.
     *
     * @param  int  $historyId
     * @param  int  $adminId
     * @param  array<int|string, string>  $blockIdToText  {block_id: new_text}
     * @param  string|null  $note  Optional audit note.
     * @return int  Number of blocks actually changed.
     */
    public function applyBlockEdits(
        int $historyId,
        int $adminId,
        array $blockIdToText,
        ?string $note = null,
    ): int {
        $history = $this->findHistory($historyId);

        $ids = array_values(array_filter(
            array_map('intval', array_keys($blockIdToText)),
            fn ($id) => $id > 0,
        ));

        $blocks = $ids === []
            ? collect()
            : TranslationBlock::where('translation_history_id', $historyId)
                ->whereIn('id', $ids)
                ->get()
                ->keyBy('id');

        $edited = 0;
        foreach ($blockIdToText as $blockId => $newText) {
            $block = $blocks->get((int) $blockId);
            if (!$block) {
                continue;
            }
            $newText = (string) $newText;
            if ($block->current_text === $newText) {
                continue;
            }

            $this->log($history->id, $block->id, $adminId, 'edit', $block->current_text, $newText, $note);

            $block->current_text = $newText;
            $block->status = ReviewStatus::EDITED;
            $block->edited_by = $adminId;
            $block->edited_at = now();
            $block->save();

            $edited++;
        }

        if ($edited > 0) {
            $history->review_status = ReviewStatus::EDITED;
            $history->reviewed_by = $adminId;
            $history->reviewed_at = now();
            $history->save();
        }

        return $edited;
    }

    /**
     * Mark an entire document translation as flagged (pending → flagged).
     *
     * The history row is updated first, then every block is cascaded to
     * 'flagged' with the same reason/note so the block list stays consistent
     * with the document status. A single history-level audit entry is written.
     *
     * @param  int  $historyId
     * @param  int  $adminId
     * @param  string  $reason
     * @param  string|null  $note
     * @return TranslationHistory
     */
    public function flagDocument(int $historyId, int $adminId, string $reason, ?string $note = null): TranslationHistory
    {
        if (!in_array($reason, FlagReason::ALL, true)) {
            throw new \InvalidArgumentException(
                "Invalid flag reason '{$reason}'. Must be one of: " . implode(', ', FlagReason::ALL)
            );
        }

        $history = $this->flag($historyId, $adminId, $reason, $note);

        $history->blocks()->update([
            'status' => ReviewStatus::FLAGGED,
            'flag_reason' => $reason,
            'flag_note' => $note,
            'edited_by' => $adminId,
            'edited_at' => now(),
        ]);

        return $history;
    }

    /**
     * Find a block scoped to a history row, or throw.
     */
    private function findBlock(int $historyId, int $blockId): TranslationBlock
    {
        $block = TranslationBlock::where('translation_history_id', $historyId)
            ->where('id', $blockId)
            ->first();

        if (!$block) {
            throw new \InvalidArgumentException(
                "Block {$blockId} not found on translation history {$historyId}."
            );
        }
        return $block;
    }

    /**
     * Apply admin edits to one or more blocks and re-render the document.
     *
     * Flow:
     *   1. For every {block_index: new_text} override, log the PREVIOUS
     *      current_text to translation_edit_log, then update current_text
     *      and mark the block edited.
     *   2. Download the ORIGINAL file from Supabase.
     *   3. Rebuild a regeneration sidecar from the persisted blocks
     *      (current state becomes the reconstruction source of truth).
     *   4. Call TranslationManager::regenerateDocument() synchronously —
     *      reconstruction only, NO re-translation.
     *   5. Upload the new version via StorageService and update the history row.
     *
     * @param  int  $historyId
     * @param  int  $adminId
     * @param  array<int, string>  $overrides  {block_index: new_text}
     * @param  string|null  $note  Optional audit note.
     * @return array{
     *     history: TranslationHistory,
     *     storage_path: string,
     *     download_filename: string,
     *     signed_url: string,
     *     edited_blocks: int,
     * }
     * @throws TranslationException  When the document cannot be regenerated.
     */
    public function saveAndRegenerate(
        int $historyId,
        int $adminId,
        array $overrides,
        ?string $note = null,
    ): array {
        $history = $this->findHistory($historyId);

        if ($history->translation_type !== 'document') {
            throw new TranslationException('Only document translations can be regenerated.');
        }
        if (blank($history->original_storage_path)) {
            throw new TranslationException(
                'The original file is not available in storage, so this document cannot be regenerated.'
            );
        }

        $history->load('blocks');
        $blocksByIndex = $history->blocks->keyBy('block_index');

        // ── 1. Apply edits: log previous value FIRST, then update current_text.
        $editedBlocks = 0;
        $regenerationOverrides = [];
        foreach ($overrides as $blockIndex => $newText) {
            /** @var TranslationBlock|null $block */
            $block = $blocksByIndex->get((int) $blockIndex);
            if (!$block) {
                continue;
            }
            $newText = (string) $newText;
            if ($block->current_text === $newText) {
                // Unchanged — still include it so the regenerated doc uses the
                // current state of every block.
                $regenerationOverrides[(int) $blockIndex] = $block->current_text;
                continue;
            }

            $previousText = $block->current_text;

            // Append-only audit: record the value about to be replaced.
            $this->log(
                $history->id,
                $block->id,
                $adminId,
                'edit',
                $previousText,
                $newText,
                $note,
            );

            $block->current_text = $newText;
            $block->status = ReviewStatus::EDITED;
            $block->edited_by = $adminId;
            $block->edited_at = now();
            $block->save();

            $regenerationOverrides[(int) $blockIndex] = $newText;
            $editedBlocks++;
        }

        if ($editedBlocks > 0) {
            $history->review_status = ReviewStatus::EDITED;
            $history->reviewed_by = $adminId;
            $history->reviewed_at = now();
        }
        $history->save();

        // ── 2. Download the original source file from Supabase.
        $originalBytes = $this->storage->downloadFile($history->original_storage_path);

        // ── 3. Rebuild a regeneration sidecar reflecting the CURRENT state.
        $sidecar = $history->sidecar ?? $this->buildFallbackSidecar($history);
        $sidecar = $this->overlayCurrentStateOnSidecar($sidecar, $history);

        // ── 4. Synchronous reconstruction-only regeneration.
        $result = $this->translationManager->regenerateDocument(
            originalBytes: $originalBytes,
            originalName: $history->original_filename,
            sidecar: $sidecar,
            overrides: $regenerationOverrides,
            sourceLang: $history->source_language ?? $sidecar['source_lang'] ?? '',
            targetLang: $history->target_language ?? $sidecar['target_lang'] ?? '',
            pdfColumnMode: $sidecar['pdf_column_mode'] ?? 'auto',
        );

        // ── 5. Upload the new version and update the history row.
        $tempPath = storage_path('app/temp/' . Str::uuid() . '_' . $result['download_filename']);
        if (!is_dir(dirname($tempPath))) {
            mkdir(dirname($tempPath), 0755, true);
        }
        file_put_contents($tempPath, $result['body']);

        try {
            $storageResult = $this->storage->uploadFile(
                $tempPath,
                $history->user_id . '/' . basename($tempPath)
            );
        } finally {
            @unlink($tempPath);
        }

        $history->storage_path = $storageResult['storage_path'];
        $history->translated_filename = $result['download_filename'];
        $history->signed_url_expires_at = $storageResult['signed_url_expires_at'];
        $history->save();

        return [
            'history' => $history,
            'storage_path' => $storageResult['storage_path'],
            'download_filename' => $result['download_filename'],
            'signed_url' => $storageResult['signed_url'],
            'edited_blocks' => $editedBlocks,
        ];
    }

    /**
     * Build a minimal sidecar when the stored sidecar is missing (legacy rows).
     *
     * @return array<string, mixed>
     */
    private function buildFallbackSidecar(TranslationHistory $history): array
    {
        $ext = strtolower('.' . pathinfo((string) $history->original_filename, PATHINFO_EXTENSION));
        $outExt = config('translation.extension_map.' . ltrim($ext, '.'), $ext ?: '.txt');
        return [
            'version' => 2,
            'format' => '.' . ltrim($outExt, '.'),
            'source_lang' => $history->source_language ?? '',
            'target_lang' => $history->target_language ?? '',
            'pdf_column_mode' => 'auto',
            'blocks' => [],
        ];
    }

    /**
     * Overlay the persisted block current_text onto the sidecar's blocks so
     * reconstruction uses the current (possibly edited) state.
     *
     * @param  array<string, mixed>  $sidecar
     * @return array<string, mixed>
     */
    private function overlayCurrentStateOnSidecar(array $sidecar, TranslationHistory $history): array
    {
        $sidecarBlocks = [];
        foreach ($sidecar['blocks'] ?? [] as $block) {
            $sidecarBlocks[(int) ($block['block_index'] ?? -1)] = $block;
        }

        foreach ($history->blocks as $block) {
            $key = (int) $block->block_index;
            $current = $sidecarBlocks[$key] ?? ['block_index' => $key];
            $current['text'] = $block->current_text;
            $current['current_text'] = $block->current_text;
            $current['ai_translated_text'] = $block->ai_translated_text;
            $sidecarBlocks[$key] = $current;
        }

        $sidecar['blocks'] = array_values($sidecarBlocks);
        return $sidecar;
    }

    /**
     * Append an audit entry to translation_edit_log.
     */
    private function log(
        int $historyId,
        ?int $blockId,
        int $adminId,
        string $action,
        ?string $previousText,
        ?string $newText,
        ?string $note,
    ): void {
        TranslationEditLog::create([
            'translation_history_id' => $historyId,
            'translation_block_id'   => $blockId,
            'admin_id'               => $adminId,
            'action'                 => $action,
            'previous_text'          => $previousText,
            'new_text'               => $newText,
            'note'                   => $note,
            'created_at'             => now(),
        ]);
    }

    /**
     * Find a translation history record or throw.
     */
    private function findHistory(int $historyId): TranslationHistory
    {
        $history = TranslationHistory::find($historyId);
        if (!$history) {
            throw new \InvalidArgumentException("Translation history record {$historyId} not found.");
        }
        return $history;
    }
}
