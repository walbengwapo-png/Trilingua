<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Backfill review_status for existing translation_history records.
     *
     * Records created before the review_status column was added have NULL.
     * We set them to 'pending' so they appear in the admin dashboard.
     */
    public function up(): void
    {
        DB::table('translation_history')
            ->whereNull('review_status')
            ->update(['review_status' => 'pending']);
    }

    public function down(): void
    {
        // No rollback needed — we can't distinguish original NULLs from
        // intentionally-set 'pending' values after this migration.
    }
};