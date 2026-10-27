<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Per-block rows for document translations.
     *
     * ai_translated_text is IMMUTABLE — admin edits live in current_text.
     * status values (application-validated, see App\Support\ReviewStatus):
     * pending | verified | edited | flagged
     */
    public function up(): void
    {
        Schema::create('translation_blocks', function (Blueprint $table) {
            $table->id();
            $table->foreignId('translation_history_id')
                ->constrained('translation_history')->cascadeOnDelete();
            $table->unsignedInteger('block_index');
            $table->string('block_type')->default('paragraph');
            $table->text('source_text');
            $table->text('ai_translated_text');
            $table->text('current_text');
            $table->unsignedInteger('quality_score')->nullable();
            $table->json('quality_issues')->nullable();
            $table->string('status')->default('pending');
            $table->string('flag_reason')->nullable();
            $table->text('flag_note')->nullable();
            $table->foreignId('edited_by')->nullable()
                ->constrained('users')->nullOnDelete();
            $table->timestampTz('edited_at')->nullable();
            $table->timestampTz('created_at')->useCurrent();

            $table->index(['translation_history_id', 'block_index']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('translation_blocks');
    }
};