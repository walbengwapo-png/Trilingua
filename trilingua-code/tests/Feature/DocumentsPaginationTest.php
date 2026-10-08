<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * Gate 3b — the My Documents list must be paginated, not truncated.
 *
 * The page used to read the newest 200 rows and render them with no way to
 * reach anything older: a user's 201st translation made the first one
 * permanently invisible with no indication that it had happened.
 */
class DocumentsPaginationTest extends TestCase
{
    use RefreshDatabase;

    private function seedDocuments(User $user, int $count): void
    {
        for ($i = 0; $i < $count; $i++) {
            TranslationHistory::create([
                'user_id'            => $user->id,
                'translation_type'   => 'document',
                'original_filename'  => 'source-' . $i . '.pdf',
                'translated_filename'=> 'translated-' . $i . '.pdf',
                'source_language'    => 'English',
                'target_language'    => 'Cebuano',
                'created_at'         => now()->subMinutes($count - $i),
            ]);
        }
    }

    public function test_the_first_page_does_not_contain_every_document(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);
        $this->seedDocuments($user, 60);

        $response = $this->get('/documents');

        $response->assertStatus(200);
        $response->assertViewHas('documents', function ($pager) {
            return $pager->total() === 60 && count($pager->items()) < 60;
        });
    }

    public function test_documents_past_the_first_page_are_reachable(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);
        $this->seedDocuments($user, 60);

        // The oldest document exists only on a later page.
        $oldest = TranslationHistory::where('user_id', $user->id)
            ->orderBy('created_at')
            ->first();

        // The card renders translated_filename, so that is what the page
        // exposes; doc 0 is the oldest and therefore the last to be listed.
        $this->get('/documents')->assertDontSee('translated-0.pdf', false);

        $lastPage = $this->get('/documents?page=3');
        $lastPage->assertStatus(200);
        $lastPage->assertSee('translated-0.pdf', false);

        $this->assertNotNull($oldest);
    }

    public function test_the_page_reports_the_true_total_not_the_page_size(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);
        $this->seedDocuments($user, 60);

        $response = $this->get('/documents');

        $response->assertStatus(200);
        // The header count must be the real total, not the 24 rows on screen.
        $response->assertSee('>60<', false);
    }

    public function test_pagination_links_render_when_there_is_more_than_one_page(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);
        $this->seedDocuments($user, 60);

        $response = $this->get('/documents');

        $response->assertStatus(200);
        $response->assertSee('docs-pagination', false);
    }

    public function test_no_pagination_markup_renders_for_a_single_page(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);
        $this->seedDocuments($user, 3);

        $response = $this->get('/documents');

        $response->assertStatus(200);
        $response->assertDontSee('docs-pagination', false);
    }

    public function test_text_translations_are_not_listed_as_documents(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);

        TranslationHistory::create([
            'user_id' => $user->id, 'translation_type' => 'text',
            'source_language' => 'English', 'target_language' => 'Cebuano',
            'source_text' => 'hello', 'created_at' => now(),
        ]);
        $this->seedDocuments($user, 2);

        $response = $this->get('/documents');

        $response->assertViewHas('documents', function ($pager) {
            return $pager->total() === 2;
        });
    }

    public function test_the_language_filter_offers_every_pair_beyond_the_first_page(): void
    {
        // The dropdown used to be built from the loaded page, so pairs that
        // only existed on later pages were missing from the filter.
        $user = User::factory()->create();
        $this->actingAs($user);

        $this->seedDocuments($user, 30);
        TranslationHistory::create([
            'user_id' => $user->id, 'translation_type' => 'document',
            'original_filename' => 'rare.pdf', 'translated_filename' => 'rare-fil.pdf',
            'source_language' => 'Cebuano', 'target_language' => 'Filipino',
            'created_at' => now()->subDays(5),
        ]);

        $response = $this->get('/documents');

        $response->assertStatus(200);
        $response->assertSee('Cebuano → Filipino', false);
    }

    public function test_history_renders_page_links(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);

        for ($i = 0; $i < 120; $i++) {
            TranslationHistory::create([
                'user_id' => $user->id, 'translation_type' => 'text',
                'source_language' => 'English', 'target_language' => 'Cebuano',
                'source_text' => 'text ' . $i, 'created_at' => now()->subMinutes(120 - $i),
            ]);
        }

        $response = $this->get('/history');

        $response->assertStatus(200);
        // The service already paginated at 50; the view never offered a link.
        $response->assertSee('history-pagination', false);
    }
}
