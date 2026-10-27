<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('translation_jobs', function (Blueprint $table) {
            $table->boolean('recoverable')->nullable()->after('storage_backend');
            $table->timestamp('terminal_failed_at')->nullable()->after('recoverable');
        });
    }

    public function down(): void
    {
        Schema::table('translation_jobs', function (Blueprint $table) {
            $table->dropColumn(['terminal_failed_at', 'recoverable']);
        });
    }
};