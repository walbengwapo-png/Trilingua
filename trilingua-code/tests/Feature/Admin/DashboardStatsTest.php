<?php

namespace Tests\Feature\Admin;

use App\Models\TranslationBlock;
use App\Models\TranslationHistory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * Admin dashboard analytics — flag-reason breakdown must count each flagged
 * translation ONCE, never per document block.
 */
class DashboardStatsTest extends TestCase
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

    public function test_flag_reason_breakdown_counts_translations_not_blocks(): void
    {
        $admin = $this->makeAdmin();
        $user  = $this->makeUser();

        // One flagged TEXT translation.
        TranslationHistory::create([
            'user_id'           => $user->id,
            'translation_type'  => 'text',
            'source_language'   => 'English',
            'target_language'   => 'Cebuano',
            'source_text'       => 'Hello',
            'translated_text'   => 'Kumusta',
            'status'            => 'completed',
            'review_status'     => 'flagged',
            'flag_reason'       => 'mistranslation',
        ]);

        // One flagged DOCUMENT translation with THREE flagged blocks sharing the reason.
        $doc = TranslationHistory::create([
            'user_id'           => $user->id,
            'translation_type'  => 'document',
            'original_filename' => 'contract.pdf',
            'translated_filename' => 'contract_ceb.pdf',
            'source_language'   => 'English',
            'target_language'   => 'Cebuano',
            'status'            => 'completed',
            'review_status'     => 'flagged',
            'flag_reason'       => 'mistranslation',
        ]);

        foreach ([0, 1, 2] as $i) {
            TranslationBlock::create([
                'translation_history_id' => $doc->id,
                'block_index'            => $i,
                'block_type'             => 'paragraph',
                'source_text'            => "Block {$i}",
                'ai_translated_text'     => 'Agi',
                'current_text'           => 'Agi',
                'status'                 => 'flagged',
                'flag_reason'            => 'mistranslation',
            ]);
        }

        $response = $this->actingAs($admin)->get('/admin')->assertOk();

        $response->assertViewHas('flagReasonBreakdown', function (array $breakdown) {
            return ($breakdown['mistranslation'] ?? 0) === 2;
        });
    }
}
