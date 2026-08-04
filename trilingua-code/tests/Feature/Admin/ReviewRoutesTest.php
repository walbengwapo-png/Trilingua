<?php

namespace Tests\Feature\Admin;

use App\Models\TranslationBlock;
use App\Models\TranslationHistory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ReviewRoutesTest extends TestCase
{
    use RefreshDatabase;

    private function createAdmin(): User
    {
        return User::factory()->create(['is_admin' => true]);
    }

    private function createUser(): User
    {
        return User::factory()->create(['is_admin' => false]);
    }

    private function createRecord(User $submitter, array $overrides = []): TranslationHistory
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

    public function test_guest_is_redirected_to_login_from_review_queue(): void
    {
        $this->get('/admin/review')->assertRedirect('/login');
    }

    public function test_non_admin_gets_403_from_review_queue(): void
    {
        $this->actingAs($this->createUser())
            ->get('/admin/review')
            ->assertForbidden();
    }

    public function test_non_admin_gets_403_from_review_detail(): void
    {
        $record = $this->createRecord($this->createUser());

        $this->actingAs($this->createUser())
            ->get("/admin/review/{$record->id}")
            ->assertForbidden();
    }

    public function test_admin_can_view_review_queue(): void
    {
        $submitter = $this->createUser();
        $record = $this->createRecord($submitter);

        $this->actingAs($this->createAdmin())
            ->get('/admin/review')
            ->assertOk()
            ->assertSee('Review Queue')
            ->assertSee($submitter->name)
            ->assertSee('Hello world');
    }

    public function test_admin_can_view_text_review_detail(): void
    {
        $record = $this->createRecord($this->createUser());

        $this->actingAs($this->createAdmin())
            ->get("/admin/review/{$record->id}")
            ->assertOk()
            ->assertSee('Kumusta kalibutan');
    }

    public function test_admin_can_view_document_review_detail_with_blocks(): void
    {
        $submitter = $this->createUser();
        $record = $this->createRecord($submitter, [
            'translation_type' => 'document',
            'original_filename' => 'sample.txt',
            'translated_filename' => 'sample_translated.txt',
        ]);

        TranslationBlock::create([
            'translation_history_id' => $record->id,
            'block_index' => 0,
            'block_type' => 'paragraph',
            'source_text' => 'Hello world',
            'ai_translated_text' => 'Kumusta kalibutan',
            'current_text' => 'Kumusta kalibutan',
            'quality_score' => 90,
            'status' => 'pending',
        ]);

        $this->actingAs($this->createAdmin())
            ->get("/admin/review/{$record->id}")
            ->assertOk()
            ->assertSee('Extracted Blocks')
            ->assertSee('Block #0')
            ->assertSee('Kumusta kalibutan');
    }

    public function test_review_queue_supports_status_filter(): void
    {
        $submitter = $this->createUser();
        $this->createRecord($submitter, ['review_status' => 'pending', 'source_text' => 'Pending one']);
        $this->createRecord($submitter, ['review_status' => 'verified', 'source_text' => 'Verified one']);

        $this->actingAs($this->createAdmin())
            ->get('/admin/review?status=pending')
            ->assertOk()
            ->assertSee('Pending one')
            ->assertDontSee('Verified one');
    }
}