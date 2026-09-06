<?php

namespace Tests\Unit;

use App\Services\Translation\DTO\TranslationRequest;
use App\Support\TranslationPresentation;
use Carbon\Carbon;
use Tests\TestCase;

class TranslationPresentationTest extends TestCase
{
    public function test_text_translation_has_a_clear_asset_lifecycle_and_risk_label(): void
    {
        $presentation = TranslationPresentation::for([
            'translation_type' => 'text',
            'source_text' => 'Please call me tomorrow.',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'status' => 'completed',
            'review_status' => 'pending',
            'quality_score' => 55,
            'created_at' => Carbon::now(),
        ]);

        $this->assertSame('text_translation', $presentation['asset']['key']);
        $this->assertSame('Translation complete · Review pending', $presentation['lifecycle']['label']);
        $this->assertSame('high', $presentation['quality']['risk']);
        $this->assertSame('55/100 · High risk', $presentation['quality']['text']);
    }

    public function test_reviewed_document_is_presented_as_a_reviewed_final(): void
    {
        $presentation = TranslationPresentation::for([
            'translation_type' => 'document',
            'original_filename' => 'notice.docx',
            'translated_filename' => 'notice_ceb.docx',
            'storage_path' => 'documents/notice_ceb.docx',
            'status' => 'completed',
            'review_status' => 'verified',
            'quality_score' => 91,
            'created_at' => '2026-09-06 08:00:00+00:00',
        ], [
            'timezone' => 'Asia/Manila',
            'date_format' => 'Y-m-d H:i T',
        ]);

        $this->assertSame('reviewed_final', $presentation['asset']['key']);
        $this->assertSame('Low risk', $presentation['quality']['label']);
        $this->assertSame('2026-09-06 16:00 PHT', $presentation['date']['exact']);
    }

    public function test_text_request_keeps_the_selected_processing_mode(): void
    {
        $request = new TranslationRequest('Hello', 'English', 'Cebuano', 'thorough');

        $this->assertSame('thorough', $request->toArray()['mode']);
    }
}
