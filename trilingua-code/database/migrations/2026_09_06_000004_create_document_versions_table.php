<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('document_versions', function (Blueprint $table) {
            $table->id();
            $table->foreignId('translation_history_id')->constrained('translation_history')->cascadeOnDelete();
            $table->unsignedInteger('version');
            $table->text('storage_path')->nullable();
            $table->string('translated_filename')->nullable();
            $table->string('artifact_label')->default('Translation output');
            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestampTz('created_at')->useCurrent();
            $table->json('metadata')->nullable();
            $table->unique(['translation_history_id', 'version']);
        });

        Schema::table('translation_history', function (Blueprint $table) {
            $table->foreignId('current_version_id')->nullable()->after('storage_path')
                ->constrained('document_versions')->nullOnDelete();
        });

        // Existing document rows already point to a real output (or an
        // attempted output). Preserve that state as v1 before future review
        // regenerations create v2+, so no artifact is silently overwritten.
        DB::table('translation_history')->where('translation_type', 'document')->orderBy('id')->chunkById(100, function ($documents) {
            foreach ($documents as $document) {
                $versionId = DB::table('document_versions')->insertGetId([
                    'translation_history_id' => $document->id,
                    'version' => 1,
                    'storage_path' => $document->storage_path,
                    'translated_filename' => $document->translated_filename,
                    'artifact_label' => in_array($document->review_status, ['verified', 'edited'], true) ? 'Reviewed final' : 'Translation output',
                    'created_by' => $document->reviewed_by,
                    'created_at' => $document->created_at ?? now(),
                    'metadata' => json_encode(['backfilled' => true]),
                ]);
                DB::table('translation_history')->where('id', $document->id)->update(['current_version_id' => $versionId]);
            }
        });
    }

    public function down(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->dropConstrainedForeignId('current_version_id');
        });
        Schema::dropIfExists('document_versions');
    }
};
