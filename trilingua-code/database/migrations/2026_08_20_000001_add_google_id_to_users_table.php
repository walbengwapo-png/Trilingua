<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Add Google OAuth support to the users table.
 *
 * - google_id: nullable, unique identifier returned by Google OAuth.
 * - password:  made nullable so Google-only accounts (which have no local
 *              password) can be created without a hash.
 *
 * Apply against the local/sqlite database only:
 *   php artisan migrate
 *
 * For the production Supabase schema, run the equivalent SQL (see the notes
 * in the batch report) after reviewing the current schema.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->string('google_id')->nullable()->unique()->after('email');
        });

        Schema::table('users', function (Blueprint $table) {
            $table->string('password')->nullable()->change();
        });
    }

    public function down(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->dropUnique(['google_id']);
            $table->dropColumn('google_id');
        });

        Schema::table('users', function (Blueprint $table) {
            $table->string('password')->nullable(false)->change();
        });
    }
};