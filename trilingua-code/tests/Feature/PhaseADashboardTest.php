<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\TranslationMetric;
use App\Models\User;
use App\Services\MetricsService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class PhaseADashboardTest extends TestCase
{
    use RefreshDatabase;

    private function history(string $type='document'): TranslationHistory
    {
        return TranslationHistory::create(['user_id'=>User::factory()->create()->id,
            'translation_type'=>$type,'source_language'=>'English','target_language'=>'Cebuano',
            'original_filename'=>$type==='document'?'fixture.pdf':null,'created_at'=>now()]);
    }

    private function dashboard()
    {
        return $this->actingAs(User::factory()->create(['is_admin'=>true]))->get('/admin')->assertOk();
    }

    public function test_legacy_samples_are_labelled_and_not_treated_as_comparable_latency(): void
    {
        TranslationMetric::create(['translation_history_id'=>$this->history()->id,'translation_type'=>'document',
            'total_time_ms'=>50,'provider'=>'old-route','model'=>'old-model','created_at'=>now()]);
        $this->dashboard()->assertSee('recorded metric sample')->assertSee('Last observed provider/model')
            ->assertDontSee('Active Provider / Model')->assertViewHas('engineHealth',fn($health)=>
                $health['avg_latency_ms']===null && $health['legacy_samples']===1);
    }

    public function test_compatible_known_ratios_and_attribution_keep_coverage(): void
    {
        app(MetricsService::class)->persistDocumentMetrics($this->history(),[
            'document_type'=>'pdf','mode'=>'fast','cache_hits'=>2,'cache_misses'=>3,
            'blocks_translated'=>4,'retranslated_chunks'=>1,'total_time_ms'=>12,
            'measurement_metadata'=>['schema_version'=>1,'cache_complete'=>true,'cache_unit'=>'lookup',
                'rework_complete'=>true,'rework_unit'=>'block','timing_scope'=>'document_pipeline_elapsed','timing_observed'=>true,
                'observed_providers'=>[['provider'=>'fixture','model'=>'one'],['provider'=>'fixture','model'=>'two']]],
        ]);
        $this->dashboard()->assertViewHas('engineHealth',fn($health)=>
            $health['cache_hit_rate']===40.0 && $health['retranslation_rate']===25.0 &&
            $health['cache_samples']===1 && count($health['last_observed_providers'])===2);
    }

    public function test_unknown_or_zero_denominator_is_unavailable(): void
    {
        app(MetricsService::class)->persistDocumentMetrics($this->history(),[
            'cache_hits'=>0,'cache_misses'=>0,'blocks_translated'=>0,'retranslated_chunks'=>0,
            'measurement_metadata'=>['schema_version'=>1,'cache_complete'=>true,'cache_unit'=>'lookup',
                'rework_complete'=>true,'rework_unit'=>'block'],
        ]);
        app(MetricsService::class)->persistDocumentMetrics($this->history(),[
            'cache_hits'=>2,
            'measurement_metadata'=>['schema_version'=>1,'cache_complete'=>true,'cache_unit'=>'lookup'],
        ]);
        $this->dashboard()->assertSee('Unavailable')->assertViewHas('engineHealth',fn($health)=>
            $health['cache_hit_rate']===null && $health['retranslation_rate']===null);
    }

    public function test_text_and_document_timing_scopes_are_not_averaged_together(): void
    {
        app(MetricsService::class)->persistDocumentMetrics($this->history(),[
            'total_time_ms'=>12,'measurement_metadata'=>['schema_version'=>1,'timing_scope'=>'document_pipeline_elapsed','timing_observed'=>true]]);
        app(MetricsService::class)->persistTextMetrics($this->history('text'),[
            'execution_time_ms'=>50,'measurement_metadata'=>['schema_version'=>1,'timing_scope'=>'translation_result_elapsed','timing_observed'=>true]]);
        $this->dashboard()->assertViewHas('engineHealth',fn($health)=>$health['avg_latency_ms']===null);
    }

    public function test_history_owner_and_cascade_are_preserved(): void
    {
        $history=$this->history();
        app(MetricsService::class)->persistDocumentMetrics($history,['provider'=>'fixture']);
        $this->actingAs(User::factory()->create())->get('/history/'.$history->id.'/view')->assertForbidden();
        $history->delete();
        $this->assertDatabaseCount('translation_metrics',0);
    }
}
