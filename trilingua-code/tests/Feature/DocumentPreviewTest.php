<?php

namespace Tests\Feature;

use App\Models\TranslationBlock;
use App\Models\TranslationHistory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * Document preview accommodation:
 *  - GET /history/{id}/blocks (lazy block fallback for the detail view)
 *  - GET /admin/review/{translation}/blocks (lazy block fallback for review)
 *  - history-detail renders the shared converter host for non-PDF formats
 *  - admin review-document renders the converter host instead of a dead-end
 */
class DocumentPreviewTest extends TestCase
{
    use RefreshDatabase;

    private function makeUser(bool $admin = false): User
    {
        return User::factory()->create(['is_admin' => $admin]);
    }

    private function makeDoc(User $user, array $overrides = []): TranslationHistory
    {
        return TranslationHistory::create(array_merge([
            'user_id'              => $user->id,
            'translation_type'     => 'document',
            'original_filename'    => 'report.docx',
            'translated_filename'  => 'report_translated.docx',
            'source_language'      => 'English',
            'target_language'      => 'Cebuano',
            'original_storage_path' => '1/originals/report.docx',
            'storage_path'         => '1/translations/report_translated.docx',
            'status'               => 'completed',
        ], $overrides));
    }

    private function makeBlock(TranslationHistory $doc, array $overrides = []): TranslationBlock
    {
        return TranslationBlock::create(array_merge([
            'translation_history_id' => $doc->id,
            'block_index'            => 0,
            'block_type'             => 'paragraph',
            'source_text'            => 'Hello world',
            'ai_translated_text'     => 'Kumusta kalibutan',
            'current_text'           => 'Kumusta kalibutan',
            'published_text'         => 'Kumusta kalibutan',
            'quality_score'          => 90,
            'status'                 => 'pending',
        ], $overrides));
    }

    public function test_owner_can_fetch_document_blocks(): void
    {
        $user = $this->makeUser();
        $doc  = $this->makeDoc($user);
        $this->makeBlock($doc);

        $this->actingAs($user)
            ->getJson("/history/{$doc->id}/blocks")
            ->assertOk()
            ->assertJsonFragment(['block_index' => 0])
            ->assertJsonFragment(['published_text' => 'Kumusta kalibutan'])
            ->assertJsonFragment(['block_type' => 'paragraph'])
            ->assertJsonMissing(['current_text' => 'Kumusta kalibutan'], 'The owner Final endpoint must not expose draft text.');
    }

    public function test_blocks_endpoint_is_forbidden_for_another_user(): void
    {
        $owner = $this->makeUser();
        $other = $this->makeUser();
        $doc   = $this->makeDoc($owner);

        $this->actingAs($other)
            ->getJson("/history/{$doc->id}/blocks")
            ->assertForbidden();
    }

    public function test_blocks_endpoint_404_for_missing_record(): void
    {
        $user = $this->makeUser();

        $this->actingAs($user)
            ->getJson('/history/999999/blocks')
            ->assertNotFound();
    }

    public function test_history_detail_renders_converter_host_for_docx_translated_file(): void
    {
        $user = $this->makeUser();
        $doc  = $this->makeDoc($user);

        $response = $this->actingAs($user)->get("/history/{$doc->id}/view");

        $response->assertOk();
        $response->assertSee('converter-host', false);
        $response->assertSee('data-ext="docx"', false);
        $response->assertSee('data-blocks-url="' . route('history.blocks', $doc->id) . '"', false);
    }

    public function test_history_detail_marks_original_panel_for_source_fallback(): void
    {
        $user = $this->makeUser();
        $doc  = $this->makeDoc($user);

        $this->actingAs($user)
            ->get("/history/{$doc->id}/view")
            ->assertOk()
            ->assertSee('data-blocks-field="source_text"', false);
    }

    public function test_history_detail_uses_iframe_for_pdf_translated_file(): void
    {
        $user = $this->makeUser();
        $doc  = $this->makeDoc($user, ['translated_filename' => 'report_translated.pdf']);

        $this->actingAs($user)
            ->get("/history/{$doc->id}/view")
            ->assertOk()
            ->assertSee('review-pane__frame', false)
            ->assertDontSee('data-ext="pdf"', false);
    }

    public function test_admin_can_fetch_review_document_blocks(): void
    {
        $submitter = $this->makeUser();
        $doc       = $this->makeDoc($submitter);
        $this->makeBlock($doc);

        $this->actingAs($this->makeUser(true))
            ->getJson("/admin/review/{$doc->id}/blocks")
            ->assertOk()
            ->assertJsonFragment(['current_text' => 'Kumusta kalibutan']);
    }

    public function test_admin_review_renders_converter_host_for_docx_translated_file(): void
    {
        $submitter = $this->makeUser();
        $doc       = $this->makeDoc($submitter);
        $this->makeBlock($doc);

        $this->actingAs($this->makeUser(true))
            ->get("/admin/review/{$doc->id}")
            ->assertOk()
            ->assertSee('id="converter-host"', false)
            ->assertSee('data-ext="docx"', false)
            ->assertSee('data-blocks-url="' . route('admin.review.blocks', $doc->id) . '"', false);
    }

    public function test_admin_review_uses_iframe_for_pdf_translated_file(): void
    {
        $submitter = $this->makeUser();
        $doc       = $this->makeDoc($submitter, ['translated_filename' => 'report_translated.pdf']);

        $this->actingAs($this->makeUser(true))
            ->get("/admin/review/{$doc->id}")
            ->assertOk()
            ->assertSee('review-pane__frame', false)
            ->assertDontSee('id="converter-host"', false);
    }
}