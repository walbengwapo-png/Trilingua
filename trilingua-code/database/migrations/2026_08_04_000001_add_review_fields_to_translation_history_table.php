<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Add admin-review fields to the translation_history table.
     *
     * status values (application-validated, see App\Support\ReviewStatus):
     * pending | verified | edited | flagged
     */
    public function up(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->string('review_status')->default('pending')->after('translated_text');
            $table->unsignedInteger('quality_score')->nullable()->after('review_status');
            $table->foreignId('reviewed_by')->nullable()->after('quality_score')
                ->constrained('users')->nullOnDelete();
            $table->timestampTz('reviewed_at')->nullable()->after('reviewed_by');
        });
    }

    public function down(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->dropConstrainedForeignId('reviewed_by');
            $table->dropColumn(['review_status', 'quality_score', 'reviewed_at']);
        });
    }
};