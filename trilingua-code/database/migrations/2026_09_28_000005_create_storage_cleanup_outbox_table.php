<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Durable record of storage objects left behind by a deleted history row.
     *
     * The row removal and the list of backend/path pairs that must be cleaned
     * are recorded in the same DB transaction (see HistoryService::deleteRecord),
     * so a storage outage can never orphan user data that is no longer
     * discoverable. Entries are unique per backend/path; a clean delete flips
     * the row to done, and anything that keeps failing stays pending with a
     * visible retry counter for translations:cleanup-storage.
     */
    public function up(): void
    {
        Schema::create('storage_cleanup_outbox', function (Blueprint $table) {
            $table->id();
            $table->unsignedBigInteger('history_id')->nullable()->index();
            $table->string('backend', 16);
            $table->string('path');
            $table->string('status', 16)->default('pending')->index();
            $table->unsignedInteger('attempts')->default(0);
            $table->text('last_error')->nullable();
            $table->timestamps();

            $table->unique(['backend', 'path']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('storage_cleanup_outbox');
    }
};