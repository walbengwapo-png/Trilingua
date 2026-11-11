<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class HistoryFiltersTest extends TestCase
{
    use RefreshDatabase;

    private function record(User $user, array $extra = [], string $date = '2026-11-01 08:00:00'): TranslationHistory
    {
        $record = TranslationHistory::create(array_replace([
            'user_id' => $user->id, 'translation_type' => 'document',
            'original_filename' => 'source.pdf', 'translated_filename' => 'translated.pdf',
            'source_language' => 'English', 'target_language' => 'Cebuano',
            'status' => 'completed', 'review_status' => 'pending',
        ], $extra));
        $record->forceFill(['created_at' => $date])->save();

        return $record;
    }

    public function test_default_order_is_global_across_languages_and_breaks_date_ties_by_id(): void
    {
        $user = User::factory()->create();
        $older = $this->record($user, ['original_filename' => 'oldest.pdf'], '2026-11-01 06:00:00');
        $middle = $this->record($user, ['original_filename' => 'middle.pdf', 'target_language' => 'Filipino']);
        $newest = $this->record($user, ['original_filename' => 'newest.pdf']);

        $response = $this->actingAs($user)->get('/history')->assertOk()
            ->assertSeeInOrder(['newest.pdf', 'middle.pdf', 'oldest.pdf']);
        $this->assertSame([$newest->id, $middle->id, $older->id], $response->viewData('records')->pluck('id')->all());
        $this->assertSame('none', $response->viewData('filters')['group']);

        $oldestFirst = $this->get('/history?sort=oldest')->assertOk();
        $this->assertSame([$older->id, $middle->id, $newest->id], $oldestFirst->viewData('records')->pluck('id')->all());
    }

    public function test_search_reaches_older_pages_full_text_and_translated_names_without_leaking_other_users(): void
    {
        $user = User::factory()->create();
        $text = $this->record($user, ['translation_type' => 'text',
            'source_text' => str_repeat('Earlier words ', 20).'Needle', 'translated_text' => 'Dagom'], '2026-10-01 08:00:00');
        $document = $this->record($user, ['translated_filename' => 'NEEDLE-result.pdf'], '2026-10-01 08:00:00');
        for ($i = 0; $i < 51; $i++) {
            $this->record($user);
        }
        $this->record(User::factory()->create(), ['translated_filename' => 'needle-private.pdf']);

        $response = $this->actingAs($user)->get('/history?q=needle')->assertOk();
        $this->assertSame(2, $response->viewData('records')->total());
        $this->assertSame([$document->id, $text->id], $response->viewData('records')->pluck('id')->all());
        $this->assertSame([$text->id], $this->get('/history?q=dagom')->viewData('records')->pluck('id')->all());
    }

    public function test_combined_filters_run_before_pagination_and_survive_page_links(): void
    {
        $user = User::factory()->create();
        $ids = [];
        for ($i = 0; $i < 52; $i++) {
            $ids[] = $this->record($user, ['translation_type' => 'text', 'source_text' => 'needle',
                'review_status' => 'pending'])->id;
        }
        $this->record($user, ['source_text' => 'needle']);
        $this->record($user, ['translation_type' => 'text', 'source_text' => 'needle', 'review_status' => 'verified']);
        $url = '/history?q=needle&type=text&review=pending&sort=oldest&group=none';
        $response = $this->actingAs($user)->get($url)->assertOk()->assertSee('Text only')
            ->assertSee('type=text', false)->assertSee('review=pending', false)->assertSee('sort=oldest', false);
        $this->assertSame(52, $response->viewData('records')->total());
        $this->assertSame(array_slice($ids, 0, 50), $response->viewData('records')->pluck('id')->all());
        $this->assertSame(array_slice($ids, 50), $this->get($url.'&page=2')->viewData('records')->pluck('id')->all());
        $this->assertSame(1, $this->get('/history?type=document')->viewData('records')->total());
    }

    public function test_search_treats_sql_wildcards_as_literal_filename_characters(): void
    {
        $user = User::factory()->create();
        $literal = $this->record($user, ['original_filename' => '100%_final!.pdf']);
        $this->record($user, ['original_filename' => '100-other-final.pdf']);
        $response = $this->actingAs($user)->get('/history?'.http_build_query(['q' => '100%_final!']))->assertOk();
        $this->assertSame([$literal->id], $response->viewData('records')->pluck('id')->all());
    }

    public function test_language_grouping_is_explicit_and_sorts_dates_within_each_group(): void
    {
        $user = User::factory()->create();
        $filipino = $this->record($user, ['target_language' => 'Filipino'], '2026-11-01 09:00:00');
        $olderCebuano = $this->record($user, [], '2026-11-01 07:00:00');
        $newerCebuano = $this->record($user);
        $response = $this->actingAs($user)->get('/history?group=language')->assertOk()
            ->assertSee('Dates are sorted within each language group.');
        $this->assertSame([$newerCebuano->id, $olderCebuano->id, $filipino->id], $response->viewData('records')->pluck('id')->all());
        $response = $this->get('/history?sort=lang-az')->assertOk();
        $this->assertSame([$newerCebuano->id, $olderCebuano->id, $filipino->id], $response->viewData('records')->pluck('id')->all());
    }

    public function test_invalid_filters_are_rejected_and_empty_results_keep_the_controls(): void
    {
        $this->actingAs(User::factory()->create());
        foreach (['sort=arbitrary', 'type=pdf', 'review=completed', 'group=arbitrary', 'q[]=bad'] as $query) {
            $this->getJson('/history?'.$query)->assertUnprocessable();
        }
        $this->get('/history?type=text&q=missing')->assertOk()
            ->assertSee('No translations found.')->assertSee('Apply filters')->assertSee('Clear filters');
    }
}
