<?php

namespace Tests\Unit;

use App\Exceptions\TranslationException;
use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationJob;
use App\Models\User;
use App\Services\BlockService;
use App\Services\HistoryService;
use App\Services\MetricsService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Notification;
use Mockery;
use Tests\TestCase;

class TranslateDocumentJobPythonIdTest extends TestCase
{
    use RefreshDatabase;

    public function test_ambiguous_connection_failure_requires_reconciliation_before_operator_recovery(): void
    {
        config(['translation.python_service.document_jobs' => true]);
        Notification::fake();
        $user = User::factory()->create();
        $state = TranslationJob::create(['user_id' => $user->id, 'payload_hash' => hash('sha256', 'source'),
            'original_name' => 'source.txt', 'original_ext' => '.txt', 'file_size' => 6,
            'source_lang' => 'English', 'target_lang' => 'Filipino', 'status' => 'queued']);
        $path = tempnam(sys_get_temp_dir(), 'trilingua-engine-test-');
        file_put_contents($path, 'source');
        $job = new TranslateDocumentJob('source.txt', '.txt', 6, 'English', 'Filipino', 'auto', $path, $user->id,
            'original/source.txt', translationJobId: $state->id, presetUuid: $state->uuid);
        $ids = [];
        $manager = Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('translateDocument')->once()->andReturnUsing(function ($file, $source, $target, $columns, $mode, $ocrMode, $id) use (&$ids) {
            $this->assertSame('strict', $ocrMode);
            $ids[] = $id;
            throw new TranslationException(count($ids) === 1 ? 'Could not connect' : 'Provider stopped', count($ids) === 1 ? 503 : 429);
        });
        $storage = Mockery::mock(StorageService::class);
        $history = Mockery::mock(HistoryService::class);
        $blocks = Mockery::mock(BlockService::class);
        $metrics = Mockery::mock(MetricsService::class);
        try {
            $job->handle($manager, $storage, $history, $blocks, $metrics);
            $this->assertSame('failed', $state->fresh()->status);
            $job->handle($manager, $storage, $history, $blocks, $metrics);
            $this->assertCount(1, $ids, 'A redelivered ambiguous job must not call the provider again.');
            $this->assertSame($ids[0], $state->fresh()->engine_job_uuid);
            $this->assertSame('failed', $state->fresh()->status);
            $job->handle($manager, $storage, $history, $blocks, $metrics);
            $state->refresh();
            $this->assertTrue($state->markQueued(recovered: true));
            $this->assertSame($ids[0], $state->fresh()->engine_job_uuid, 'Retain the prior engine UUID for reconciliation.');
        } finally {
            if (file_exists($path)) {
                unlink($path);
            }
        }
    }
}
