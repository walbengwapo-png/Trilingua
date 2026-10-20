<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\TranslationMetric;
use App\Models\User;
use App\Services\BlockService;
use App\Services\HistoryService;
use App\Services\TranslationStatsService;
use App\Support\SourceWordCounter;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\DataProvider;
use Tests\TestCase;

class PhaseASourceWordsTest extends TestCase
{
    use RefreshDatabase;

    public static function words(): array
    {
        return [
            ['Ang bata nagtuon.',3], ['España niño',2], ['café niño',2], ["cafe\u{0301} niño",2],
            ["don't l’amour mag-aaral",3], ["'bata' -- bata",2], ['foo--bar',2], ['bata—guro',2],
            ['Bata 123 456',1], ['3.14 95% 2026-10-19',0], ['Grade7 ika-3 10kg',3],
            ['bata,guro;aklat!',3], ['https://a.example/x',4], ['... + =',0], ['',0],
            ['bata‐guro bata‑guro',2], ["\u{0301}",0],
        ];
    }

    #[DataProvider('words')]
    public function test_unicode_rule(string $source, int $expected): void
    {
        $this->assertSame($expected, SourceWordCounter::count($source));
    }

    private function history(): TranslationHistory
    {
        return TranslationHistory::create(['user_id'=>User::factory()->create()->id,
            'translation_type'=>'document','source_language'=>'English','target_language'=>'Cebuano',
            'status'=>'completed','created_at'=>now()]);
    }

    public function test_blocks_count_validated_source_with_method(): void
    {
        $history=$this->history();
        app(BlockService::class)->persistBlocks($history,[['source_text'=>'España niño','text'=>'Translated words']]);
        $history->refresh();
        $this->assertSame(2,$history->document_word_count);
        $this->assertSame('source-words-unicode-v1',$history->source_word_metadata['method']);
        $this->assertSame('derived',$history->source_word_metadata['provenance']);
        $this->assertSame('unknown',$history->source_word_metadata['extraction_coverage']);
    }

    public function test_output_fallback_does_not_become_source_words(): void
    {
        $history=$this->history();
        app(BlockService::class)->persistBlocks($history,[['text'=>'Translated output only']]);
        $this->assertNull($history->refresh()->document_word_count);
        $this->assertSame('missing',$history->source_word_metadata['completeness']);
    }

    public function test_verified_empty_source_is_zero(): void
    {
        $history=$this->history();
        app(BlockService::class)->persistBlocks($history,[['source_text'=>'','text'=>'']]);
        $this->assertSame(0,$history->refresh()->document_word_count);
    }

    public function test_partial_source_keeps_a_labelled_subtotal_not_a_complete_total(): void
    {
        $history=$this->history();
        app(BlockService::class)->persistBlocks($history,[['source_text'=>'Ang bata','text'=>'Output'],['text'=>'Unknown source']]);
        $this->assertNull($history->refresh()->document_word_count);
        $this->assertSame(2,$history->source_word_metadata['known_words']);
        $this->assertSame('partial',$history->source_word_metadata['completeness']);
    }

    public function test_regeneration_does_not_rewrite_original_source_volume(): void
    {
        $history=$this->history();
        $service=app(BlockService::class);
        $service->persistBlocks($history,[['source_text'=>'Ang bata','text'=>'Output']]);
        $metric=TranslationMetric::create(['translation_history_id'=>$history->id,
            'translation_type'=>'document','provider'=>'original-fixture','llm_calls'=>2]);
        $original=$history->refresh()->source_word_metadata;
        $history->blocks()->delete();
        $service->persistBlocks($history,[['source_text'=>'Different reconstruction source words','text'=>'Output']]);
        $this->assertSame($original,$history->refresh()->source_word_metadata);
        $this->assertSame(2,$history->document_word_count);
        $this->assertDatabaseCount('translation_metrics',1);
        $this->assertSame('original-fixture',$metric->refresh()->provider);
        $this->assertSame(2,$metric->llm_calls);
    }

    public function test_new_text_counts_and_legacy_totals_are_reported_separately(): void
    {
        $user=User::factory()->create();
        TranslationHistory::create(['user_id'=>$user->id,'translation_type'=>'document','document_word_count'=>500,
            'source_language'=>'English','target_language'=>'Cebuano','created_at'=>now()]);
        app(HistoryService::class)->insertRecord(['user_id'=>$user->id,'translation_type'=>'text',
            'source_language'=>'English','target_language'=>'Cebuano','source_text'=>'España niño',
            'translated_text'=>'Output','review_status'=>'pending']);
        $stats=TranslationStatsService::forUser($user->id);
        $this->assertSame(2,$stats['sourceWords']['known_words']);
        $this->assertSame(1,$stats['sourceWords']['complete_records']);
        $this->assertSame(500,$stats['sourceWords']['legacy_words']);
        $this->assertSame(1,$stats['sourceWords']['legacy_records']);
        $records=TranslationHistory::where('user_id',$user->id)->get()->toArray();
        $this->assertSame(TranslationStatsService::compute($records),$stats['core']);

        // Separate fixture: the same Unicode method across current/prior periods.
        $periodUser=User::factory()->create();
        foreach ([0,40] as $daysAgo) {
            $record=app(HistoryService::class)->insertRecord(['user_id'=>$periodUser->id,'translation_type'=>'text',
                'source_language'=>'English','target_language'=>'Cebuano','source_text'=>'España niño',
                'translated_text'=>'Output','review_status'=>'pending']);
            $record->forceFill(['created_at'=>now()->subDays($daysAgo)])->save();
        }
        $period=TranslationStatsService::forUser($periodUser->id);
        $this->assertSame(4,$period['sourceWords']['known_words']);
        $this->assertSame(0,$period['deltas']['wordsDelta']);
    }

    public function test_invalid_unicode_is_unavailable_instead_of_a_fake_zero(): void
    {
        $metadata=SourceWordCounter::measure("\xFF");
        $this->assertNull($metadata['count']);
        $this->assertSame('unknown',$metadata['provenance']);
    }
}
