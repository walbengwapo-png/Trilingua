<?php

namespace Tests\Feature\Admin;

use App\Models\TranslationBlock;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Exceptions\TranslationException;
use App\Services\Admin\ReviewService;
use App\Support\ReviewStatus;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class DocumentReviewWriteActionsTest extends TestCase
{
    use RefreshDatabase;

    private function makeAdmin(): User
    {
        return User::factory()->create(['is_admin' => true]);
    }

    private function makeUser(): User
    {
        return User::factory()->create(['is_admin' => false]);
    }

    private function makeDocRecord(User $submitter, array $overrides = []): TranslationHistory
    {
        return TranslationHistory::create(array_merge([
            'user_id' => $submitter->id,
            'translation_type' => 'document',
            'original_filename' => 'contract.pdf',
            'translated_filename' => 'contract_ceb.pdf',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'original_storage_path' => '1/originals/contract.pdf',
            'status' => 'completed',
            'review_status' => 'pending',
            'quality_score' => 60,
        ], $overrides));
    }

    private function makeBlock(TranslationHistory $history, int $index, array $overrides = []): TranslationBlock
    {
        return TranslationBlock::create(array_merge([
            'translation_history_id' => $history->id,
            'block_index' => $index,
            'block_type' => 'paragraph',
            'source_text' => "Source $index",
            'ai_translated_text' => "Ai text $index",
            'current_text' => "Ai text $index",
            'quality_score' => 90,
            'status' => 'pending',
        ], $overrides));
    }

    public function test_verify_document_cascades_to_blocks(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $blockA = $this->makeBlock($history, 0);
        $blockB = $this->makeBlock($history, 1);

        $result = app(ReviewService::class)->verifyDocument($history->id, $admin->id);

        $this->assertSame(ReviewStatus::VERIFIED, $result->review_status);
        $this->assertSame(ReviewStatus::VERIFIED, $blockA->fresh()->status);
        $this->assertSame(ReviewStatus::VERIFIED, $blockB->fresh()->status);

        $log = TranslationEditLog::where('translation_history_id', $history->id)->latest('id')->first();
        $this->assertNotNull($log);
        $this->assertSame('verify', $log->action);
        $this->assertNull($log->translation_block_id);
    }

    public function test_verify_document_rejects_unpublished_draft_edits(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $block = $this->makeBlock($history, 0);

        // Persist a draft edit (Save Edit) — the file is not regenerated.
        app(ReviewService::class)->updateBlock($history->id, $block->id, $admin->id, 'Draft only');
        $this->assertTrue($history->fresh()->hasUnpublishedEdits());

        try {
            app(ReviewService::class)->verifyDocument($history->id, $admin->id);
            $this->fail('verifyDocument must reject a document with unpublished draft edits.');
        } catch (TranslationException $e) {
            $this->assertStringContainsString('Save & Regenerate', $e->getMessage());
        }

        // Nothing was verified, no verify audit row was written.
        $this->assertSame('edited', $history->fresh()->review_status);
        $this->assertSame(0, TranslationEditLog::where('translation_history_id', $history->id)->where('action', 'verify')->count());
    }

    public function test_update_block_audits_previous_and_preserves_ai_text(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $block = $this->makeBlock($history, 0);

        $result = app(ReviewService::class)->updateBlock($history->id, $block->id, $admin->id, 'Edited current text');

        $this->assertSame(ReviewStatus::EDITED, $result->status);
        $this->assertSame('Edited current text', $result->current_text);
        // Immutability: ai_translated_text untouched.
        $this->assertSame('Ai text 0', $result->ai_translated_text);

        $log = TranslationEditLog::where('translation_history_id', $history->id)->latest('id')->first();
        $this->assertNotNull($log);
        $this->assertSame('edit', $log->action);
        $this->assertSame('Ai text 0', $log->previous_text);
        $this->assertSame('Edited current text', $log->new_text);

        // Save Edit is a DRAFT: draft revision advances, published does not.
        $fresh = $history->fresh();
        $this->assertSame(1, (int) $fresh->draft_revision);
        $this->assertSame(0, (int) $fresh->published_revision);
        $this->assertTrue($fresh->hasUnpublishedEdits());
    }

    public function test_update_block_no_op_when_unchanged(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $block = $this->makeBlock($history, 0);

        app(ReviewService::class)->updateBlock($history->id, $block->id, $admin->id, 'Ai text 0');

        $this->assertSame(ReviewStatus::PENDING, $block->fresh()->status);
        $this->assertSame(0, TranslationEditLog::where('translation_history_id', $history->id)->count());
    }

    public function test_flag_document_cascades_to_blocks(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $blockA = $this->makeBlock($history, 0);
        $blockB = $this->makeBlock($history, 1);

        $result = app(ReviewService::class)->flagDocument($history->id, $admin->id, 'formatting_broken', 'Line broken');

        $this->assertSame(ReviewStatus::FLAGGED, $result->review_status);
        $this->assertSame('formatting_broken', $result->flag_reason);
        $this->assertSame('Line broken', $result->flag_note);
        $this->assertSame(ReviewStatus::FLAGGED, $blockA->fresh()->status);
        $this->assertSame('formatting_broken', $blockA->fresh()->flag_reason);
        $this->assertSame(ReviewStatus::FLAGGED, $blockB->fresh()->status);
        $this->assertSame('formatting_broken', $blockB->fresh()->flag_reason);

        $log = TranslationEditLog::where('translation_history_id', $history->id)->latest('id')->first();
        $this->assertNotNull($log);
        $this->assertSame('flag', $log->action);
        $this->assertNull($log->translation_block_id);
    }

    public function test_flag_document_rejects_invalid_reason(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $this->makeBlock($history, 0);

        $this->expectException(\InvalidArgumentException::class);

        app(ReviewService::class)->flagDocument($history->id, $admin->id, 'not-a-real-reason');
    }

    public function test_find_block_scoped_to_history_throws_on_mismatch(): void
    {
        $this->expectException(\InvalidArgumentException::class);

        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $other = $this->makeDocRecord($this->makeUser());
        $block = $this->makeBlock($history, 0);

        app(ReviewService::class)->updateBlock($other->id, $block->id, $admin->id, 'Edited text');
    }

    public function test_apply_block_edits_audits_changes_and_skips_no_ops(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $blockA = $this->makeBlock($history, 0);
        $blockB = $this->makeBlock($history, 1);

        $changed = app(ReviewService::class)->applyBlockEdits(
            $history->id,
            $admin->id,
            [
                $blockA->id => 'Bag-ong text A',
                $blockB->id => 'Ai text 1', // unchanged → must be a no-op
                999 => 'ignored',           // unknown block → must be a no-op
            ],
        );

        $this->assertSame(1, $changed);
        $this->assertSame('Bag-ong text A', $blockA->fresh()->current_text);
        $this->assertSame(ReviewStatus::EDITED, $blockA->fresh()->status);
        $this->assertSame('Ai text 1', $blockB->fresh()->current_text);
        $this->assertSame(ReviewStatus::PENDING, $blockB->fresh()->status);
        $this->assertSame(ReviewStatus::EDITED, $history->fresh()->review_status);

        $logs = TranslationEditLog::where('translation_history_id', $history->id)->get();
        $this->assertCount(1, $logs);
        $this->assertSame('edit', $logs[0]->action);
        $this->assertSame('Ai text 0', $logs[0]->previous_text);
        $this->assertSame('Bag-ong text A', $logs[0]->new_text);

        $this->assertSame(1, (int) $history->fresh()->draft_revision);
        $this->assertSame(0, (int) $history->fresh()->published_revision);
    }

    public function test_apply_block_edits_no_op_when_nothing_changes(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $block = $this->makeBlock($history, 0);

        $changed = app(ReviewService::class)->applyBlockEdits(
            $history->id,
            $admin->id,
            [$block->id => 'Ai text 0'],
        );

        $this->assertSame(0, $changed);
        $this->assertSame(ReviewStatus::PENDING, $history->fresh()->review_status);
        $this->assertSame(0, TranslationEditLog::where('translation_history_id', $history->id)->count());
    }

    public function test_apply_block_edits_ignores_blocks_from_other_histories(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $other = $this->makeDocRecord($this->makeUser());
        $otherBlock = $this->makeBlock($other, 0);

        $changed = app(ReviewService::class)->applyBlockEdits(
            $history->id,
            $admin->id,
            [$otherBlock->id => 'Hacked text'],
        );

        $this->assertSame(0, $changed);
        $this->assertSame('Ai text 0', $otherBlock->fresh()->current_text);
        $this->assertSame(0, TranslationEditLog::where('translation_history_id', $history->id)->count());
    }
}