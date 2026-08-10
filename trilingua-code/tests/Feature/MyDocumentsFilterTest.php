<?php

namespace Tests\Feature;

use App\Services\HistoryService;
use App\Models\TranslationHistory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * My Documents page — language pair filter and dropdown contents.
 */
class MyDocumentsFilterTest extends TestCase
{
    use RefreshDatabase;

    private function makeDoc(User $user, string $source, string $target, string $name = 'doc.pdf'): array
    {
        return [
            'id'                    => random_int(1, 999999),
            'user_id'               => $user->id,
            'translation_type'      => 'document',
            'original_filename'     => $name,
            'translated_filename'   => 'doc_ceb.pdf',
            'source_language'       => $source,
            'target_language'       => $target,
            'created_at'            => now()->toIso8601String(),
            'review_status'         => 'pending',
            'is_priority'           => false,
            'is_bookmarked'         => false,
        ];
    }

    private function mockService(array $documents): void
    {
        $this->mock(HistoryService::class, function ($mock) use ($documents) {
            $mock->shouldReceive('getOriginalsWithTranslations')
                 ->once()
                 ->andReturn([]);
            $mock->shouldReceive('getHistory')
                 ->once()
                 ->andReturn($documents);
        });
    }

    public function test_language_filter_uses_pairs_not_single_languages(): void
    {
        $user = User::factory()->create();
        $this->mockService([
            $this->makeDoc($user, 'English', 'Cebuano', 'a.pdf'),
            $this->makeDoc($user, 'English', 'Filipino', 'b.pdf'),
        ]);

        $response = $this->actingAs($user)->get('/documents');

        $response->assertOk();
        $response->assertSee('English → Cebuano', false);
        $response->assertSee('English → Filipino', false);
        $response->assertSee('data-lang="English → Cebuano"', false);
        $response->assertSee('data-lang="English → Filipino"', false);
        $response->assertDontSee('<option value="Tagalog">', false);
        $response->assertDontSee('<option value="English">English</option>', false);
    }

    public function test_empty_documents_shows_empty_state_without_pair_dropdown(): void
    {
        $user = User::factory()->create();
        $this->mockService([]);

        $response = $this->actingAs($user)->get('/documents');

        $response->assertOk();
        $response->assertSee('You have no documents yet.', false);
        $response->assertDontSee('All Language Pairs', false);
    }
}
