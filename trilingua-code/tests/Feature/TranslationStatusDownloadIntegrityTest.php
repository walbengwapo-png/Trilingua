<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Models\User;
use App\Services\StorageService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * Package C: a completed status must never carry a link known to fail, and a
 * storage outage must never be reported as a confirmed failure.
 */
class TranslationStatusDownloadIntegrityTest extends TestCase
{
    use RefreshDatabase;

    private function makeUser(): User
    {
        return User::factory()->create(['is_admin' => false]);
    }

    private function makeCompletedJob(User $user, string $backend = StorageService::BACKEND_SUPABASE): TranslationJob
    {
        $history = TranslationHistory::create([
            'user_id' => $user->id,
            'translation_type' => 'document',
            'original_filename' => 'contract.pdf',
            'translated_filename' => 'contract_ceb.pdf',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'original_storage_path' => '1/originals/contract.pdf',
            'storage_path' => '1/translations/out.pdf',
            'storage_backend' => $backend,
            'status' => 'completed',
            'review_status' => 'pending',
        ]);

        return TranslationJob::create([
            'uuid' => 'job-' . uniqid(),
            'user_id' => $user->id,
            'payload_hash' => str_repeat('a', 64),
            'original_name' => 'contract.pdf',
            'original_ext' => 'pdf',
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'status' => TranslationJob::STATUS_COMPLETED,
            'translation_history_id' => $history->id,
            'recoverable' => true,
        ]);
    }

    private function mockStorage(string $presence, bool $signerFails): StorageService
    {
        $mock = \Mockery::mock(StorageService::class);
        $mock->shouldReceive('exists')->andReturn($presence);
        if ($signerFails) {
            $mock->shouldReceive('generateSignedUrl')->andThrow(new \RuntimeException('signer outage'));
        }
        $this->app->instance(StorageService::class, $mock);

        return $mock;
    }

    public function test_signer_failure_with_readable_object_returns_owner_route(): void
    {
        $user = $this->makeUser();
        $job = $this->makeCompletedJob($user);
        $this->mockStorage(StorageService::PRESENCE_PRESENT, signerFails: true);

        $historyId = $job->translation_history_id;
        $this->actingAs($user)
            ->getJson("/translate/status/{$job->uuid}")
            ->assertOk()
            ->assertJson([
                'status' => 'completed',
                'download_url' => route('history.file', ['id' => $historyId]),
            ]);
    }

    public function test_signer_failure_with_confirmed_missing_returns_terminal_failure(): void
    {
        $user = $this->makeUser();
        $job = $this->makeCompletedJob($user);
        $this->mockStorage(StorageService::PRESENCE_MISSING, signerFails: true);

        $this->actingAs($user)
            ->getJson("/translate/status/{$job->uuid}")
            ->assertOk()
            ->assertJson([
                'status' => 'failed',
                'recoverable' => false,
            ]);
    }

    public function test_storage_outage_keeps_completed_without_asserting_a_link(): void
    {
        $user = $this->makeUser();
        $job = $this->makeCompletedJob($user);
        $this->mockStorage(StorageService::PRESENCE_UNKNOWN, signerFails: true);

        $response = $this->actingAs($user)->getJson("/translate/status/{$job->uuid}")->assertOk();
        $response->assertJson(['status' => 'completed', 'download_available' => false]);
        $this->assertNull($response->json('download_url'));

        // The durable job state is never flipped to failed by a status-time outage.
        $this->assertSame(TranslationJob::STATUS_COMPLETED, $job->fresh()->status);
    }

    public function test_local_backend_missing_is_a_confirmed_failure(): void
    {
        $user = $this->makeUser();
        $job = $this->makeCompletedJob($user, StorageService::BACKEND_LOCAL);
        $this->mockStorage(StorageService::PRESENCE_MISSING, signerFails: false);

        $this->actingAs($user)
            ->getJson("/translate/status/{$job->uuid}")
            ->assertOk()
            ->assertJson(['status' => 'failed', 'recoverable' => false]);
    }

    public function test_local_backend_present_returns_owner_route(): void
    {
        $user = $this->makeUser();
        $job = $this->makeCompletedJob($user, StorageService::BACKEND_LOCAL);
        $this->mockStorage(StorageService::PRESENCE_PRESENT, signerFails: false);

        $historyId = $job->translation_history_id;
        $this->actingAs($user)
            ->getJson("/translate/status/{$job->uuid}")
            ->assertOk()
            ->assertJson([
                'status' => 'completed',
                'download_url' => route('history.file', ['id' => $historyId]),
            ]);
    }
}