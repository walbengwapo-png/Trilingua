<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Add document relationship fields to translation_history.
 *
 * This migration adds:
 * - original_storage_path: path in Supabase Storage for the original uploaded file
 * - parent_document_id: FK self-reference linking a translation to its source document
 * - file_size: size of the original file in bytes
 * - status: translation status (completed, failed, etc.)
 *
 * The equivalent SQL that must be run against the live Supabase instance is:
 *
 * ALTER TABLE translation_history
 *   ADD COLUMN original_storage_path text,
 *   ADD COLUMN parent_document_id bigint REFERENCES translation_history(id),
 *   ADD COLUMN file_size bigint,
 *   ADD COLUMN status text NOT NULL DEFAULT 'completed';
 *
 * CREATE INDEX translation_history_parent_document_id_index
 *   ON translation_history (parent_document_id);
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->text('original_storage_path')->nullable()->after('storage_path');
            $table->unsignedBigInteger('parent_document_id')->nullable()->after('original_storage_path');
            $table->foreign('parent_document_id')->references('id')->on('translation_history')->nullOnDelete();
            $table->bigInteger('file_size')->nullable()->after('parent_document_id');
            $table->text('status')->default('completed')->after('file_size');
        });
    }

    public function down(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->dropForeign(['parent_document_id']);
            $table->dropIndex(['parent_document_id']);
            $table->dropColumn([
                'original_storage_path',
                'parent_document_id',
                'file_size',
                'status',
            ]);
        });
    }
};