<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Add flag-reason columns to translation_history so text-translation flags
     * are queryable (mirrors translation_blocks) and feed admin analytics.
     */
    public function up(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->string('flag_reason')->nullable()->after('reviewed_at');
            $table->text('flag_note')->nullable()->after('flag_reason');
        });
    }

    public function down(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->dropColumn(['flag_reason', 'flag_note']);
        });
    }
};