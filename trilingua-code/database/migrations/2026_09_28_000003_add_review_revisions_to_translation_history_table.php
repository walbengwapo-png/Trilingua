<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Draft / published revision marker.
     *
     * translation_blocks.current_text is the DRAFT content (edits are audited
     * and applied immediately), while translation_history.storage_path points at
     * the PUBLISHED file. The published file only contains the draft edits after
     * a successful Save & Regenerate. A draft_revision > published_revision means
     * "there are edits that are not in the downloadable file yet" — used to
     * refuse Verify and to label the record as draft-unpublished.
     */
    public function up(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->unsignedBigInteger('draft_revision')->default(0)->after('review_status');
            $table->unsignedBigInteger('published_revision')->default(0)->after('draft_revision');
        });

        // Legacy rows in review_status 'edited' were edited, but there is no
        // durable signal that a regenerated file was ever published for them.
        // Never claim the downloadable file contains those edits: reconciliation-
        // flag them as unpublished drafts (Verify will refuse, and the admin
        // must run Save & Regenerate to confirm the published version).
        DB::table('translation_history')
            ->where('review_status', 'edited')
            ->where('draft_revision', 0)
            ->update(['draft_revision' => 1]);
    }

    public function down(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->dropColumn(['draft_revision', 'published_revision']);
        });
    }
};