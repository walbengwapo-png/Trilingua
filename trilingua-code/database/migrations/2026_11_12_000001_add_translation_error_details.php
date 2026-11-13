<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('translation_jobs', fn (Blueprint $table) => $table->jsonb('error_details')->nullable());
        Schema::table('python_document_jobs', function (Blueprint $table): void {
            $table->jsonb('error_details')->nullable();
            $table->jsonb('request_context')->nullable();
        });
        DB::unprepared(file_get_contents(database_path('sql/python_document_jobs_v2.sql')));
    }

    public function down(): void
    {
        DB::unprepared('DROP FUNCTION IF EXISTS public.finish_python_document_job_v2(uuid,uuid,text,text,integer,jsonb)');
        Schema::table('python_document_jobs', fn (Blueprint $table) => $table->dropColumn(['error_details', 'request_context']));
        Schema::table('translation_jobs', fn (Blueprint $table) => $table->dropColumn('error_details'));
    }
};
