<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * One row per translation run capturing the AI engine metrics that the Python
 * FastAPI engine returns (DocumentContext.summary()).
 *
 * These are surfaced on the admin dashboard: engine latency, LLM call count,
 * cache hit rate, retranslation rate (a direct translation-quality proxy) and
 * which provider/model handled the run. Rows are append-only for auditability
 * and link back to the owning translation via translation_history_id.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('translation_metrics', function (Blueprint $table) {
            $table->id();
            $table->foreignId('translation_history_id')
                ->constrained('translation_history')
                ->cascadeOnDelete();
            $table->string('translation_type')->default('text');
            $table->string('provider')->nullable();
            $table->string('model')->nullable();
            $table->string('mode')->nullable();
            $table->decimal('total_time_ms', 12, 1)->nullable();
            $table->unsignedInteger('llm_calls')->default(0);
            $table->decimal('llm_total_time_ms', 12, 1)->nullable();
            $table->unsignedInteger('total_blocks')->default(0);
            $table->unsignedInteger('blocks_translated')->default(0);
            $table->unsignedInteger('blocks_cached')->default(0);
            $table->unsignedInteger('blocks_passthrough')->default(0);
            $table->unsignedInteger('retranslated_chunks')->default(0);
            $table->unsignedInteger('cache_hits')->default(0);
            $table->unsignedInteger('cache_misses')->default(0);
            $table->unsignedBigInteger('input_tokens')->default(0);
            $table->unsignedBigInteger('output_tokens')->default(0);
            $table->string('document_type')->nullable();
            $table->timestamp('created_at')->nullable();

            $table->index('translation_type');
            $table->index('created_at');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('translation_metrics');
    }
};