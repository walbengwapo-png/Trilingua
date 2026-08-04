<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Append-only audit trail for every admin review action.
     *
     * translation_block_id is null for text-translation edits.
     * action values (application-validated): verify | edit | flag
     */
    public function up(): void
    {
        Schema::create('translation_edit_log', function (Blueprint $table) {
            $table->id();
            $table->foreignId('translation_history_id')
                ->constrained('translation_history')->cascadeOnDelete();
            $table->foreignId('translation_block_id')->nullable()
                ->constrained('translation_blocks')->cascadeOnDelete();
            $table->foreignId('admin_id')->constrained('users')->cascadeOnDelete();
            $table->string('action'); // verify | edit | flag
            $table->text('previous_text')->nullable();
            $table->text('new_text')->nullable();
            $table->text('note')->nullable();
            $table->timestampTz('created_at')->useCurrent();

            $table->index(['translation_history_id', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('translation_edit_log');
    }
};