<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * R4 completion integrity: once the worker durably stores the translated
 * object, its key/backend are recorded on the state-machine row BEFORE any
 * history/block database writes. Object storage cannot join a DB transaction,
 * so these paths are what a later retry reuses (idempotent) and what a cleanup
 * job could use to remove a stranded object.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('translation_jobs', function (Blueprint $table) {
            $table->string('translated_storage_path')->nullable()->after('original_storage_backend');
            $table->string('translated_storage_backend', 16)->nullable()->after('translated_storage_path');
        });
    }

    public function down(): void
    {
        Schema::table('translation_jobs', function (Blueprint $table) {
            $table->dropColumn(['translated_storage_path', 'translated_storage_backend']);
        });
    }
};