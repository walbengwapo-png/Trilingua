<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Let users flag a pending translation as a review priority so admins can
 * pick up the most urgent items first. Mirrors the bookmark field.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->boolean('is_priority')->default(false)->after('review_status');
            $table->timestampTz('priority_at')->nullable()->after('is_priority');
        });
    }

    public function down(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->dropColumn(['is_priority', 'priority_at']);
        });
    }
};
