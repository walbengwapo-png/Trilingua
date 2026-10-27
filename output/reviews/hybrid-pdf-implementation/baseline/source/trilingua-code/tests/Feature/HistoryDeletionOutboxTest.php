<?php

namespace Tests\Feature;

use App\Models\StorageCleanupOutbox;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Services\StorageService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Artisan;
use Tests\TestCase;

/**
 * R7: history deletion commits the deletion intent AND a durable list of the
 * storage objects to clean up in one transaction. Shared originals survive so
 * long as any other row references them; a storage failure leaves the object
 * pending and the translations:cleanup-storage command retries it; a missing
 * object resolves to done.
 */
class HistoryDeletionOutboxTest extends TestCase
{
    use RefreshDatabase;

    protected function tearDown(): void
    {
        \Mockery::close();
        parent::tearDown();
    }

    private function user(): User
    {
        return User::factory()->create();
    }

    private function parent(User $user): TranslationHistory
    {
        return TranslationHistory::create([
            'user_id'                  => $user->id,
            'translation_type'         => 'document',
            'original_filename'        => 'doc.pdf',
            'translated_filename'      => 'doc_translated.pdf',
            'source_language'          => 'English',
            'target_language'          => 'Cebuano',
            'storage_path'             => $user->id . '/translations/v1.pdf',
            'storage_backend'          => 'supabase',
            'original_storage_path'    => $user->id . '/originals/doc.pdf',
            'original_storage_backend' => 'supabase',
            'status'                   => 'completed',
        ]);
    }

    private function child(User $user, int $parentId): TranslationHistory
    {
        return TranslationHistory::create([
            'user_id'                  => $user->id,
            'translation_type'         => 'document',
            'original_filename'        => 'doc.pdf',
            'translated_filename'      => 'doc_translated_v2.pdf',
            'source_language'          => 'English',
            'target_language'          => 'Filipino',
            'storage_path'             => $user->id . '/translations/v2.pdf',
            'storage_backend'          => 'supabase',
            'original_storage_path'    => $user->id . '/originals/doc.pdf',
            'original_storage_backend' => 'supabase',
            'parent_document_id'       => $parentId,
            'status'                   => 'translated',
        ]);
    }

    private function fakeStorage(): FakeStorageService
    {
        $fake = new FakeStorageService(\Mockery::mock(\GuzzleHttp\Client::class));
        $this->app->instance(StorageService::class, $fake);

        return $fake;
    }

    public function test_delete_removes_rows_and_cleans_all_unique_objects(): void
    {
        $fake = $this->fakeStorage();
        $user = $this->user();
        $parent = $this->parent($user);
        $this->child($user, $parent->id);

        $this->actingAs($user)->deleteJson('/history/' . $parent->id)
            ->assertOk()
            ->assertJsonPath('success', true);

        $this->assertSame(0, TranslationHistory::count(), 'parent and children removed');
        $this->assertSame(0, StorageCleanupOutbox::where('status', StorageCleanupOutbox::STATUS_PENDING)->count(), 'everything cleaned in the immediate pass');

        foreach ([
            $user->id . '/originals/doc.pdf',
            $user->id . '/translations/v1.pdf',
            $user->id . '/translations/v2.pdf',
        ] as $path) {
            $this->assertContains('supabase::' . $path, $fake->deleted, 'object should be deleted: ' . $path);
        }
        $this->assertCount(3, $fake->deleted, 'translated outputs + shared original all cleaned once');
    }

    public function test_shared_original_survives_if_another_row_still_references_it(): void
    {
        $fake = $this->fakeStorage();
        $user = $this->user();

        $parent = $this->parent($user);
        $this->child($user, $parent->id);
        // An unrelated surviving record that still needs the same original.
        $survivor = TranslationHistory::create([
            'user_id'                  => $user->id,
            'translation_type'         => 'document',
            'original_filename'        => 'doc.pdf',
            'source_language'          => 'English',
            'target_language'          => 'English',
            'storage_path'             => $user->id . '/translations/other.pdf',
            'storage_backend'          => 'supabase',
            'original_storage_path'    => $user->id . '/originals/doc.pdf',
            'original_storage_backend' => 'supabase',
            'status'                   => 'completed',
        ]);

        $this->actingAs($user)->deleteJson('/history/' . $parent->id)
            ->assertOk()
            ->assertJsonPath('success', true);

        $this->assertNull(TranslationHistory::find($parent->id));
        $this->assertNotNull(TranslationHistory::find($survivor->id));

        $this->assertNotContains('supabase::' . $user->id . '/originals/doc.pdf', $fake->deleted, 'shared original must not be deleted');
        $this->assertContains('supabase::' . $user->id . '/translations/v1.pdf', $fake->deleted);
        $this->assertContains('supabase::' . $user->id . '/translations/v2.pdf', $fake->deleted);
        $this->assertSame(0, StorageCleanupOutbox::where('path', $user->id . '/originals/doc.pdf')->count(), 'shared original never enqueued');
    }

    public function test_backend_failure_leaves_pending_and_command_retries_to_done(): void
    {
        $fake = $this->fakeStorage();
        $user = $this->user();
        $parent = $this->parent($user);

        $failPath = $user->id . '/translations/v1.pdf';
        $fake->failPaths->add('supabase::' . $failPath);

        $this->actingAs($user)->deleteJson('/history/' . $parent->id)
            ->assertOk()
            ->assertJsonPath('success', true);

        $pending = StorageCleanupOutbox::where('status', StorageCleanupOutbox::STATUS_PENDING)->get();
        $this->assertSame(1, $pending->count());
        $this->assertSame('supabase', $pending->first()->backend);
        $this->assertSame($failPath, $pending->first()->path);
        $this->assertSame(1, (int) $pending->first()->attempts);
        $this->assertNotNull($pending->first()->last_error);
        $this->assertTrue(TranslationHistory::find($parent->id) === null);

        // Storage is still down: the command defers again, never loses intent.
        Artisan::call('translations:cleanup-storage', ['--limit' => 50]);
        $still = StorageCleanupOutbox::where('status', StorageCleanupOutbox::STATUS_PENDING)->firstOrFail();
        $this->assertSame(2, (int) $still->attempts);

        // Storage recovers: the command finishes the job.
        $fake->failPaths = collect();
        $code = Artisan::call('translations:cleanup-storage', ['--limit' => 50]);
        $this->assertSame(0, $code);
        $this->assertSame(0, StorageCleanupOutbox::where('status', StorageCleanupOutbox::STATUS_PENDING)->count());
        $this->assertContains('supabase::' . $failPath, $fake->deleted, 'retried cleanup must actually delete the object');
    }

    public function test_persistent_failure_never_overflows_the_retry_counter(): void
    {
        $fake = $this->fakeStorage();
        $user = $this->user();

        $failPath = $user->id . '/translations/v1.pdf';
        $fake->failPaths->add('supabase::' . $failPath);

        TranslationHistory::create([
            'user_id'             => $user->id,
            'translation_type'    => 'document',
            'original_filename'   => 'doc.pdf',
            'source_language'     => 'English',
            'target_language'     => 'Cebuano',
            'storage_path'        => $failPath,
            'storage_backend'     => 'supabase',
            'original_storage_path' => $user->id . '/originals/doc.pdf',
            'original_storage_backend' => 'supabase',
            'status'              => 'completed',
        ]);

        $this->actingAs($user)->deleteJson('/history/' . TranslationHistory::firstOrFail()->id)
            ->assertOk();

        // A backend that never recovers must keep the entry pending through
        // many passes without the counter overflowing any supported engine.
        $service = app(\App\Services\StorageCleanupService::class);

        $baselineAttempts = (int) StorageCleanupOutbox::where('path', $failPath)->firstOrFail()->attempts;

        // A backend that never recovers must keep the entry pending through
        // many passes without the counter overflowing any supported engine.
        $passes = 400;
        for ($i = 0; $i < $passes; $i++) {
            $service->processPending(50);
        }

        $entry = StorageCleanupOutbox::where('path', $failPath)->firstOrFail();
        $this->assertSame(StorageCleanupOutbox::STATUS_PENDING, $entry->status, 'entry stays pending for the next pass');
        $this->assertSame($baselineAttempts + $passes, (int) $entry->attempts, 'accounting tracks every pass and cannot overflow');
        $this->assertNull(StorageCleanupOutbox::where('path', $failPath)->where('status', StorageCleanupOutbox::STATUS_DONE)->first());

        // When storage finally recovers, the same entry resolves to done.
        $fake->failPaths = collect();
        $result = $service->processPending(50);
        $this->assertSame(0, $result['remaining']);
        $this->assertContains('supabase::' . $failPath, $fake->deleted);
    }

    public function test_missing_object_resolves_to_done(): void
    {
        $fake = $this->fakeStorage();
        $user = $this->user();
        $parent = $this->parent($user);

        $this->actingAs($user)->deleteJson('/history/' . $parent->id)
            ->assertOk()
            ->assertJsonPath('success', true);

        $this->assertSame(0, StorageCleanupOutbox::where('status', StorageCleanupOutbox::STATUS_PENDING)->count(), 'missing object is already success');
        $this->assertContains('supabase::' . $user->id . '/translations/v1.pdf', $fake->deleted);
    }

    public function test_foreign_or_absent_record_returns_404_and_changes_nothing(): void
    {
        $fake = $this->fakeStorage();
        $owner = $this->user();
        $intruder = $this->user();
        $parent = $this->parent($owner);

        $this->actingAs($intruder)->deleteJson('/history/' . $parent->id)
            ->assertStatus(404);

        $this->assertNotNull(TranslationHistory::find($parent->id));
        $this->assertCount(0, $fake->deleted);
        $this->assertSame(0, StorageCleanupOutbox::count());

        $this->actingAs($owner)->deleteJson('/history/999999')->assertStatus(404);
        $this->assertSame(1, TranslationHistory::count());
    }

    public function test_local_delete_is_observable_and_stays_pending(): void
    {
        // Real StorageService instance: exercises the observable local unlink.
        $this->app->instance(StorageService::class, app(StorageService::class));
        $user = $this->user();

        $path = $user->id . '/translations/local.pdf';
        $dirPath = $this->createLocalDir('storage.fallback.path', $path);
        $parent = TranslationHistory::create([
            'user_id'                  => $user->id,
            'translation_type'         => 'document',
            'original_filename'        => 'local.pdf',
            'source_language'          => 'English',
            'target_language'          => 'Cebuano',
            'storage_path'             => $path,
            'storage_backend'          => 'local',
            'original_storage_path'    => '',
            'status'                   => 'completed',
        ]);

        $this->actingAs($user)->deleteJson('/history/' . $parent->id)
            ->assertOk()
            ->assertJsonPath('success', true);

        $pending = StorageCleanupOutbox::where('backend', 'local')
            ->where('path', $path)
            ->first();

        $this->assertNotNull($pending, 'a failed local unlink keeps the entry pending');
        $this->assertSame(1, (int) $pending->attempts);
        $this->assertNotNull($pending->last_error);

        // The mechanical problem is resolved (remove the blocking dir): retry works.
        @rmdir($dirPath);
        Artisan::call('translations:cleanup-storage');
        $this->assertSame(0, StorageCleanupOutbox::where('status', StorageCleanupOutbox::STATUS_PENDING)->count());
    }

    private function createLocalDir(string $configKey, string $relative): string
    {
        $root = rtrim((string) config($configKey), '/\\');
        $abs = $root . DIRECTORY_SEPARATOR . ltrim($relative, '/\\');
        if (! is_dir($abs)) {
            mkdir($abs, 0770, true);
        }
        return $abs;
    }
}

/**
 * Overrides StorageService's remote calls so destroy() and the cleanup command
 * exercise the pipeline without a live backend. Failure keys are "backend::path".
 */
class FakeStorageService extends StorageService
{
    public array $deleted = [];
    public \Illuminate\Support\Collection $failPaths;

    public function __construct(\GuzzleHttp\Client $client)
    {
        $this->failPaths = collect();
    }

    public function delete(string $backend, string $storagePath): void
    {
        $key = $backend . '::' . $storagePath;

        if ($this->failPaths->contains($key)) {
            throw new \RuntimeException('Remote storage delete failed for: ' . $storagePath);
        }

        $this->deleted[] = $key;
    }

    public function read(string $backend, string $storagePath): string
    {
        return '';
    }

    public function uploadWithFallback(string $localPath, string $storagePath): array
    {
        return [
            'backend' => 'supabase',
            'storage_path' => $storagePath,
            'signed_url' => 'https://example.test/signed',
            'signed_url_expires_at' => now()->toIso8601String(),
        ];
    }

    public function generateSignedUrl(string $storagePath): array
    {
        return [
            'signed_url' => 'https://example.test/signed',
            'signed_url_expires_at' => now()->addHour()->toIso8601String(),
        ];
    }
}