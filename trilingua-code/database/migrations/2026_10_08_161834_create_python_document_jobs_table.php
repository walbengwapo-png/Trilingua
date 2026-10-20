<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('python_document_jobs', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->string('fingerprint', 64);
            $table->string('filename');
            $table->string('input_path');
            $table->json('options');
            $table->string('status')->default('queued')->index();
            $table->uuid('lease_id')->nullable();
            $table->timestampTz('lease_until')->nullable();
            $table->timestampTz('deadline')->nullable();
            $table->string('result_path')->nullable();
            $table->text('error')->nullable();
            $table->unsignedSmallInteger('error_status')->nullable();
            $table->boolean('provider_stop_released')->default(false);
            $table->boolean('acknowledged')->default(false);
            $table->timestampTz('created_at')->useCurrent();
            $table->timestampTz('updated_at')->useCurrent();
        });

        Schema::table('translation_jobs', fn (Blueprint $table) => $table->uuid('engine_job_uuid')->nullable());
        if (DB::getDriverName() === 'pgsql') {
            DB::unprepared(file_get_contents(database_path('sql/python_document_jobs.sql')));
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        if (DB::getDriverName() === 'pgsql') {
            DB::unprepared('DROP FUNCTION IF EXISTS public.claim_python_document_job(), public.renew_python_document_job(uuid, uuid), public.finish_python_document_job(uuid, uuid, text, text, integer)');
        }
        Schema::table('translation_jobs', fn (Blueprint $table) => $table->dropColumn('engine_job_uuid'));
        Schema::dropIfExists('python_document_jobs');
    }
};
