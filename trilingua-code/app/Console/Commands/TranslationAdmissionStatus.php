<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use App\Models\TranslationJob;

final class TranslationAdmissionStatus extends Command
{
    protected $signature = 'translations:admission {user?} {--release-owner=} {--drained : Operator verified all execution for this admission has stopped}';
    protected $description = 'Inspect admissions; release an owner-matched abandoned operation after drain';

    public function handle(): int
    {
        $query = DB::table('translation_admissions')->whereNotNull('owner');
        if ($this->argument('user') !== null) { $query->where('user_id', (int) $this->argument('user')); }
        if ($owner = $this->option('release-owner')) {
            if (!$this->argument('user') || !$this->option('drained')) {
                $this->error('Release requires an exact user/owner and verified drained execution.');
                return self::FAILURE;
            }
            $changed = DB::transaction(function () use ($query, $owner): int {
                $matched = (clone $query)->where('owner', $owner)->whereIn('phase', ['uncertain', 'intake', 'document']);
                $row = (clone $matched)->lockForUpdate()->first();
                if (!$row) { return 0; }
                $job = $row->translation_job_id ? TranslationJob::find($row->translation_job_id) : null;
                if (TranslationJob::where('user_id', $row->user_id)->whereIn('status', TranslationJob::ACTIVE_STATUSES)->exists()
                    || ($job && ($job->engine_job_uuid
                    && DB::table('python_document_jobs')->where('id', $job->engine_job_uuid)
                        ->whereIn('status', ['queued', 'processing'])->exists()))) {
                    $this->error('Reconcile the active durable job before releasing admission.');
                    return 0;
                }
                return $matched->update([
                    'owner' => null, 'phase' => 'idle', 'translation_job_id' => null,
                    'expected_attempt' => null, 'heartbeat_at' => null, 'deadline_at' => null,
                ]);
            });
            if ($changed !== 1) { $this->error('Admission changed or requires reconciliation; no release.'); return self::FAILURE; }
            $this->info('Reviewed admission released. No job was replayed.');
            return self::SUCCESS;
        }
        $rows = $query->orderBy('user_id')->get()->map(fn ($row) => (array) $row)->all();
        $this->table(['User', 'Owner', 'Phase', 'Job', 'Attempt', 'Heartbeat', 'Deadline'], array_map(fn ($row) => [
            $row['user_id'], $row['owner'], $row['phase'], $row['translation_job_id'], $row['expected_attempt'], $row['heartbeat_at'], $row['deadline_at'],
        ], $rows));
        return self::SUCCESS;
    }
}
