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
            ->assertSee('Editable Document')
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

    public function test_review_queue_supports_type_filter(): void
    {
        $submitter = $this->createUser();
        $this->createRecord($submitter, ['translation_type' => 'text', 'source_text' => 'Text one']);
        $this->createRecord($submitter, [
            'translation_type' => 'document',
            'original_filename' => 'doc.pdf',
            'translated_filename' => 'doc_ceb.pdf',
            'source_text' => null,
        ]);

        $this->actingAs($this->createAdmin())
            ->get('/admin/review?type=document')
            ->assertOk()
            ->assertSee('doc.pdf')
            ->assertDontSee('Text one');
    }

    public function test_review_queue_supports_user_filter(): void
    {
        $alice = $this->createUser();
        $bob = $this->createUser();
        $this->createRecord($alice, ['source_text' => 'Alice text']);
        $this->createRecord($bob, ['source_text' => 'Bob text']);

        $this->actingAs($this->createAdmin())
            ->get('/admin/review?user=' . $alice->id)
            ->assertOk()
            ->assertSee('Alice text')
            ->assertDontSee('Bob text');
    }

    public function test_review_queue_supports_date_range_filter(): void
    {
        $submitter = $this->createUser();
        $old = $this->createRecord($submitter, ['source_text' => 'Old text']);
        $old->forceFill(['created_at' => now()->subDays(10)])->save();
        $new = $this->createRecord($submitter, ['source_text' => 'New text']);
        $new->forceFill(['created_at' => now()->subDays(1)])->save();

        $this->actingAs($this->createAdmin())
            ->get('/admin/review?from=' . now()->subDays(5)->format('Y-m-d'))
            ->assertOk()
            ->assertSee('New text')
            ->assertDontSee('Old text');
    }

    public function test_review_queue_supports_lang_pair_filter(): void
    {
        $submitter = $this->createUser();
        $this->createRecord($submitter, ['source_text' => 'Cebuano text']); // English → Cebuano
        $this->createRecord($submitter, [
            'source_text' => 'Filipino text',
            'target_language' => 'Filipino',
        ]);

        $this->actingAs($this->createAdmin())
            ->get('/admin/review?' . http_build_query(['lang_pair' => 'English → Filipino']))
            ->assertOk()
            ->assertSee('Filipino text')
            ->assertDontSee('Cebuano text');
    }

    public function test_document_review_supports_block_status_filter(): void
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
            'source_text' => 'Pending block source',
            'ai_translated_text' => 'Pending block text',
            'current_text' => 'Pending block text',
            'quality_score' => 90,
            'status' => 'pending',
        ]);
        TranslationBlock::create([
            'translation_history_id' => $record->id,
            'block_index' => 1,
            'block_type' => 'paragraph',
            'source_text' => 'Flagged block source',
            'ai_translated_text' => 'Flagged block text',
            'current_text' => 'Flagged block text',
            'quality_score' => 30,
            'status' => 'flagged',
        ]);

        $this->actingAs($this->createAdmin())
            ->get("/admin/review/{$record->id}?status=flagged")
            ->assertOk()
            ->assertSee('Flagged block text')
            ->assertDontSee('Pending block text');
    }

    public function test_document_review_paginates_blocks(): void
    {
        $submitter = $this->createUser();
        $record = $this->createRecord($submitter, [
            'translation_type' => 'document',
            'original_filename' => 'big.txt',
            'translated_filename' => 'big_translated.txt',
        ]);

        for ($i = 0; $i < 30; $i++) {
            TranslationBlock::create([
                'translation_history_id' => $record->id,
                'block_index' => $i,
                'block_type' => 'paragraph',
                'source_text' => "Source block {$i}",
                'ai_translated_text' => "Translation block {$i}",
                'current_text' => "Translation block {$i}",
                'quality_score' => 50,
                'status' => 'pending',
            ]);
        }

        $this->actingAs($this->createAdmin())
            ->get("/admin/review/{$record->id}")
            ->assertOk()
            ->assertSee('Showing 25 of 30 blocks');
    }

    public function test_document_review_block_search_filters_content(): void
    {
        $submitter = $this->createUser();
        $record = $this->createRecord($submitter, [
            'translation_type' => 'document',
            'original_filename' => 'search.txt',
            'translated_filename' => 'search_translated.txt',
        ]);

        TranslationBlock::create([
            'translation_history_id' => $record->id,
            'block_index' => 0,
            'block_type' => 'paragraph',
            'source_text' => 'contractual clause about pricing',
            'ai_translated_text' => 'clausula sa presyo',
            'current_text' => 'clausula sa presyo',
            'quality_score' => 80,
            'status' => 'pending',
        ]);
        TranslationBlock::create([
            'translation_history_id' => $record->id,
            'block_index' => 1,
            'block_type' => 'paragraph',
            'source_text' => 'entirely unrelated paragraph',
            'ai_translated_text' => 'walay kalabotan nga paragraph',
            'current_text' => 'walay kalabotan nga paragraph',
            'quality_score' => 70,
            'status' => 'pending',
        ]);

        $this->actingAs($this->createAdmin())
            ->get("/admin/review/{$record->id}?" . http_build_query(['search' => 'pricing']))
            ->assertOk()
            ->assertSee('clausula sa presyo')
            ->assertDontSee('walay kalabotan nga paragraph');
    }

    public function test_admin_can_preview_translated_pdf_file_inline(): void
    {
        $record = $this->createRecord($this->createUser(), [
            'translation_type' => 'document',
            'original_filename' => 'contract.pdf',
            'translated_filename' => 'contract_ceb.pdf',
            'storage_path' => '2/7ccb9dc7-contract_ceb.pdf',
        ]);

        $storage = \Mockery::mock(\App\Services\StorageService::class);
        $storage->shouldReceive('downloadFile')->once()->andReturn('%PDF-1.4 fake pdf bytes');
        $this->app->instance(\App\Services\StorageService::class, $storage);

        $response = $this->actingAs($this->createAdmin())
            ->get("/admin/review/{$record->id}/file");

        $response->assertOk()
            ->assertHeader('Content-Type', 'application/pdf')
            ->assertHeader('Content-Disposition', 'inline; filename="contract_ceb.pdf"');
        $this->assertStringContainsString('%PDF-1.4 fake pdf bytes', $response->streamedContent());
    }

    public function test_translated_file_mime_comes_from_filename_not_local_path(): void
    {
        // storage_path is a Supabase bucket key, never a local filesystem path —
        // mime_content_type() on it throws under Laravel. Detection must come
        // from the translated filename extension.
        $record = $this->createRecord($this->createUser(), [
            'translation_type' => 'document',
            'original_filename' => 'report.docx',
            'translated_filename' => 'report_translated.docx',
            'storage_path' => '3/xyz-report_translated.docx',
        ]);

        $storage = \Mockery::mock(\App\Services\StorageService::class);
        $storage->shouldReceive('downloadFile')->once()->andReturn('PK fake docx zip bytes');
        $this->app->instance(\App\Services\StorageService::class, $storage);

        $response = $this->actingAs($this->createAdmin())
            ->get("/admin/review/{$record->id}/file");

        $response->assertOk()
            ->assertHeader(
                'Content-Type',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            ->assertHeader('Content-Disposition', 'inline; filename="report_translated.docx"');
    }

    public function test_translated_file_route_404_for_text_translation(): void
    {
        $record = $this->createRecord($this->createUser()); // translation_type = 'text'

        $this->actingAs($this->createAdmin())
            ->get("/admin/review/{$record->id}/file")
            ->assertNotFound();
    }

    public function test_review_queue_supports_keyword_search(): void
    {
        $submitter = $this->createUser();
        $this->createRecord($submitter, ['source_text' => 'confidential clause details']);
        $this->createRecord($submitter, ['source_text' => 'unrelated sentence here']);

        $this->actingAs($this->createAdmin())
            ->get('/admin/review?' . http_build_query(['q' => 'confidential']))
            ->assertOk()
            ->assertSee('confidential clause details')
            ->assertDontSee('unrelated sentence here');
    }

    public function test_review_queue_renders_search_input(): void
    {
        $this->createRecord($this->createUser());

        $this->actingAs($this->createAdmin())
            ->get('/admin/review')
            ->assertOk()
            ->assertSee('name="q"', false);
    }

    public function test_review_queue_supports_priority_filter(): void
    {
        $submitter = $this->createUser();
        $priority = $this->createRecord($submitter, ['source_text' => 'Priority flagged text']);
        $priority->forceFill(['is_priority' => true])->save();
        $this->createRecord($submitter, ['source_text' => 'Regular text']);

        $this->actingAs($this->createAdmin())
            ->get('/admin/review?' . http_build_query(['priority' => '1']))
            ->assertOk()
            ->assertSee('Priority flagged text')
            ->assertDontSee('Regular text');
    }

    public function test_review_queue_shows_priority_badge(): void
    {
        $submitter = $this->createUser();
        $priority = $this->createRecord($submitter, ['source_text' => 'Priority text']);
        $priority->forceFill(['is_priority' => true])->save();

        $this->actingAs($this->createAdmin())
            ->get('/admin/review')
            ->assertOk()
            ->assertSee('Priority', false);
    }
}