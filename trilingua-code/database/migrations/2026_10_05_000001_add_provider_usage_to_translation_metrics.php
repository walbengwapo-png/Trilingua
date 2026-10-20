<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('translation_metrics', function (Blueprint $table) {
            $table->json('provider_usage')->nullable();
            $table->unsignedInteger('llm_calls')->nullable()->default(null)->change();
            $table->unsignedBigInteger('input_tokens')->nullable()->default(null)->change();
            $table->unsignedBigInteger('output_tokens')->nullable()->default(null)->change();
        });
    }

    public function down(): void
    {
        // The legacy schema requires numbers; detailed unknown markers are lost on rollback.
        foreach (['llm_calls', 'input_tokens', 'output_tokens'] as $column) {
            DB::table('translation_metrics')->whereNull($column)->update([$column => 0]);
        }
        Schema::table('translation_metrics', function (Blueprint $table) {
            $table->dropColumn('provider_usage');
            $table->unsignedInteger('llm_calls')->nullable(false)->default(0)->change();
            $table->unsignedBigInteger('input_tokens')->nullable(false)->default(0)->change();
            $table->unsignedBigInteger('output_tokens')->nullable(false)->default(0)->change();
        });
    }
};
