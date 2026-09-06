<?php

namespace Tests\Feature\Admin;

use App\Models\TranslationBlock;
use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Auth;
use Tests\TestCase;

class RenderAdminViewsTest extends TestCase
{
    use RefreshDatabase;

    public function test_render_dashboard_text_and_document_views(): void
    {
        $admin = User::factory()->create(['is_admin' => true, 'name' => 'Alice Admin']);
        $user = User::factory()->create(['name' => 'Bob User']);

        $text = TranslationHistory::create([
            'user_id' => $user->id,
            'translation_type' => 'text',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'source_text' => 'Hello world, this is a sample sentence for review.',
            'translated_text' => 'Kumusta kalibutan, kini usa ka sample nga sentence alang sa review.',
            'status' => 'completed',
            'review_status' => 'verified',
            'quality_score' => 88,
            'reviewed_by' => $admin->id,
            'reviewed_at' => now()->subHours(3),
            'created_at' => now()->subDay(),
        ]);

        $flagged = TranslationHistory::create([
            'user_id' => $user->id,
            'translation_type' => 'text',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'source_text' => 'The quick brown fox jumps over the lazy dog.',
            'translated_text' => 'Ang paspas nga brown nga fox molukso sa tapulan nga iro.',
            'status' => 'completed',
            'review_status' => 'flagged',
            'flag_reason' => 'mistranslation',
            'flag_note' => 'Missed the article.',
            'quality_score' => 45,
            'reviewed_by' => $admin->id,
            'reviewed_at' => now()->subHours(5),
            'created_at' => now()->subDay(),
        ]);

        $doc = TranslationHistory::create([
            'user_id' => $user->id,
            'translation_type' => 'document',
            'original_filename' => 'contract.pdf',
            'translated_filename' => 'contract_ceb.pdf',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'original_storage_path' => '1/originals/contract.pdf',
            'status' => 'completed',
            'review_status' => 'pending',
            'quality_score' => 62,
            'created_at' => now()->subDay(),
        ]);

        foreach ([
            ['index' => 0, 'source' => 'This Agreement is entered into on 2024-01-01.', 'ai' => 'Kini nga Kasabutan nahimo kaniadtong 2024-01-01.', 'score' => 91, 'status' => 'pending'],
            ['index' => 1, 'source' => 'Party A shall deliver the goods.', 'ai' => 'Ang Partido A magpadala sa mga butang.', 'score' => 73, 'status' => 'pending'],
            ['index' => 2, 'source' => 'Payment terms are 30 days net.', 'ai' => 'Ang mga termino sa pagbayad kay 30 ka adlaw.', 'score' => 38, 'status' => 'flagged'],
        ] as $b) {
            TranslationBlock::create([
                'translation_history_id' => $doc->id,
                'block_index' => $b['index'],
                'block_type' => 'paragraph',
                'source_text' => $b['source'],
                'ai_translated_text' => $b['ai'],
                'current_text' => $b['ai'],
                'quality_score' => $b['score'],
                'status' => $b['status'],
                'flag_reason' => $b['status'] === 'flagged' ? 'inaccurate' : null,
            ]);
        }

        TranslationEditLog::create([
            'translation_history_id' => $text->id,
            'admin_id' => $admin->id,
            'action' => 'verify',
            'previous_text' => null,
            'new_text' => null,
            'created_at' => now()->subHours(3),
        ]);
        TranslationEditLog::create([
            'translation_history_id' => $text->id,
            'admin_id' => $admin->id,
            'action' => 'edit',
            'previous_text' => 'old value',
            'new_text' => 'new value',
            'created_at' => now()->subHours(2),
        ]);

        $out = base_path('review_render_out');
        if (!is_dir($out)) {
            mkdir($out, 0755, true);
        }

        Auth::login($admin);

        // Dashboard (full data set).
        $dash = $this->get('/admin')->assertOk()->getContent();
        file_put_contents($out . '/dashboard.html', $dash);

        // Text review (flagged record).
        $textView = $this->get("/admin/review/{$flagged->id}")->assertOk()->getContent();
        file_put_contents($out . '/review-text-write.html', $textView);

        // Document review (blocks + actions).
        $docView = $this->get("/admin/review/{$doc->id}")->assertOk()->getContent();
        file_put_contents($out . '/review-document-write.html', $docView);

        $this->assertTrue(true);
    }
}
