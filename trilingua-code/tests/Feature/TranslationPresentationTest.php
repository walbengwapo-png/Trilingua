<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\User;
use App\Notifications\TranslationCompleted;
use App\Notifications\TranslationFailed;
use App\Services\BlockService;
use App\Support\TranslationQuality;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class TranslationPresentationTest extends TestCase
{
    use RefreshDatabase;

    private function record(User $user, array $extra = []): TranslationHistory
    {
        return TranslationHistory::create(array_merge([
            'user_id' => $user->id, 'translation_type' => 'document',
            'original_filename' => 'contract.pdf', 'translated_filename' => 'contract_ceb.pdf',
            'source_language' => 'English', 'target_language' => 'Cebuano',
            'status' => 'completed', 'review_status' => 'pending',
        ], $extra));
    }

    public function test_translation_page_has_no_processing_selector(): void
    {
        $this->actingAs(User::factory()->create())->get('/translate')->assertOk()
            ->assertDontSee('translation-mode')->assertDontSee('translationMode');
    }

    public function test_notifications_identify_text_and_use_current_document_name(): void
    {
        $user = User::factory()->create();
        $text = $this->record($user, ['translation_type' => 'text', 'original_filename' => null,
            'translated_filename' => null, 'source_text' => 'School assembly on Monday']);
        $user->notify(new TranslationCompleted($text));
        $doc = $this->record($user);
        $user->notify(new TranslationCompleted($doc));
        $doc->update(['translated_filename' => '<script>renamed</script>.pdf']);

        $items = $this->actingAs($user)->getJson('/notifications/data')->assertOk()->json('notifications');
        $this->assertCount(2, $items);
        $this->assertStringContainsString('School assembly on Monday', implode(' ', array_column($items, 'display_title')));
        $this->assertStringContainsString('Translation #'.$text->id, implode(' ', array_column($items, 'description')));
        $this->get('/notifications')->assertOk()->assertSee('&lt;script&gt;renamed&lt;/script&gt;.pdf', false)
            ->assertDontSee('<script>renamed</script>', false);
    }

    public function test_failed_notification_identifies_job_and_language_pair(): void
    {
        $user = User::factory()->create();
        $user->notify(new TranslationFailed('broken.pdf', 'Internal error', 12, 'English', 'Cebuano'));
        $this->actingAs($user)->getJson('/notifications/data')->assertOk()
            ->assertJsonPath('notifications.0.display_title', 'Translation failed — broken.pdf')
            ->assertJsonPath('notifications.0.description', 'English → Cebuano · Job #12');
    }

    public function test_document_score_coverage_excludes_passthrough_and_rejects_invalid_scores(): void
    {
        $user = User::factory()->create();
        $record = $this->record($user);
        app(BlockService::class)->persistBlocks($record, [
            ['source_text' => 'First text', 'text' => 'Unang teksto', 'quality_score' => 88.5],
            ['source_text' => 'Second text', 'text' => 'Ikaduhang teksto', 'quality_score' => null],
            ['source_text' => 'Kept source', 'text' => 'Kept source', 'quality_score' => 100, 'passthrough' => true],
            ['source_text' => 'Third text', 'text' => 'Ikatulong teksto', 'quality_score' => 101],
        ]);
        $record->refresh();
        $this->assertSame(89, $record->quality_score);
        $this->assertSame('partial', $record->sidecar['quality_review']['status']);
        $this->assertSame(3, $record->sidecar['quality_review']['eligible_blocks']);
        $this->actingAs($user)->get('/history')->assertOk()->assertSee('89/100')
            ->assertSee('1 of 3 text sections checked')->assertDontSee('match-badge');

        $record->blocks()->delete();
        app(BlockService::class)->persistBlocks($record, [['source_text' => 'Text', 'text' => 'Teksto']]);
        $this->assertNull($record->fresh()->quality_score);
    }

    public function test_invalid_scores_do_not_become_zero_or_full_confidence(): void
    {
        foreach ([null, '', true, false, 'NaN', INF, NAN, -1, 101, []] as $value) {
            $this->assertNull(TranslationQuality::score($value));
        }
        $this->assertSame(0, TranslationQuality::score(0));
        $this->assertSame(100, TranslationQuality::score('100'));
    }

    public function test_details_show_analysis_and_distinguish_review_failure_from_translation_failure(): void
    {
        $user = User::factory()->create();
        $record = $this->record($user, ['sidecar' => [
            'quality_review' => ['status' => 'unavailable', 'reason' => 'review_failed'],
            'analysis' => ['status' => 'analyzed', 'domain' => 'legal', 'document_type' => 'legal_contract',
                'extracted_blocks' => 12, 'extracted_words' => 300, 'summary' => 'A rental contract.', 'confidence' => .86],
        ]]);
        $this->actingAs($user)->get('/history/'.$record->id.'/view')->assertOk()
            ->assertSee('legal')->assertSee('Legal Contract')->assertSee('Words read')
            ->assertDontSee('Extracted text blocks')->assertDontSee('Analyzer confidence')->assertDontSee('86%')
            ->assertSee('A rental contract.')->assertSee('Review unavailable')
            ->assertSee('translation remains accessible');
        $this->actingAs(User::factory()->create())->get('/history/'.$record->id.'/view')->assertForbidden();
    }

    public function test_legacy_details_do_not_invent_analysis_or_score(): void
    {
        $user = User::factory()->create();
        $record = $this->record($user);
        $this->actingAs($user)->get('/history/'.$record->id.'/view')->assertOk()
            ->assertSee('A document summary was not saved')->assertSee('Review not recorded');
    }

    public function test_partial_details_explain_unchanged_pages_without_exposing_internal_reasons(): void
    {
        $user = User::factory()->create();
        $region = ['page' => 0, 'status' => 'held', 'reason' => 'native_fit_hold'];
        $record = $this->record($user, ['quality_score' => 89, 'sidecar' => [
            'content_summary' => ['status' => 'partial', 'held' => 3, 'translated' => 1, 'ocr_mode' => 'preview'],
            'analysis' => ['status' => 'analyzed', 'domain' => 'legal', 'extracted_words' => 42,
                'entities' => ['School'], 'terminology' => ['Agreement'], 'analyzer_model' => 'internal-model'],
            'render_plan' => ['regions' => [$region, $region, ['page' => 2, 'status' => 'held',
                'reason' => '<script>internal reason</script>']]],
        ]]);
        $response = $this->actingAs($user)->get('/history/'.$record->id.'/view')->assertOk()
            ->assertSee('Partly translated.')->assertSee('Page 1:')->assertSee('Page 3:')
            ->assertSee('could not fit without affecting the layout')
            ->assertSee('Experimental image-text translation')->assertSee('Words read (incomplete count)')
            ->assertSee('Translation Status')->assertSee('Completed')->assertSee('Pending')
            ->assertSee('89/100')->assertSee('Domain')->assertSee('Entities')->assertSee('Terminology')
            ->assertDontSee('native_fit_hold')->assertDontSee('internal reason')->assertDontSee('internal-model');
        $this->assertSame(1, substr_count($response->getContent(), 'Page 1:'));
    }
}
