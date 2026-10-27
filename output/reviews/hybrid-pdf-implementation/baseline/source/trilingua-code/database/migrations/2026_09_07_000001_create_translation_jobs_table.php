<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('translation_jobs', function (Blueprint $table) {
            $table->id();
            $table->string('uuid', 36)->unique();
            $table->unsignedBigInteger('user_id');
            $table->string('payload_hash', 64);
            $table->string('original_name');
            $table->string('original_ext', 16)->default('');
            $table->string('source_lang');
            $table->string('target_lang');
            $table->string('pdf_column_mode', 16)->default('auto');
            $table->string('mode', 16)->default('balanced');
            $table->unsignedBigInteger('parent_document_id')->nullable();
            $table->unsignedBigInteger('translation_history_id')->nullable();
            $table->unsignedBigInteger('file_size')->nullable();
            $table->string('original_storage_path')->nullable();
            $table->string('original_storage_backend', 16)->nullable();
            $table->string('storage_path')->nullable();
            $table->string('storage_backend', 16)->nullable();
            $table->string('status', 16)->default('created')->index();
            $table->integer('progress')->default(0);
            $table->integer('attempts')->default(0);
            $table->text('error')->nullable();
            $table->timestamp('last_heartbeat_at')->nullable();
            $table->timestamp('started_at')->nullable();
            $table->timestamp('completed_at')->nullable();
            $table->timestamps();

            $table->index('user_id');
            $table->index(['user_id', 'created_at']);
        });

        // Active-job-only deduplication: uniqueness is enforced ONLY while a job
        // is created/queued/processing, so re-translating an already-completed
        // file remains possible (or callers may explicitly reuse the completed
        // result). Partial index is supported by both PostgreSQL and SQLite.
        DB::statement(
            "create unique index translation_jobs_active_unique
             on translation_jobs (user_id, payload_hash)
             where status in ('created', 'queued', 'processing')"
        );
    }

    public function down(): void
    {
        DB::statement('drop index if exists translation_jobs_active_unique');
        Schema::dropIfExists('translation_jobs');
    }
};