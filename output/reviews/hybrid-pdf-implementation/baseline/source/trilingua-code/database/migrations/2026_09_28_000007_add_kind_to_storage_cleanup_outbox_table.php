<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Distinguish durable deletion intents for objects whose owning row is gone
     * ('orphan') from durable publish-candidates for objects that were uploaded
     * but whose commit may not have happened yet ('candidate').
     *
     * The cleanup worker (processPending) only ever deletes 'orphan' rows, and
     * the candidate reclaimer only touches 'candidate' rows older than a grace
     * period. A successful publish deletes its candidate row atomically with the
     * pointer commit, so any surviving candidate is never a published file.
     */
    public function up(): void
    {
        Schema::table('storage_cleanup_outbox', function (Blueprint $table) {
            $table->string('kind', 16)->default('orphan')->after('history_id')->index();
        });

        // All pre-existing rows were orphans (deleted-history cleanup intents).
        DB::table('storage_cleanup_outbox')->whereNull('kind')->update(['kind' => 'orphan']);
    }

    public function down(): void
    {
        Schema::table('storage_cleanup_outbox', function (Blueprint $table) {
            $table->dropColumn('kind');
        });
    }
};