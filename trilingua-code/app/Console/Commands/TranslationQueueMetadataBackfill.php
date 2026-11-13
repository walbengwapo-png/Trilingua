<?php

namespace App\Console\Commands;

use App\Support\TranslationQueueMetadata;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/** Optional compatibility aid only. Normal recovery uses read-time resolution. */
class TranslationQueueMetadataBackfill extends Command
{
    protected $signature = 'jobs:backfill-translation-metadata {manifest} {--apply} {--approve-sha256=}';
    protected $description = 'Separately gated metadata-only rewrite; never changes serialized command bytes';

    public function handle(): int
    {
        $bytes = file_get_contents($this->argument('manifest'));
        $rows = json_decode($bytes, true, 32, JSON_THROW_ON_ERROR);
        if (count($rows) !== 16 || count(array_unique(array_column($rows, 'translation_job_id'))) !== 16
            || count(array_unique(array_column($rows, 'failed_job_id'))) !== 16
            || in_array(false, array_column($rows, 'valid'), true)) {
            $this->error('Expected sixteen unique, validated manifest entries.'); return self::FAILURE;
        }
        $hash = hash('sha256', $bytes);
        $this->line('Manifest SHA256: '.$hash);
        if (!$this->option('apply')) { $this->line('DRY RUN: no payloads changed.'); return self::SUCCESS; }
        if (!hash_equals($hash, (string) $this->option('approve-sha256'))) {
            $this->error('Explicit approval hash does not match the reviewed manifest.'); return self::FAILURE;
        }
        DB::transaction(function () use ($rows): void {
            foreach ($rows as $item) {
                $row = DB::table('failed_jobs')->where('id', $item['failed_job_id'])->lockForUpdate()->first();
                if (!$row) { throw new \RuntimeException('A reviewed failure row is missing.'); }
                $metadata = TranslationQueueMetadata::extract($row->payload);
                $job = TranslationQueueMetadata::resolve($row->payload);
                if (!$job || !$metadata || $job->id !== $item['translation_job_id']) {
                    throw new \RuntimeException('Metadata no longer matches the durable job.');
                }
                $envelope = json_decode($row->payload, true, 32, JSON_THROW_ON_ERROR);
                if (isset($envelope['translation_job_id'])) {
                    // Idempotent rerun: existing correct metadata needs no rewrite.
                    continue;
                }
                if (!hash_equals($item['payload_sha256'], hash('sha256', $row->payload))) {
                    throw new \RuntimeException('Payload hash changed since review.');
                }
                $envelope['translation_job_id'] = $metadata['translation_job_id'];
                unset($metadata['translation_job_id']);
                $envelope['translation_job_metadata'] = $metadata;
                $rewritten = json_encode($envelope, JSON_THROW_ON_ERROR);
                if (json_decode($rewritten, true, 32, JSON_THROW_ON_ERROR)['data']['command'] !== $envelope['data']['command']) {
                    throw new \RuntimeException('Serialized command changed.');
                }
                DB::table('failed_jobs')->where('id', $row->id)->where('payload', $row->payload)->update(['payload' => $rewritten]);
            }
        });
        $this->line('Reviewed metadata attached; serialized commands preserved.'); return self::SUCCESS;
    }
}
