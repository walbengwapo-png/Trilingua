<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('translation_metrics', function (Blueprint $table): void {
            foreach (['llm_calls', 'total_blocks', 'blocks_translated', 'blocks_cached',
                'blocks_passthrough', 'retranslated_chunks', 'cache_hits', 'cache_misses'] as $field) {
                $table->unsignedInteger($field)->nullable()->default(null)->change();
            }
            $table->unsignedBigInteger('input_tokens')->nullable()->default(null)->change();
            $table->unsignedBigInteger('output_tokens')->nullable()->default(null)->change();
            $table->json('measurement_metadata')->nullable();
        });
        Schema::table('translation_history', function (Blueprint $table): void {
            $table->json('source_word_metadata')->nullable();
        });
    }

    public function down(): void
    {
        // A code rollback can ignore these fields; dropping them would erase provenance.
        throw new LogicException('Retain additive processing metadata on rollback; destructive downgrade requires a reviewed data migration.');
    }
};
