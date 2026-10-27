<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('translation_history', function (Blueprint $table) {
            $table->id();
            $table->text('session_id');
            $table->text('translation_type')->default('document'); // 'document' or 'text'
            // Document-only fields (nullable for text translations)
            $table->text('original_filename')->nullable();
            $table->text('translated_filename')->nullable();
            $table->text('storage_path')->nullable();
            $table->timestampTz('signed_url_expires_at')->nullable();
            // Text-only fields (nullable for document translations)
            $table->text('source_text')->nullable();
            $table->text('translated_text')->nullable();
            // Common fields
            $table->text('source_language');
            $table->text('target_language');
            $table->timestampTz('created_at')->useCurrent();

            $table->index(['session_id', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('translation_history');
    }
};
