<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        // Legacy OCR options are resolved from inert queue metadata at retry time, never guessed.
        Schema::table('translation_jobs', fn (Blueprint $table) => $table->string('ocr_mode', 16)->nullable());
        DB::statement('CREATE UNIQUE INDEX translation_history_user_job_unique ON public.translation_history (user_id, job_id) WHERE job_id IS NOT NULL');
    }

    public function down(): void
    {
        DB::statement('DROP INDEX IF EXISTS public.translation_history_user_job_unique');
        Schema::table('translation_jobs', fn (Blueprint $table) => $table->dropColumn('ocr_mode'));
    }
};
