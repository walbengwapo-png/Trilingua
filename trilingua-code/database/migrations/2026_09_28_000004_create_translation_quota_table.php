<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Daily per-user upload quota ledger.
     *
     * The quota is charged at ACCEPTANCE (created/queued translation_jobs),
     * not at completion: provider + queue capacity is consumed the moment work
     * is accepted. The old rule counted completed history rows, so concurrent
     * uploads could all pass before anything was written. This table replaces
     * that read-then-act check with an atomic per-user/day reservation — the
     * intake does a conditional increment whose WHERE is evaluated under the
     * row lock, so simultaneous requests cannot jointly exceed the cap.
     */
    public function up(): void
    {
        Schema::create('translation_quota', function (Blueprint $table) {
            $table->id();
            $table->unsignedBigInteger('user_id');
            $table->date('quota_day');
            $table->unsignedBigInteger('files')->default(0);
            $table->unsignedBigInteger('bytes')->default(0);
            $table->timestamps();

            $table->unique(['user_id', 'quota_day']);
        });

        $this->backfillTodayFromAcceptedWork();
    }

    /**
     * Seed today's ledger from things already accepted before this migration:
     * every document translation_job created today, plus document history rows
     * created today that have no owning job (legacy intake) — never double
     * counting a job that already produced its history row.
     */
    private function backfillTodayFromAcceptedWork(): void
    {
        $today = now()->toDateString();

        $jobRows = DB::table('translation_jobs')
            ->selectRaw('user_id, count(*) as files, coalesce(sum(file_size), 0) as bytes')
            ->whereDate('created_at', $today)
            ->groupBy('user_id')
            ->get();

        $legacyRows = DB::table('translation_history')
            ->selectRaw(
                'translation_history.user_id as user_id, count(*) as files, coalesce(sum(translation_history.file_size), 0) as bytes'
            )
            ->leftJoin('translation_jobs', 'translation_jobs.translation_history_id', '=', 'translation_history.id')
            ->where('translation_history.translation_type', 'document')
            ->whereDate('translation_history.created_at', $today)
            ->whereNull('translation_jobs.id')
            ->groupBy('translation_history.user_id')
            ->get();

        $totals = [];

        foreach ($jobRows as $row) {
            $totals[(int) $row->user_id] ??= ['files' => 0, 'bytes' => 0];
            $totals[(int) $row->user_id]['files'] += (int) $row->files;
            $totals[(int) $row->user_id]['bytes'] += (int) $row->bytes;
        }

        foreach ($legacyRows as $row) {
            $totals[(int) $row->user_id] ??= ['files' => 0, 'bytes' => 0];
            $totals[(int) $row->user_id]['files'] += (int) $row->files;
            $totals[(int) $row->user_id]['bytes'] += (int) $row->bytes;
        }

        foreach ($totals as $userId => $counts) {
            DB::table('translation_quota')->insert([
                'user_id'    => $userId,
                'quota_day'  => $today,
                'files'      => $counts['files'],
                'bytes'      => $counts['bytes'],
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('translation_quota');
    }
};