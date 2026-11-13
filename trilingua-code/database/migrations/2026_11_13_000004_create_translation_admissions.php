<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration {
    public function up(): void
    {
        Schema::create('translation_admissions', function (Blueprint $table): void {
            $table->foreignId('user_id')->primary()->constrained()->cascadeOnDelete();
            $table->uuid('owner')->nullable();
            $table->string('phase', 24)->default('idle');
            $table->foreignId('translation_job_id')->nullable()->constrained()->nullOnDelete();
            $table->unsignedInteger('expected_attempt')->nullable();
            $table->timestampTz('heartbeat_at')->nullable();
            $table->timestampTz('deadline_at')->nullable();
            $table->index('translation_job_id');
        });
        if (DB::getDriverName() === 'pgsql') {
            DB::statement('ALTER TABLE public.translation_admissions ENABLE ROW LEVEL SECURITY');
            DB::statement('REVOKE ALL ON public.translation_admissions FROM PUBLIC, anon, authenticated');
            DB::statement('GRANT SELECT, INSERT, UPDATE, DELETE ON public.translation_admissions TO service_role');
        }
    }

    public function down(): void
    {
        if (DB::table('translation_admissions')->whereNotNull('owner')->exists()) {
            throw new RuntimeException('Drain/reconcile translation admissions before rollback.');
        }
        Schema::dropIfExists('translation_admissions');
    }
};
