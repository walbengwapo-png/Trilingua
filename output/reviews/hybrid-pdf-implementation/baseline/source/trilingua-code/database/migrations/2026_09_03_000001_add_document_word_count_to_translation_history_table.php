<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Real source word count for document translations.
 *
 * Previously the dashboard estimated 250 words per document. Now that the
 * per-block source text is persisted we can sum actual words so the "Words
 * Translated" metric is meaningful. Populated by BlockService at persist time.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->unsignedInteger('document_word_count')->nullable()->after('job_id');
        });
    }

    public function down(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->dropColumn('document_word_count');
        });
    }
};