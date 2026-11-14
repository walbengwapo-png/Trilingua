<?php

namespace App\Console\Commands;

use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationJob;
use App\Services\Translation\TranslationManager;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/** Explicit recovery of a completed engine result, without another provider call. */
class ResumeDocumentResult extends Command
{
    protected $signature = 'translations:resume-result {job : Laravel translation job ID}';
    protected $description = 'Save the retained completed engine result after a polling interruption; never resubmit translation.';

    public function handle(TranslationManager $manager): int
    {
        $row = TranslationJob::findOrFail($this->argument('job'));
        if ($row->status !== TranslationJob::STATUS_FAILED || !$row->engine_job_uuid
            || !str_starts_with((string) $row->error, 'Document status is temporarily unavailable.')) {
            $this->error('This job is not awaiting result reconciliation.');
            return self::FAILURE;
        }
        if (($manager->inspectDocumentJob($row->engine_job_uuid)['status'] ?? null) !== 'completed') {
            $this->error('The engine has no confirmed completed result. No work was submitted.');
            return self::FAILURE;
        }
        $queue = config('queue.connections.database', []);
        if (config('queue.default') !== 'database' || !empty($queue['after_commit'])
            || (($queue['connection'] ?? null) !== null && $queue['connection'] !== config('database.default'))) {
            $this->error('Recovery requires the transactional database queue on the application connection.');
            return self::FAILURE;
        }
        DB::transaction(function () use ($row) {
            $locked = TranslationJob::whereKey($row->id)->lockForUpdate()->firstOrFail();
            if ($locked->status !== TranslationJob::STATUS_FAILED || $locked->engine_job_uuid !== $row->engine_job_uuid
                || !str_starts_with((string) $locked->error, 'Document status is temporarily unavailable.')) {
                throw new \RuntimeException('The job changed; no recovery was queued.');
            }
            $engine = $locked->engine_job_uuid;
            if (!$locked->markQueued(recovered: true)) { throw new \RuntimeException('Recovery already claimed.'); }
            $locked->engine_job_uuid = $engine;
            $locked->save();
            dispatch(new TranslateDocumentJob($locked->original_name, $locked->original_ext, (int) $locked->file_size,
                $locked->source_lang, $locked->target_lang, $locked->pdf_column_mode, '', (int) $locked->user_id,
                $locked->original_storage_path, $locked->mode, $locked->parent_document_id,
                $locked->original_storage_backend, (int) $locked->id, $locked->uuid, $locked->ocr_mode ?? 'strict', true));
        });
        $this->info('Retained result recovery queued. No document was submitted for translation.');
        return self::SUCCESS;
    }
}
