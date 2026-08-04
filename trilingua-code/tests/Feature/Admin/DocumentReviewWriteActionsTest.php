<?php

namespace Tests\Feature\Admin;

use App\Models\TranslationBlock;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\User;
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

    public function test_verify_block_sets_verified_and_logs(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $block = $this->makeBlock($history, 0);

        $result = app(ReviewService::class)->verifyBlock($history->id, $block->id, $admin->id);

        $this->assertSame(ReviewStatus::VERIFIED, $result->status);

        $log = TranslationEditLog::where('translation_history_id', $history->id)->latest('id')->first();
        $this->assertNotNull($log);
        $this->assertSame('verify', $log->action);
        $this->assertSame($block->id, $log->translation_block_id);
        $this->assertSame('Ai text 0', $log->previous_text);
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

    public function test_flag_block_sets_reason_and_logs(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $block = $this->makeBlock($history, 0);

        $result = app(ReviewService::class)->flagBlock($history->id, $block->id, $admin->id, 'formatting_broken', 'Line broken');

        $this->assertSame(ReviewStatus::FLAGGED, $result->status);
        $this->assertSame('formatting_broken', $result->flag_reason);
        $this->assertSame('Line broken', $result->flag_note);

        $log = TranslationEditLog::where('translation_history_id', $history->id)->latest('id')->first();
        $this->assertNotNull($log);
        $this->assertSame('flag', $log->action);
        $this->assertSame($block->id, $log->translation_block_id);
    }

    public function test_bulk_approve_verifies_only_blocks_at_or_above_threshold(): void
    {
        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $this->makeBlock($history, 0, ['quality_score' => 95]);
        $this->makeBlock($history, 1, ['quality_score' => 60]);
        $this->makeBlock($history, 2, ['quality_score' => 85]);

        $result = app(ReviewService::class)->bulkApprove($history->id, $admin->id, 80);

        $this->assertSame(2, $result['approved']);
        $this->assertSame(3, $result['total']);

        $blocks = $history->blocks()->orderBy('block_index')->get();
        $this->assertSame(ReviewStatus::VERIFIED, $blocks[0]->status);
        $this->assertSame(ReviewStatus::PENDING, $blocks[1]->status);
        $this->assertSame(ReviewStatus::VERIFIED, $blocks[2]->status);

        // Two audit rows (one per approved block).
        $this->assertSame(2, TranslationEditLog::where('translation_history_id', $history->id)->count());
    }

    public function test_find_block_scoped_to_history_throws_on_mismatch(): void
    {
        $this->expectException(\InvalidArgumentException::class);

        $admin = $this->makeAdmin();
        $history = $this->makeDocRecord($this->makeUser());
        $other = $this->makeDocRecord($this->makeUser());
        $block = $this->makeBlock($history, 0);

        app(ReviewService::class)->verifyBlock($other->id, $block->id, $admin->id);
    }
}