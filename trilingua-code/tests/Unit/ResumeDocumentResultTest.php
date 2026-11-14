<?php

namespace Tests\Unit;

use App\Exceptions\DocumentJobUncertainException;
use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationJob;
use App\Services\BlockService;
use App\Services\HistoryService;
use App\Services\MetricsService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Queue;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Str;
use Mockery;
use Tests\TestCase;

class ResumeDocumentResultTest extends TestCase
{
    protected function setUp(): void
    {
        parent::setUp();
        Queue::fake();
        config(['queue.default' => 'database', 'queue.connections.database.connection' => null,
            'queue.connections.database.after_commit' => false]);
        Schema::create('translation_jobs', function (Blueprint $table) {
            $table->id();
            foreach (['uuid', 'engine_job_uuid', 'original_name', 'original_ext', 'source_lang', 'target_lang',
                'pdf_column_mode', 'mode', 'original_storage_path', 'original_storage_backend', 'status', 'error', 'ocr_mode'] as $column) {
                $table->string($column)->nullable();
            }
            $table->integer('user_id');
            $table->integer('file_size')->default(10);
            $table->integer('progress')->default(15);
            $table->integer('attempts')->default(1);
            $table->integer('parent_document_id')->nullable();
            $table->boolean('recoverable')->default(false);
            foreach (['completed_at', 'started_at', 'terminal_failed_at', 'last_heartbeat_at'] as $column) {
                $table->timestamp($column)->nullable();
            }
            $table->timestamps();
        });
    }

    private function uncertain(): TranslationJob
    {
        return TranslationJob::create(['uuid' => (string) Str::uuid(), 'engine_job_uuid' => (string) Str::uuid(),
            'user_id' => 1, 'original_name' => 'source.txt', 'original_ext' => '.txt', 'source_lang' => 'English',
            'target_lang' => 'Filipino', 'pdf_column_mode' => 'auto', 'mode' => 'balanced',
            'original_storage_path' => 'private/original.txt', 'original_storage_backend' => 'supabase',
            'status' => 'failed', 'error' => 'Document status is temporarily unavailable. Operator reconciliation is required.']);
    }

    public function test_only_completed_result_can_be_queued_once(): void
    {
        $row = $this->uncertain();
        $engine = $row->engine_job_uuid;
        $manager = Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('inspectDocumentJob')->once()->with($engine)->andReturn(['status' => 'completed']);
        $manager->shouldNotReceive('translateDocument');
        $this->app->instance(TranslationManager::class, $manager);
        $this->artisan('translations:resume-result', ['job' => $row->id])->assertSuccessful();
        $this->assertSame('queued', $row->fresh()->status);
        $this->assertSame($engine, $row->fresh()->engine_job_uuid);
        Queue::assertPushed(TranslateDocumentJob::class, fn ($job) => $job->resumeEngineOnly && $job->uuid() === $row->uuid);
        $this->artisan('translations:resume-result', ['job' => $row->id])->assertFailed();
        Queue::assertPushed(TranslateDocumentJob::class, 1);
    }

    public function test_running_engine_job_is_never_replayed(): void
    {
        $row = $this->uncertain();
        $manager = Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('inspectDocumentJob')->once()->andReturn(['status' => 'processing']);
        $this->app->instance(TranslationManager::class, $manager);
        $this->artisan('translations:resume-result', ['job' => $row->id])->assertFailed();
        $this->assertSame('failed', $row->fresh()->status);
        Queue::assertNothingPushed();
    }

    public function test_nontransactional_queue_cannot_mutate_recovery_state(): void
    {
        $row = $this->uncertain();
        config(['queue.default' => 'sync']);
        $manager = Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('inspectDocumentJob')->once()->andReturn(['status' => 'completed']);
        $this->app->instance(TranslationManager::class, $manager);
        $this->artisan('translations:resume-result', ['job' => $row->id])->assertFailed();
        $this->assertSame('failed', $row->fresh()->status);
        Queue::assertNothingPushed();
    }

    public function test_polling_uncertainty_cannot_automatically_retranslate(): void
    {
        $row = $this->uncertain();
        $row->update(['status' => 'queued', 'error' => null]);
        $engine = $row->engine_job_uuid;
        config(['translation.python_service.document_jobs' => true]);
        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('read')->once()->andReturn('retained original');
        $manager = Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('translateDocument')->once()->andThrow(new DocumentJobUncertainException($engine));
        $history = Mockery::mock(HistoryService::class);
        $history->shouldNotReceive('insertRecord');
        $job = new TranslateDocumentJob($row->original_name, $row->original_ext, 10, 'English', 'Filipino',
            'auto', '', 1, $row->original_storage_path, 'balanced', null, 'supabase', $row->id, $row->uuid);
        $job->handle($manager, $storage, $history, Mockery::mock(BlockService::class), Mockery::mock(MetricsService::class));
        $this->assertSame('failed', $row->fresh()->status);
        $this->assertFalse($row->fresh()->isTerminalFailedRecoverable());
        $this->assertSame($engine, $row->fresh()->engine_job_uuid);
        $this->assertStringContainsString('reconciliation', $row->fresh()->error);
        Queue::assertNothingPushed();
    }
}
