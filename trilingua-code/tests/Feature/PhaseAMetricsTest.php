<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\TranslationMetric;
use App\Models\User;
use App\Services\MetricsService;
use App\Services\Translation\DTO\TranslationResponse;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Notification;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use Illuminate\Database\Schema\Blueprint;
use Tests\TestCase;

class PhaseAMetricsTest extends TestCase
{
    use RefreshDatabase;

    private function history(string $type = 'document'): TranslationHistory
    {
        return TranslationHistory::create([
            'user_id' => User::factory()->create()->id,
            'translation_type' => $type,
            'source_language' => 'English', 'target_language' => 'Cebuano',
            'status' => 'completed', 'created_at' => now(),
        ]);
    }

    public function test_missing_document_usage_and_counts_stay_unknown(): void
    {
        $history = $this->history();
        $this->assertTrue(app(MetricsService::class)->persistDocumentMetrics($history, ['provider' => 'fixture']));
        $metric = TranslationMetric::firstOrFail();
        $this->assertNull($metric->input_tokens);
        $this->assertNull($metric->output_tokens);
        $this->assertNull($metric->llm_calls);
        $this->assertSame('unknown', $metric->measurement_metadata['field_provenance']['input_tokens']);
    }

    public function test_empty_metrics_are_an_explicit_missing_result(): void
    {
        $this->assertFalse(app(MetricsService::class)->persistDocumentMetrics($this->history(), []));
        $this->assertDatabaseCount('translation_metrics', 0);
    }

    public function test_cache_zero_needs_explicit_scope_and_does_not_invent_usage(): void
    {
        app(MetricsService::class)->persistTextMetrics($this->history('text'), [
            'provider' => 'cache', 'model' => 'configured-model',
            'measurement_metadata' => ['schema_version' => 1, 'cache_served' => true,
                'llm_calls' => 0, 'calls_complete' => true, 'calls_scope' => 'translation',
                'calls_provenance' => 'measured locally'],
        ]);
        $metric = TranslationMetric::firstOrFail();
        $this->assertSame(0, $metric->llm_calls);
        $this->assertNull($metric->input_tokens);
        $this->assertSame([], $metric->measurement_metadata['observed_providers']);
    }

    public function test_cached_translation_with_unobserved_review_does_not_claim_zero_total(): void
    {
        app(MetricsService::class)->persistTextMetrics($this->history('text'), [
            'provider' => 'cache',
            'measurement_metadata' => ['schema_version' => 1, 'cache_served' => true,
                'llm_calls' => 0, 'calls_complete' => false, 'calls_scope' => 'operation',
                'calls_provenance' => 'unknown'],
        ]);
        $this->assertNull(TranslationMetric::firstOrFail()->llm_calls);
    }

    public function test_simple_observed_request_and_partial_reported_usage_survive(): void
    {
        app(MetricsService::class)->persistTextMetrics($this->history('text'), [
            'provider' => 'fixture', 'model' => 'model-one', 'token_usage' => ['input' => 12],
            'measurement_metadata' => ['schema_version' => 1, 'llm_calls' => 1,
                'calls_complete' => true, 'calls_scope' => 'translation', 'calls_provenance' => 'measured locally',
                'usage_provenance' => ['input' => 'provider-reported', 'output' => 'unknown'],
                'observed_providers' => [['provider' => 'fixture', 'model' => 'model-one']]],
        ]);
        $metric = TranslationMetric::firstOrFail();
        $this->assertSame(1, $metric->llm_calls);
        $this->assertSame(12, $metric->input_tokens);
        $this->assertNull($metric->output_tokens);
        $this->assertSame('provider-reported', $metric->measurement_metadata['field_provenance']['input_tokens']);
    }

    public function test_estimated_usage_is_kept_separate_from_reported_tokens(): void
    {
        app(MetricsService::class)->persistTextMetrics($this->history('text'), [
            'token_usage' => ['input' => 3, 'output' => 4],
            'measurement_metadata' => ['schema_version' => 1,
                'usage_provenance' => ['input' => 'estimated', 'output' => 'estimated'],
                'usage_method' => ['input' => 'word-proxy-v1', 'output' => 'word-proxy-v1']],
        ]);
        $metric = TranslationMetric::firstOrFail();
        $this->assertNull($metric->input_tokens);
        $this->assertNull($metric->output_tokens);
        $this->assertSame(3, $metric->measurement_metadata['estimated_usage']['input']['value']);
        $this->assertSame('word-proxy-v1', $metric->measurement_metadata['estimated_usage']['input']['method']);
    }

    public function test_provider_pairs_are_preserved_without_content_or_raw_errors(): void
    {
        $pairs = [['provider' => 'primary', 'model' => 'one'], ['provider' => 'primary', 'model' => 'two'],
                  ['provider' => 'fallback', 'model' => 'three']];
        app(MetricsService::class)->persistDocumentMetrics($this->history(), [
            'measurement_metadata' => ['schema_version' => 1, 'observed_providers' => $pairs,
                'prompt' => 'DO NOT STORE', 'raw_error' => 'DO NOT STORE'],
        ]);
        $metadata = TranslationMetric::firstOrFail()->measurement_metadata;
        $this->assertSame($pairs, $metadata['observed_providers']);
        $this->assertStringNotContainsString('DO NOT STORE', json_encode($metadata));
    }

    public function test_invalid_numbers_are_not_coerced_to_zero(): void
    {
        app(MetricsService::class)->persistDocumentMetrics($this->history(), [
            'total_time_ms' => INF, 'cache_hits' => 'not-a-number', 'cache_misses' => -1,
            'measurement_metadata' => ['schema_version' => 1],
        ]);
        $metric = TranslationMetric::firstOrFail();
        $this->assertNull($metric->total_time_ms);
        $this->assertNull($metric->cache_hits);
        $this->assertNull($metric->cache_misses);
        $this->assertSame('invalid', $metric->measurement_metadata['completeness']);
    }

    public function test_real_text_mapping_preserves_usage_metadata_through_controller(): void
    {
        Notification::fake();
        Http::fake(['*/translate/text'=>Http::response([
            'translated'=>'Kumusta','provider'=>'fixture','model'=>'one','mode'=>'fast',
            'token_usage'=>['input'=>12,'output'=>3],
            'measurement_metadata'=>['schema_version'=>1,
                'usage_provenance'=>['input'=>'provider-reported','output'=>'estimated'],
                'usage_method'=>['output'=>'word-proxy-v1'],
                'observed_providers'=>[['provider'=>'fixture','model'=>'one']]],
        ])]);
        $this->actingAs(User::factory()->create())->postJson('/translate',[
            'text'=>'España niño','source_lang'=>'English','target_lang'=>'Cebuano','mode'=>'fast',
        ])->assertOk()->assertJsonPath('saved',true)
            ->assertJsonPath('measurement_metadata.usage_provenance.input','provider-reported');
        $metric=TranslationMetric::firstOrFail();
        $this->assertSame(12,$metric->input_tokens);
        $this->assertNull($metric->output_tokens);
        $this->assertSame(3,$metric->measurement_metadata['estimated_usage']['output']['value']);
        $this->assertSame(2,TranslationHistory::firstOrFail()->source_word_metadata['count']);
    }

    public function test_upgrade_preserves_legacy_zero_without_creating_new_tables(): void
    {
        config(['database.connections.phase_a_upgrade'=>['driver'=>'sqlite','database'=>':memory:','prefix'=>'','foreign_key_constraints'=>true]]);
        $original=DB::getDefaultConnection();
        DB::setDefaultConnection('phase_a_upgrade');
        try {
            Schema::create('translation_history',function(Blueprint $table): void { $table->id(); });
            DB::table('translation_history')->insert(['id'=>1]);
            $old=require database_path('migrations/2026_09_03_000002_create_translation_metrics_table.php');
            $old->up();
            DB::table('translation_metrics')->insert(['translation_history_id'=>1]);
            $before=Schema::getTableListing();
            $migration=require database_path('migrations/2026_10_19_000001_correct_processing_measurements.php');
            $migration->up();
            $this->assertSame($before,Schema::getTableListing());
            $legacy=DB::table('translation_metrics')->first();
            $this->assertSame(0,$legacy->input_tokens);
            $this->assertNull($legacy->measurement_metadata);
            DB::table('translation_metrics')->insert(['translation_history_id'=>1,'input_tokens'=>null,'llm_calls'=>null]);
            $new=DB::table('translation_metrics')->orderByDesc('id')->first();
            $this->assertNull($new->input_tokens);
            $this->assertNull($new->llm_calls);
        } finally {
            DB::purge('phase_a_upgrade');
            DB::setDefaultConnection($original);
        }
    }

    public function test_unknown_version_and_oversized_attribution_remain_explicitly_invalid(): void
    {
        app(MetricsService::class)->persistDocumentMetrics($this->history(),[
            'measurement_metadata'=>['schema_version'=>99,'observed_providers'=>[['provider'=>'unverified','model'=>'one']]],
        ]);
        $first=TranslationMetric::firstOrFail();
        $this->assertSame([],$first->measurement_metadata['observed_providers']);
        $this->assertSame('invalid',$first->measurement_metadata['completeness']);
        $pairs=array_map(fn($n)=>['provider'=>'fixture','model'=>'model-'.$n],range(1,40));
        app(MetricsService::class)->persistDocumentMetrics($this->history(),[
            'measurement_metadata'=>['schema_version'=>1,'observed_providers'=>$pairs,'raw_error'=>'do not retain'],
        ]);
        $metadata=TranslationMetric::orderByDesc('id')->firstOrFail()->measurement_metadata;
        $this->assertSame('invalid',$metadata['completeness']);
        $this->assertFalse($metadata['attribution_complete']);
        $this->assertLessThanOrEqual(16,count($metadata['observed_providers']));
        $this->assertLessThanOrEqual(8192,strlen(json_encode($metadata)));
        $this->assertArrayNotHasKey('raw_error',$metadata);
    }

    public function test_public_text_metadata_keeps_only_known_categories_and_safe_fields(): void
    {
        $response=TranslationResponse::fromArray(['translated'=>'Output',
            'token_usage'=>['input'=>'invalid','output'=>4,'prompt'=>'DO NOT EXPOSE'],
            'measurement_metadata'=>['schema_version'=>1,'prompt'=>'DO NOT EXPOSE',
                'usage_provenance'=>['input'=>'invented','output'=>'estimated'],
                'usage_method'=>['output'=>'word-proxy-v1']]]);
        $public=$response->toArray();
        $this->assertSame(['output'=>4],$public['token_usage']);
        $this->assertSame('unknown',$public['measurement_metadata']['usage_provenance']['input']);
        $this->assertSame('estimated',$public['measurement_metadata']['usage_provenance']['output']);
        $this->assertStringNotContainsString('DO NOT EXPOSE',json_encode($public));
        $this->assertTrue($response->measurementMetadata['invalid']);
    }
}
