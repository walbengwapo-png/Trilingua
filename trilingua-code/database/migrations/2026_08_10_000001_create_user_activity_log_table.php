<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Append-only audit trail for login, logout, and account changes.
     *
     * user_id is nullable so failed logins (no matched user) are still recorded.
     */
    public function up(): void
    {
        Schema::create('user_activity_log', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->nullable()
                ->constrained('users')->nullOnDelete();
            $table->string('attempted_email')->nullable();
            $table->string('action'); // login_success | login_failed | logout | account_updated | password_changed
            $table->string('ip_address', 45)->nullable();
            $table->text('user_agent')->nullable();
            $table->text('previous_value')->nullable();
            $table->text('new_value')->nullable();
            $table->text('note')->nullable();
            $table->timestampTz('created_at')->useCurrent();

            $table->index(['user_id', 'created_at']);
            $table->index(['action', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('user_activity_log');
    }
};