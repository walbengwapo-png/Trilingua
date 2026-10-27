<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Persist the async queue job UUID on the history row so the translate
     * status endpoint can recover a completed result from the database even
     * after the polling cache entry is gone.
     */
    public function up(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->string('job_id', 36)->nullable()->index()->after('id');
        });
    }

    public function down(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->dropColumn('job_id');
        });
    }
};
