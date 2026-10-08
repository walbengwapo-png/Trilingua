<?php

use App\Support\LegacyPublishedTextBackfill;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Persist the PUBLISHED text of each document block.
     *
     * translation_blocks.current_text is the DRAFT (edits are applied
     * immediately and audited), while translation_history.storage_path points at
     * the PUBLISHED downloadable file. The published file only contains the
     * draft text after a successful Save & Regenerate. This column records the
     * exact block text the published file contains, so a Final/Saved preview can
     * render what is actually downloadable instead of an unpublished draft.
     *
     * Legacy backfill is EVIDENCE BASED and reversible: only unambiguous rows
     * are populated; ambiguous rows stay NULL and keep their downloadable file.
     * See LegacyPublishedTextBackfill for the exact predicate and rationale.
     */
    public function up(): void
    {
        Schema::table('translation_blocks', function (Blueprint $table) {
            $table->text('published_text')->nullable()->after('current_text');
        });

        LegacyPublishedTextBackfill::apply();
    }

    public function down(): void
    {
        Schema::table('translation_blocks', function (Blueprint $table) {
            $table->dropColumn('published_text');
        });
    }
};