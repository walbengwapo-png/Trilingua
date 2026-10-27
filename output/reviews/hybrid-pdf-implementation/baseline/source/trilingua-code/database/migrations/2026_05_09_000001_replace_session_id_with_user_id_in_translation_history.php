<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Replace session_id with user_id in translation_history.
 *
 * The translation_history table lives in Supabase (PostgreSQL), not in the
 * local database. This migration file documents the schema change for version
 * control. The equivalent SQL that must be run against the live Supabase
 * instance is:
 *
 * -- Step 1: Add the new user_id column with a foreign key to users
 * ALTER TABLE translation_history ADD COLUMN user_id bigint NOT NULL REFERENCES users(id);
 *
 * -- Step 2: Drop the old composite index on (session_id, created_at)
 * DROP INDEX IF EXISTS translation_history_session_id_created_at_index;
 *
 * -- Step 3: Create a new composite index on (user_id, created_at)
 * CREATE INDEX translation_history_user_id_created_at_index ON translation_history (user_id, created_at);
 *
 * -- Step 4: Drop the now-obsolete session_id column
 * ALTER TABLE translation_history DROP COLUMN session_id;
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            // Add user_id as a foreign key to users.id (bigint unsigned, not null)
            $table->unsignedBigInteger('user_id')->after('id');
            $table->foreign('user_id')->references('id')->on('users');

            // Drop the old session-based index
            $table->dropIndex(['session_id', 'created_at']);

            // Drop the session_id column
            $table->dropColumn('session_id');

            // Add the new user-based composite index
            $table->index(['user_id', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            // Reverse: drop user_id index and foreign key, restore session_id
            $table->dropIndex(['user_id', 'created_at']);
            $table->dropForeign(['user_id']);
            $table->dropColumn('user_id');

            $table->text('session_id')->after('id');
            $table->index(['session_id', 'created_at']);
        });
    }
};
