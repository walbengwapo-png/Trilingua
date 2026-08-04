<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Store the Python sidecar (structural + review metadata captured at
     * translate time) so admin "Save & Regenerate" can re-render the document
     * without re-running extraction/analysis/translation.
     */
    public function up(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->json('sidecar')->nullable()->after('translated_text');
        });
    }

    public function down(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->dropColumn('sidecar');
        });
    }
};
