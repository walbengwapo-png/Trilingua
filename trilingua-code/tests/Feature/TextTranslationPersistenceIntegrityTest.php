<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\User;
use App\Services\HistoryService;
use App\Services\MetricsService;
use App\Services\Translation\DTO\TranslationResponse;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Notification;
use RuntimeException;
use Tests\TestCase;

class TextTranslationPersistenceIntegrityTest extends TestCase
{
    use RefreshDatabase;

    private function translate(User $user)
    {
        return $this->actingAs($user)->postJson('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'text' => 'Hello, world.',
        ]);
    }

    private function fakeTranslation(): void
    {
        $this->mock(TranslationManager::class, function ($mock) {
            $mock->shouldReceive('translateText')->once()
                ->andReturn(new TranslationResponse(translatedText: 'Kumusta, kalibutan.'));
        });
    }

    public function test_history_failure_returns_usable_unsaved_text(): void
    {
        $user = User::factory()->create();
        $this->fakeTranslation();
        $this->mock(HistoryService::class, function ($mock) {
            $mock->shouldReceive('insertRecord')->once()->andThrow(new RuntimeException('write failed'));
        });

        $this->translate($user)->assertOk()
            ->assertJsonPath('translated', 'Kumusta, kalibutan.')
            ->assertJsonPath('saved', false);
        $this->assertSame(0, TranslationHistory::count());
    }

    public function test_history_success_remains_saved_when_metrics_fail(): void
    {
        Notification::fake();
        $user = User::factory()->create();
        $this->fakeTranslation();
        $this->mock(MetricsService::class, function ($mock) {
            $mock->shouldReceive('persistTextMetrics')->once()
                ->andThrow(new RuntimeException('metrics unavailable'));
        });

        $this->translate($user)->assertOk()
            ->assertJsonPath('translated', 'Kumusta, kalibutan.')
            ->assertJsonPath('saved', true);
        $this->assertSame(1, TranslationHistory::where('user_id', $user->id)->count());
    }
}
