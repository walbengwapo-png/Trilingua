<?php

namespace App\Services\Admin;

use App\Exceptions\ReviewConflictException;
use App\Exceptions\TranslationException;
use App\Models\StorageCleanupOutbox;
use App\Models\TranslationBlock;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Services\StorageCleanupService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use App\Support\FlagReason;
use App\Support\ReviewStatus;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

/**
 * Admin document review orchestration.
 *
 * Handles the full "admin reviews a translation" lifecycle:
 *   - status transitions (pending -> verified | edited | flagged)
 *   - append-only audit trail in translation_edit_log
 *   - block-level editing with regeneration ("Save & Regenerate")
 *
 * IMPORTANT immutable-data invariant:
 *   `translation_blocks.ai_translated_text` and
 *   `translation_history.translated_text` are NEVER overwritten in place.
 *   Admin edits only touch `translation_blocks.current_text`, and every
 *   change writes the PREVIOUS value to translation_edit_log first.
 *
 * CONCURRENCY invariant: every logically indivisible change runs inside one
 * short DB transaction; draft edits and publications verify an expected
 * draft_revision / storage pointer and refuse (ReviewConflictException) rather
 * than overwrite a newer admin's text. No DB transaction is ever held open
 * across a Python or storage call.
 */
class ReviewService
{
    public function __construct(
        private TranslationManager $translationManager,
        private StorageService $storage,
        private StorageCleanupService $cleanup,
    ) {}

    /**
     * Mark a translation as verified (pending -> verified).
     *
     * @param  int  $historyId  translation_history.id
     * @param  int  $adminId    authenticated admin user id
     * @param  string|null  $note  Optional audit note.
     * @return TranslationHistory
     */
    public function verify(int $historyId, int $adminId, ?string $note = null): TranslationHistory
    {
        return DB::transaction(function () use ($historyId, $adminId, $note) {
            $history = $this->findHistory($historyId);

            $history->review_status = ReviewStatus::VERIFIED;
            $history->reviewed_by = $adminId;
            $history->reviewed_at = now();
            $history->save();

            $this->log($history->id, null, $adminId, 'verify', null, null, $note);

            return $history;
        });
    }

    /**
     * Flag a translation for follow-up (pending -> flagged).
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

        return DB::transaction(function () use ($historyId, $adminId, $reason, $note) {
            $history = $this->findHistory($historyId);

            $history->review_status = ReviewStatus::FLAGGED;
            $history->reviewed_by = $adminId;
            $history->reviewed_at = now();
            $history->flag_reason = $reason;
            $history->flag_note = $note;
            $history->save();

            $this->log($history->id, null, $adminId, 'flag', null, null, $note ?: "Flagged: {$reason}");

            return $history;
        });
    }

    /**
     * Edit a text translation's translated_text (pending/verified/flagged -> edited).
     *
     * Implements the same immutable-data + audit invariant as document blocks:
     * the PREVIOUS translated_text is logged to translation_edit_log BEFORE it
     * is overwritten. The edit and its audit row commit atomically.
     *
     * @param  int  $historyId
     * @param  int  $adminId
     * @param  string  $newText
     * @param  string|null  $note
     * @return TranslationHistory
     */
    public function editText(int $historyId, int $adminId, string $newText, ?string $note = null): TranslationHistory
    {
        return DB::transaction(function () use ($historyId, $adminId, $newText, $note) {
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
        });
    }

    /**
     * Mark an entire document translation as verified (pending -> verified).
     *
     * The history row is locked, verified, and its block cascade + single audit
     * row commit in ONE transaction, so a concurrent edit cannot slip in and a
     * failed audit write rolls the status change back.
     *
     * @param  int  $historyId
     * @param  int  $adminId
     * @param  string|null  $note
     * @return TranslationHistory
     */
    public function verifyDocument(int $historyId, int $adminId, ?string $note = null): TranslationHistory
    {
        return DB::transaction(function () use ($historyId, $adminId, $note) {
            $history = TranslationHistory::whereKey($historyId)->lockForUpdate()->firstOrFail();

            // The published file is what a verification vouches for. Approved
            // contract: a document carrying edits the downloadable file does not
            // contain yet must be published (Save & Regenerate) before Verify.
            if ($history->hasUnpublishedEdits()) {
                throw new TranslationException(
                    'This document has edits saved as a draft that are not in the downloadable file yet. ' .
                    'Run Save & Regenerate to publish them before verifying.'
                );
            }

            $history->review_status = ReviewStatus::VERIFIED;
            $history->reviewed_by = $adminId;
            $history->reviewed_at = now();
            $history->save();

            $this->log($history->id, null, $adminId, 'verify', null, null, $note);

            $history->blocks()->update([
                'status' => ReviewStatus::VERIFIED,
                'edited_by' => $adminId,
                'edited_at' => now(),
                'flag_reason' => null,
                'flag_note' => null,
            ]);

            return $history;
        });
    }

    /**
     * Edit a single document block's current_text (-> edited).
     *
     * Delegates to applyBlockEdits() so single-block and multi-block edits share
     * ONE implementation of the audit/immutability rule (and of the draft
     * revision bump). ai_translated_text is NEVER touched and the PREVIOUS
     * current_text is always logged first.
     *
     * @param  int  $historyId
     * @param  int  $blockId
     * @param  int  $adminId
     * @param  string  $newText
     * @param  string|null  $note
     * @param  int|null  $expectedDraftRevision  Stale-submission guard; when set,
     *                                           reject a request based on an old
     *                                           draft revision with a 409 conflict.
     * @return TranslationBlock
     */
    public function updateBlock(
        int $historyId,
        int $blockId,
        int $adminId,
        string $newText,
        ?string $note = null,
        ?int $expectedDraftRevision = null,
    ): TranslationBlock {
        $this->applyBlockEdits($historyId, $adminId, [$blockId => $newText], $note, $expectedDraftRevision);

        return $this->findBlock($historyId, $blockId);
    }

    /**
     * Persist admin edits for several blocks at once, keyed by block id
     * ({block_id: new_text}). Blocks outside this history, or whose text is
     * unchanged, are skipped - no audit row is written for a no-op. When any
     * block actually changes, the history row is flipped to 'edited'.
     *
     * Same invariant as updateBlock(): the PREVIOUS current_text is audited
     * first and ai_translated_text is never touched. Every persisted edit bumps
     * draft_revision so the record's "published file contains the edits" state
     * (published_revision) can never drift into a false "up to date".
     *
     * The history row is locked for the duration of the whole batch and the
     * batch + audit + revision bump commit in ONE transaction.
     *
     * @param  int  $historyId
     * @param  int  $adminId
     * @param  array<int|string, string>  $blockIdToText  {block_id: new_text}
     * @param  string|null  $note  Optional audit note.
     * @param  int|null  $expectedDraftRevision  Stale-submission guard.
     * @return int  Number of blocks actually changed.
     */
    public function applyBlockEdits(
        int $historyId,
        int $adminId,
        array $blockIdToText,
        ?string $note = null,
        ?int $expectedDraftRevision = null,
    ): int {
        $ids = array_values(array_filter(
            array_map('intval', array_keys($blockIdToText)),
            fn ($id) => $id > 0,
        ));

        return DB::transaction(function () use ($historyId, $adminId, $blockIdToText, $note, $ids, $expectedDraftRevision) {
            $history = TranslationHistory::whereKey($historyId)->lockForUpdate()->firstOrFail();

            // Never overwrite a newer admin's draft text.
            $this->assertExpectedRevision($history, $expectedDraftRevision);

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
                $history->draft_revision = (int) $history->draft_revision + $edited;
                $history->save();
            }

            return $edited;
        });
    }

    /**
     * Mark an entire document translation as flagged (pending -> flagged).
     *
     * The history row, its audit entry, and the block cascade commit in one
     * transaction.
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

        return DB::transaction(function () use ($historyId, $adminId, $reason, $note) {
            $history = $this->findHistory($historyId);

            $history->review_status = ReviewStatus::FLAGGED;
            $history->reviewed_by = $adminId;
            $history->reviewed_at = now();
            $history->flag_reason = $reason;
            $history->flag_note = $note;
            $history->save();

            $this->log($history->id, null, $adminId, 'flag', null, null, $note ?: "Flagged: {$reason}");

            $history->blocks()->update([
                'status' => ReviewStatus::FLAGGED,
                'flag_reason' => $reason,
                'flag_note' => $note,
                'edited_by' => $adminId,
                'edited_at' => now(),
            ]);

            return $history;
        });
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
     * Publish the current block draft to a new downloadable file (Save & Regenerate).
     *
     * This is the ONLY operation that makes draft text visible in a downloadable
     * file. Flow:
     *   1. Persist and audit posted edits ({block_id: new_text} = draft_revision)
     *      atomically, protected by the stale expected_draft_revision guard.
     *   2. Take a consistent snapshot of EVERY block's current_text (index-keyed)
     *      as the reconstruction source of truth.
     *   3. Read the ORIGINAL from the recorded original_storage_backend.
     *   4. Rebuild the sidecar overlaying the current block state.
     *   5. Regenerate via Python: reconstruction only, NO re-translation.
     *   6. Register a durable publish-candidate, then upload to a NEW unique key
     *      via uploadWithFallback, and VERIFY the object is readable.
     *   7. Atomically commit the pointer, published_revision, published_text
     *      snapshot, and a 'publish' audit row, and clear the candidate - ONLY
     *      inside the same transaction, so a surviving candidate row implies the
     *      object was never committed and may be reclaimed.
     *   8. Record the superseded object for durable cleanup (never leave live
     *      data unreachable; deletion re-checks live references at run time).
     *
     * No DB transaction is held open during regeneration, upload, or storage
     * read-back: all of those happen between step 1 and step 7.
     *
     * @param  int  $historyId
     * @param  int  $adminId
     * @param  array<int|string, string>  $blockIdToText  {block_id: new_text}
     * @param  string|null  $note  Optional audit note.
     * @param  int|null  $expectedDraftRevision  Stale draft-revision guard.
     * @param  string|null  $expectedStoragePath  Stale file-pointer guard.
     * @return array{
     *     history: TranslationHistory,
     *     storage_path: string,
     *     storage_backend: string,
     *     download_filename: string,
     *     signed_url: ?string,
     *     edited_blocks: int,
     *     published: bool,
     *     draft: bool,
     * }
     * @throws TranslationException   If regeneration or commit fails.
     * @throws ReviewConflictException If the draft revision or pointer moved.
     */
    public function saveAndRegenerate(
        int $historyId,
        int $adminId,
        array $blockIdToText,
        ?string $note = null,
        ?int $expectedDraftRevision = null,
        ?string $expectedStoragePath = null,
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

        // -- 1. Persist posted edits through the audited path (single source of truth).
        $editedBlocks = $this->applyBlockEdits($history->id, $adminId, $blockIdToText, $note, $expectedDraftRevision);

        // Re-load so the publish instance reflects the edits applied above
        // (draft_revision bump, review_status flip) and is not stale.
        $history = $this->findHistory($historyId);

        // -- 2. Consistent snapshot of the current draft state.
        $history->load('blocks');
        $snapshotByIndex = [];
        $overrides = [];
        foreach ($history->blocks as $block) {
            $key = (int) $block->block_index;
            $snapshotByIndex[$key] = $block->current_text;
            $overrides[$key] = $block->current_text;
        }

        // Draft revision AFTER our edits - the value the publish transaction must
        // still see unchanged (guards against a third admin editing meanwhile).
        $draftAtSnapshot = (int) $history->draft_revision;

        // -- 3. Read the ORIGINAL from the backend it was stored on.
        $originalBackend = $history->original_storage_backend ?: StorageService::BACKEND_SUPABASE;
        $originalBytes = $this->storage->read($originalBackend, $history->original_storage_path);

        // -- 4. Rebuild the sidecar reflecting the CURRENT state.
        $sidecar = $history->sidecar ?? $this->buildFallbackSidecar($history);
        $sidecar = $this->overlayCurrentStateOnSidecar($sidecar, $history);

        // -- 5. Synchronous reconstruction-only regeneration (no DB transaction open).
        $result = $this->translationManager->regenerateDocument(
            originalBytes: $originalBytes,
            originalName: $history->original_filename,
            sidecar: $sidecar,
            overrides: $overrides,
            sourceLang: $history->source_language ?? $sidecar['source_lang'] ?? '',
            targetLang: $history->target_language ?? $sidecar['target_lang'] ?? '',
            pdfColumnMode: $sidecar['pdf_column_mode'] ?? 'auto',
        );

        // -- 6. Upload durably to a NEW unique key and verify readability.
        $outExt = strtolower((string) pathinfo($result['download_filename'], PATHINFO_EXTENSION));
        $outExt = ($outExt === '' || strlen($outExt) > 10 || !preg_match('/^[a-z0-9]+$/', $outExt)) ? 'bin' : $outExt;
        $storageKey = $history->user_id . '/translations/' . (string) Str::uuid() . '.' . $outExt;

        // Durable publish-candidate BEFORE upload closes the crash window: if the
        // process dies after the object is written but before the commit, the
        // candidate row survives and the reclaimer removes the orphan. The commit
        // deletes the candidate row atomically, so any surviving candidate is
        // unambiguously never-committed and safe to reclaim.
        $this->cleanup->recordPublishCandidate(StorageService::BACKEND_SUPABASE, $storageKey, $historyId);

        $tempPath = storage_path('app/temp/' . Str::uuid() . '_' . $result['download_filename']);
        if (!is_dir(dirname($tempPath))) {
            mkdir(dirname($tempPath), 0755, true);
        }
        file_put_contents($tempPath, $result['body']);

        try {
            $storageResult = $this->storage->uploadWithFallback(
                $tempPath,
                $storageKey
            );
        } finally {
            @unlink($tempPath);
        }

        // Durably cover a local-fallback object too (the pre-upload candidate used
        // the intended primary backend).
        if ($storageResult['backend'] === StorageService::BACKEND_LOCAL) {
            $this->cleanup->recordPublishCandidate(StorageService::BACKEND_LOCAL, $storageKey, $historyId);
        }

        try {
            $this->storage->read($storageResult['backend'], $storageResult['storage_path']);
        } catch (\Throwable $e) {
            $this->cleanupUploadedObject($storageResult['backend'], $storageResult['storage_path']);
            throw new TranslationException(
                'The regenerated file could not be read back from storage, so the previous version remains published.',
                0,
                $e
            );
        }

        // -- 7. Commit pointer + published revision + published block snapshot +
        //        publish audit + candidate clear in ONE transaction.
        $previousBackend = $history->storage_backend ?: StorageService::BACKEND_SUPABASE;
        $previousPath = $history->storage_path;
        $newBackend = $storageResult['backend'];
        $newPath = $storageResult['storage_path'];

        try {
            $committed = DB::transaction(function () use (
                $historyId,
                $adminId,
                $snapshotByIndex,
                $draftAtSnapshot,
                $expectedDraftRevision,
                $expectedStoragePath,
                $storageKey,
                $newBackend,
                $newPath,
                $result,
                $storageResult,
                $note,
            ) {
                $history = TranslationHistory::whereKey($historyId)->lockForUpdate()->firstOrFail();

                // Re-check stale submission at the database write. The draft revision
                // must still equal the post-edit snapshot (a further change means
                // another admin edited while we regenerated) and the published
                // pointer must still be the one the rendered page carried.
                $this->assertExpectedStoragePath($history, $expectedStoragePath);
                if ((int) $history->draft_revision !== $draftAtSnapshot) {
                    throw new ReviewConflictException(
                        'The document was edited while it was regenerating. Reload to see the latest version before publishing.'
                    );
                }

                // Guard against a block-level race: the snapshot we sent to Python
                // must still equal the persisted blocks, or we must not publish.
                $lockedBlocks = TranslationBlock::where('translation_history_id', $historyId)
                    ->lockForUpdate()
                    ->get()
                    ->keyBy('block_index');
                foreach ($snapshotByIndex as $index => $text) {
                    $block = $lockedBlocks->get($index);
                    if ($block === null || $block->current_text !== $text) {
                        throw new ReviewConflictException(
                            'A block changed while the document was regenerating. Reload to see the latest version before publishing.'
                        );
                    }
                }

                $history->storage_path = $newPath;
                $history->storage_backend = $newBackend;
                $history->translated_filename = $result['download_filename'];
                $history->signed_url_expires_at = $storageResult['signed_url_expires_at'];
                $history->reviewed_by = $adminId;
                $history->reviewed_at = now();
                $history->published_revision = (int) $history->draft_revision;
                $history->save();

                // Persist the published block snapshot for every block (draft stays
                // in current_text; ai_translated_text stays immutable).
                foreach ($lockedBlocks as $block) {
                    $block->published_text = $block->current_text;
                    $block->save();
                }

                $this->log($history->id, null, $adminId, 'publish', null, null, $note ?: 'Published regenerated document.');

                // The object is now live/referenced: clear the candidate so the
                // reclaimer never deletes a published file.
                $this->cleanup->markCandidatesCommitted([[$newBackend, $newPath]]);

                return $history;
            });
        } catch (\Throwable $e) {
            // Leave the candidate pending (or clean immediately) so the object is
            // never orphaned silently; the previous published file stays intact.
            $this->cleanupUploadedObject($newBackend, $newPath);
            if ($e instanceof ReviewConflictException) {
                throw $e;
            }
            throw new TranslationException(
                'The new version could not be committed; the previous file remains downloadable.',
                0,
                $e
            );
        }

        // -- 8. Superseded object: durable cleanup intent. The reclaimer and
        //        processPending re-check live references immediately before delete.
        if ($previousPath && $previousPath !== $newPath) {
            $this->cleanup->recordPending($previousBackend, $previousPath, $historyId);
        }

        return [
            'history' => $committed,
            'storage_path' => $newPath,
            'storage_backend' => $newBackend,
            'download_filename' => $result['download_filename'],
            'signed_url' => $storageResult['signed_url'] ?? null,
            'edited_blocks' => $editedBlocks,
            'published' => true,
            'draft' => $committed->hasUnpublishedEdits(),
        ];
    }

    /**
     * Reject a write whose expected draft revision does not match the current
     * row (after the row lock is taken).
     */
    private function assertExpectedRevision(TranslationHistory $history, ?int $expected): void
    {
        if ($expected !== null && (int) $history->draft_revision !== $expected) {
            throw new ReviewConflictException(
                'This document was changed by another admin. Reload to see the latest version before editing.'
            );
        }
    }

    /**
     * Reject a publication whose expected storage pointer does not match the
     * currently published file pointer.
     */
    private function assertExpectedStoragePath(TranslationHistory $history, ?string $expected): void
    {
        if ($expected !== null && (string) $history->storage_path !== $expected) {
            throw new ReviewConflictException(
                'The document was republished by another admin. Reload to see the latest version.'
            );
        }
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

        // Preserve document order: reconstruction must see blocks in
        // block_index order, not insertion order.
        ksort($sidecarBlocks, SORT_NUMERIC);
        $sidecar['blocks'] = array_values($sidecarBlocks);
        return $sidecar;
    }

    /**
     * Best-effort delete of an object that must never become the published
     * file (readability failure, DB commit failure). Failures are logged. The
     * candidate outbox row is left pending so the reclaimer retries.
     */
    private function cleanupUploadedObject(string $backend, string $storagePath): void
    {
        try {
            $this->storage->delete($backend, $storagePath);
        } catch (\Throwable $e) {
            Log::warning('ReviewService could not clean up an uncommitted regenerated object', [
                'storage_path' => $storagePath,
                'exception' => $e->getMessage(),
            ]);
        }
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
