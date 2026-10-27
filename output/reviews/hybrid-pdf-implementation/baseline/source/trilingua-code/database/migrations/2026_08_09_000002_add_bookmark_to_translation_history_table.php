<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Persisted bookmarks for translations so a dedicated "Bookmarked" page can
 * show everything a user saved for later. Mirrors the priority field.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->boolean('is_bookmarked')->default(false)->after('is_priority');
            $table->timestampTz('bookmarked_at')->nullable()->after('is_bookmarked');
        });
    }

    public function down(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->dropColumn(['is_bookmarked', 'bookmarked_at']);
        });
    }
};
