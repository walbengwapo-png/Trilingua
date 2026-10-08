<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Models\User;
use App\Services\StorageService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Queue;
use Mockery;
use RuntimeException;
use Tests\TestCase;

/**
 * Gate 3c — re-translation reports a lost original honestly.
 *
 * The route only checked that `original_storage_path` was non-empty. A path is
 * a string in the database, not evidence that the object is still stored, so a
 * deleted original surfaced as an opaque 500 from read() — inviting retries
 * that can never succeed and hiding the re-upload the user actually needs.
 */
class RetranslateAvailabilityTest extends TestCase
{
    use RefreshDatabase;

    private function record(User $user): TranslationHistory
    {
        return TranslationHistory::create([
            'user_id'                  => $user->id,
            'translation_type'         => 'document',
            'original_filename'        => 'doc.docx',
            'source_language'          => 'English',
            'target_language'          => 'Cebuano',
            'storage_path'             => 'user/translations/v1.pdf',
            'storage_backend'          => StorageService::BACKEND_SUPABASE,
            'original_storage_path'    => 'user/originals/doc.docx',
            'original_storage_backend' => StorageService::BACKEND_SUPABASE,
            'status'                   => 'completed',
            'file_size'                => 0,
        ]);
    }

    private function retrans(User $user, TranslationHistory $record, string $target = 'Filipino')
    {
        return $this->actingAs($user)->post('/documents/' . $record->id . '/re-translate', [
            'target_lang' => $target,
        ], ['Accept' => 'application/json']);
    }

    public function test_a_deleted_original_offers_a_re_upload_instead_of_a_500(): void
    {
        $user = User::factory()->create();
        $record = $this->record($user);

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('exists')->andReturn(StorageService::PRESENCE_MISSING);
        $storage->shouldNotReceive('read');
        $this->app->instance(StorageService::class, $storage);

        $response = $this->retrans($user, $record);

        $response->assertStatus(422);
        $this->assertStringContainsString('re-upload', $response->json('error'));
    }

    public function test_an_unverifiable_original_is_retryable_not_reported_as_lost(): void
    {
        $user = User::factory()->create();
        $record = $this->record($user);

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('exists')->andReturn(StorageService::PRESENCE_UNKNOWN);
        $storage->shouldNotReceive('read');
        $this->app->instance(StorageService::class, $storage);

        $response = $this->retrans($user, $record);

        $this->assertSame(503, $response->getStatusCode(),
            'Storage uncertainty must be retryable, never reported as a lost file.');
        $this->assertStringNotContainsString('re-upload', $response->json('error'),
            'An outage must not tell the user their original is gone.');
    }

    public function test_a_failing_probe_is_treated_as_uncertainty(): void
    {
        $user = User::factory()->create();
        $record = $this->record($user);

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('exists')
            ->andThrow(new RuntimeException('bucket unreachable'));
        $storage->shouldNotReceive('read');
        $this->app->instance(StorageService::class, $storage);

        $this->assertSame(503, $this->retrans($user, $record)->getStatusCode());
    }

    public function test_a_present_original_proceeds_normally(): void
    {
        Queue::fake();
        config(['translation.upload.max_daily_files' => 25]);

        $user = User::factory()->create();
        $record = $this->record($user);

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('exists')->andReturn(StorageService::PRESENCE_PRESENT);
        $storage->shouldReceive('read')->andReturn('PK-original-bytes');
        $this->app->instance(StorageService::class, $storage);

        $this->retrans($user, $record)->assertOk()->assertJsonPath('status', 'processing');
    }

    public function test_ownership_is_checked_before_storage_is_probed(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $record = $this->record($owner);

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldNotReceive('exists');
        $storage->shouldNotReceive('read');
        $this->app->instance(StorageService::class, $storage);

        $this->retrans($other, $record)->assertStatus(403);
    }

    public function test_a_missing_stored_path_is_still_refused_before_any_probe(): void
    {
        $user = User::factory()->create();
        $record = $this->record($user);
        $record->original_storage_path = null;
        $record->save();

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldNotReceive('exists');
        $this->app->instance(StorageService::class, $storage);

        $this->assertSame(422, $this->retrans($user, $record)->getStatusCode());
    }

    public function test_reused_result_does_not_offer_a_confirmed_missing_download(): void
    {
        $user = User::factory()->create();
        $record = $this->record($user);
        $originalBytes = 'PK-original-bytes';
        $payloadHash = TranslationJob::payloadHash(
            $user->id,
            hash('sha256', $originalBytes),
            'English',
            'Filipino',
            'balanced',
            'auto',
            $record->id,
        );

        $completedHistory = $this->record($user);
        $completedHistory->update(['storage_path' => 'user/translations/missing.pdf']);
        TranslationJob::create([
            'uuid' => 'reused-missing-output',
            'user_id' => $user->id,
            'payload_hash' => $payloadHash,
            'original_name' => 'doc.docx',
            'original_ext' => '.docx',
            'source_lang' => 'English',
            'target_lang' => 'Filipino',
            'status' => TranslationJob::STATUS_COMPLETED,
            'translation_history_id' => $completedHistory->id,
        ]);

        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('exists')
            ->with(StorageService::BACKEND_SUPABASE, 'user/originals/doc.docx')
            ->andReturn(StorageService::PRESENCE_PRESENT);
        $storage->shouldReceive('read')->andReturn($originalBytes);
        $storage->shouldReceive('generateSignedUrl')->andThrow(new RuntimeException('signer unavailable'));
        $storage->shouldReceive('exists')
            ->with(StorageService::BACKEND_SUPABASE, 'user/translations/missing.pdf')
            ->andReturn(StorageService::PRESENCE_MISSING);
        $this->app->instance(StorageService::class, $storage);

        $response = $this->retrans($user, $record);
        $response->assertOk()->assertJsonPath('reused', true)->assertJsonPath('status', 'failed');
        $this->assertNull($response->json('download_url'));
    }
}
