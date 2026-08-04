<?php

namespace Tests\Feature\Admin;

use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Services\Admin\ReviewService;
use App\Support\ReviewStatus;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class TextReviewWriteActionsTest extends TestCase
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

    private function makeTextRecord(User $submitter, array $overrides = []): TranslationHistory
    {
        return TranslationHistory::create(array_merge([
            'user_id' => $submitter->id,
            'translation_type' => 'text',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'source_text' => 'Hello world',
            'translated_text' => 'Kumusta kalibutan',
            'status' => 'completed',
            'review_status' => 'pending',
            'quality_score' => 70,
        ], $overrides));
    }

    public function test_text_verify_transitions_status_and_logs(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeTextRecord($this->makeUser());

        $review = app(ReviewService::class);
        $result = $review->verify($record->id, $admin->id);

        $this->assertSame(ReviewStatus::VERIFIED, $result->review_status);
        $this->assertSame($admin->id, $result->reviewed_by);

        $log = TranslationEditLog::where('translation_history_id', $record->id)->latest('id')->first();
        $this->assertNotNull($log);
        $this->assertSame('verify', $log->action);
        $this->assertNull($log->translation_block_id);
    }

    public function test_text_edit_audits_previous_text_before_overwrite_and_edits(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeTextRecord($this->makeUser());

        $review = app(ReviewService::class);
        $result = $review->editText($record->id, $admin->id, 'Bag-ong hubad');

        $this->assertSame(ReviewStatus::EDITED, $result->review_status);
        $this->assertSame('Bag-ong hubad', $result->translated_text);

        // Audit log recorded the PREVIOUS value before overwrite.
        $log = TranslationEditLog::where('translation_history_id', $record->id)->latest('id')->first();
        $this->assertNotNull($log);
        $this->assertSame('edit', $log->action);
        $this->assertSame('Kumusta kalibutan', $log->previous_text);
        $this->assertSame('Bag-ong hubad', $log->new_text);
    }

    public function test_text_edit_no_op_when_text_unchanged(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeTextRecord($this->makeUser());

        $review = app(ReviewService::class);
        $result = $review->editText($record->id, $admin->id, 'Kumusta kalibutan');

        $this->assertSame(ReviewStatus::PENDING, $result->review_status);
        $this->assertSame(0, TranslationEditLog::where('translation_history_id', $record->id)->count());
    }

    public function test_text_flag_persists_reason_and_logs(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeTextRecord($this->makeUser());

        $review = app(ReviewService::class);
        $result = $review->flag($record->id, $admin->id, 'mistranslation', 'Wrong verb tense');

        $this->assertSame(ReviewStatus::FLAGGED, $result->review_status);
        $this->assertSame('mistranslation', $result->flag_reason);
        $this->assertSame('Wrong verb tense', $result->flag_note);

        $log = TranslationEditLog::where('translation_history_id', $record->id)->latest('id')->first();
        $this->assertNotNull($log);
        $this->assertSame('flag', $log->action);
    }

    public function test_text_flag_rejects_invalid_reason(): void
    {
        $this->expectException(\InvalidArgumentException::class);

        $admin = $this->makeAdmin();
        $record = $this->makeTextRecord($this->makeUser());

        app(ReviewService::class)->flag($record->id, $admin->id, 'not-a-real-reason');
    }

    public function test_text_edit_rejects_document_record(): void
    {
        $this->expectException(\InvalidArgumentException::class);

        $admin = $this->makeAdmin();
        $record = TranslationHistory::create([
            'user_id' => $this->makeUser()->id,
            'translation_type' => 'document',
            'original_filename' => 'x.pdf',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'status' => 'completed',
            'review_status' => 'pending',
        ]);

        app(ReviewService::class)->editText($record->id, $admin->id, 'new text');
    }
}