<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\TranslationMetric;
use App\Models\User;
use App\Services\MetricsService;
use App\Services\Translation\DTO\TranslationResponse;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ProviderUsageMetricsTest extends TestCase
{
    use RefreshDatabase;

    private function history(): TranslationHistory
    {
        return TranslationHistory::create([
            'user_id' => User::factory()->create()->id,
            'translation_type' => 'text',
            'source_language' => 'English', 'target_language' => 'Cebuano',
            'source_text' => 'Water', 'translated_text' => 'Tubig',
            'created_at' => now(),
        ]);
    }

    public function test_text_usage_survives_dto_and_persistence(): void
    {
        $usage = ['request_count' => 4, 'input_tokens' => 120, 'output_tokens' => 30,
                  'complete' => true, 'attempts' => [['purpose' => 'quality_review', 'model' => 'gemma4']]];
        $dto = TranslationResponse::fromArray(['translated' => 'Tubig', 'provider_usage' => $usage]);
        $this->assertSame($usage, $dto->toArray()['provider_usage']);
        $this->assertTrue(app(MetricsService::class)->persistTextMetrics($this->history(), $dto->toArray()));
        $row = TranslationMetric::firstOrFail();
        $this->assertSame(4, $row->llm_calls);
        $this->assertSame(120, $row->input_tokens);
        $this->assertSame(30, $row->output_tokens);
        $this->assertSame($usage, $row->provider_usage);
    }

    public function test_document_partial_usage_stays_unknown(): void
    {
        $usage = ['request_count' => 3, 'input_tokens' => null, 'output_tokens' => null,
                  'reported_input_tokens' => 10, 'reported_output_tokens' => 4, 'complete' => false];
        $this->assertTrue(app(MetricsService::class)->persistDocumentMetrics($this->history(), ['provider_usage' => $usage]));
        $row = TranslationMetric::firstOrFail();
        $this->assertSame(3, $row->llm_calls);
        $this->assertNull($row->input_tokens);
        $this->assertNull($row->output_tokens);
        $this->assertFalse($row->provider_usage['complete']);
        $this->assertSame(10, $row->provider_usage['reported_input_tokens']);
    }

    public function test_old_envelope_does_not_invent_one_call_or_zero_tokens(): void
    {
        $this->assertTrue(app(MetricsService::class)->persistTextMetrics($this->history(), ['token_usage' => ['input' => 9]]));
        $row = TranslationMetric::firstOrFail();
        $this->assertNull($row->llm_calls);
        $this->assertNull($row->input_tokens);
        $this->assertNull($row->provider_usage);
    }
    public function test_usage_migration_can_roll_back_and_reapply_on_disposable_database(): void
    {
        app(MetricsService::class)->persistTextMetrics($this->history(), []);
        $migration = require database_path('migrations/2026_10_05_000001_add_provider_usage_to_translation_metrics.php');
        $migration->down();
        $this->assertFalse(\Illuminate\Support\Facades\Schema::hasColumn('translation_metrics', 'provider_usage'));
        $this->assertSame(0, TranslationMetric::firstOrFail()->input_tokens);
        $migration->up();
        $this->assertTrue(\Illuminate\Support\Facades\Schema::hasColumn('translation_metrics', 'provider_usage'));
    }

}
