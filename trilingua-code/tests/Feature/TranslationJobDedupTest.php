<?php

namespace Tests\Feature;

use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Services\BlockService;
use App\Services\HistoryService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Mockery;
use Tests\TestCase;

class TranslationJobDedupTest extends TestCase
{
    use RefreshDatabase;

    public function test_identical_concurrent_submissions_yield_one_job_and_one_history_row(): void
    {
        // Use the real database queue so the first job is still queued when
        // the second identical submission arrives.
        config(['queue.default' => 'database']);
        Cache::flush();

        $user = User::factory()->create();
        $file = UploadedFile::fake()->create(
            'duplicate.docx',
            1024,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        );

        $first = $this->actingAs($user)->postJson('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => $file,
        ]);
        $first->assertOk()->assertJsonPath('status', 'processing');
        $this->assertSame(1, DB::table('jobs')->count());

        // Second identical submission while the first is queued. A fresh
        // UploadedFile instance (mirrors a real second browser upload).
        $dupFile = UploadedFile::fake()->create(
            'duplicate.docx',
            1024,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        );
        $dup = $this->actingAs($user)->postJson('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => $dupFile,
        ]);
        $dup->assertOk();
        $dup->assertJsonPath('duplicate', true);
        $this->assertSame(1, DB::table('jobs')->count(), 'no duplicate job may be queued');
        $this->assertSame(0, TranslationHistory::count(), 'nothing processed yet');

        // Process the single queued job exactly once.
        $job = $this->hydrateQueuedJob();

        $manager = Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('translateDocument')
            ->once()
            ->andReturn([
                'download_filename' => 'duplicate_translated.docx',
                'body' => 'translated file body',
                'blocks' => [],
                'sidecar' => null,
            ]);

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('uploadFile')
            ->once()
            ->andReturn([
                'storage_path' => 'user/originals/test.docx',
                'signed_url' => 'https://example.test/signed',
                'signed_url_expires_at' => now()->toIso8601String(),
            ]);

        // Real HistoryService so insertRecord() genuinely persists the row.
        $history = app(HistoryService::class);

        $blocks = Mockery::mock(BlockService::class);
        $blocks->shouldReceive('persistBlocks')->once();

        $job->handle($manager, $storage, $history, $blocks);

        $this->assertSame(1, TranslationHistory::count(), 'one queued job must write one history row');
    }

    public function test_unique_id_is_stable_for_identical_submissions(): void
    {
        $a = new TranslateDocumentJob('doc.pdf', '.pdf', 100, 'English', 'Cebuano', 'auto', '/tmp/a', 7, null);
        $b = new TranslateDocumentJob('doc.pdf', '.pdf', 100, 'English', 'Cebuano', 'auto', '/tmp/b', 7, null);
        $c = new TranslateDocumentJob('doc.pdf', '.pdf', 100, 'English', 'Filipino', 'auto', '/tmp/c', 7, null);

        $this->assertSame($a->uniqueId(), $b->uniqueId());
        $this->assertNotSame($a->uniqueId(), $c->uniqueId(), 'different target language must not dedup');
    }

    private function hydrateQueuedJob(): TranslateDocumentJob
    {
        $row = DB::table('jobs')->firstOrFail();
        $payload = json_decode($row->payload, true);

        /** @var TranslateDocumentJob $job */
        $job = unserialize($payload['data']['command']);
        $this->assertInstanceOf(TranslateDocumentJob::class, $job);

        return $job;
    }

    protected function tearDown(): void
    {
        Mockery::close();
        parent::tearDown();
    }
}