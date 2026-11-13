<?php

namespace App\Console\Commands;

use App\Models\TranslationJob;
use App\Services\StorageService;
use App\Support\TranslationQueueMetadata;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

class TranslationQueueManifest extends Command
{
    protected $signature = 'jobs:translation-manifest {--snapshot= : Read a data-only snapshot instead of the configured database}
        {--expect=16} {--output= : Write the stable JSON report locally}';
    protected $description = 'Read-only legacy queue-to-translation validation; never rewrites queue payloads';

    public function handle(StorageService $storage): int
    {
        if ($path = $this->option('snapshot')) {
            $snapshot = json_decode(file_get_contents($path), true, 64, JSON_THROW_ON_ERROR);
        } else {
            $failed = DB::table('failed_jobs')->orderBy('id')->get()->map(fn ($row) => [
                'failed_job_id' => $row->id, 'payload' => $row->payload,
                'payload_sha256' => hash('sha256', $row->payload),
            ])->all();
            $ids = array_filter(array_map(fn ($row) => TranslationQueueMetadata::extract($row['payload'])['translation_job_id'] ?? null, $failed));
            $translations = TranslationJob::whereIn('id', $ids)->get()->map(function ($job) use ($storage) {
                return $job->getAttributes() + ['storage_exists' =>
                    $storage->exists($job->original_storage_backend, $job->original_storage_path) === 'present'];
            })->all();
            $snapshot = compact('failed', 'translations');
        }
        $report = TranslationQueueMetadata::manifest($snapshot['failed'], $snapshot['translations']);
        $json = json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR)."\n";
        if ($path = $this->option('output')) { file_put_contents($path, $json); }
        $this->line($json);
        return count($report) === (int) $this->option('expect') && !in_array(false, array_column($report, 'valid'), true)
            ? self::SUCCESS : self::FAILURE;
    }
}
