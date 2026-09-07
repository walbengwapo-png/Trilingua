<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->string('storage_backend', 16)->nullable()->after('storage_path');
            $table->string('original_storage_backend', 16)->nullable()->after('original_storage_path');
        });
    }

    public function down(): void
    {
        Schema::table('translation_history', function (Blueprint $table) {
            $table->dropColumn(['storage_backend', 'original_storage_backend']);
        });
    }
};