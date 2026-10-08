<?php

namespace Tests\Feature;

use App\Services\HistoryService;
use App\Services\StorageService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use RuntimeException;
use Tests\TestCase;

/**
 * Gate 3c — availability is decided by the backend, never by exception text.
 *
 * Both redownload routes used to search the thrown exception's message for the
 * substring "not found" to choose between a permanent 404 and a retryable 500.
 * Exception text is not a contract, and the substring matched both a real
 * deletion and a transient outage, so the two answers were routinely swapped.
 */
class DownloadAvailabilityTest extends TestCase
{
    use RefreshDatabase;

    private function record(array $overrides = []): array
    {
        return array_merge([
            'id'                     => 7,
            'user_id'                => 1,
            'translated_filename'    => 'report-fil.pdf',
            'original_filename'      => 'report.pdf',
            'storage_path'           => 'user/1/report-fil.pdf',
            'storage_backend'        => StorageService::BACKEND_SUPABASE,
            'original_storage_path'  => 'user/1/report.pdf',
            'original_storage_backend' => StorageService::BACKEND_SUPABASE,
        ], $overrides);
    }

    private function signedUrl(): array
    {
        return [
            'signed_url'            => 'https://storage.example.com/signed',
            'signed_url_expires_at' => now()->addHour()->toIso8601String(),
        ];
    }

    /**
     * @dataProvider routes
     */
    public function test_a_missing_object_returns_404(string $route, string $expiryCall): void
    {
        $user = \App\Models\User::factory()->create();
        $this->actingAs($user);

        $this->mock(HistoryService::class, function ($mock) use ($expiryCall) {
            $mock->shouldReceive('getRecord')->andReturn($this->record());
            $mock->shouldReceive($expiryCall)->andReturn(null);
        });

        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('exists')->andReturn(StorageService::PRESENCE_MISSING);
            $mock->shouldNotReceive('generateSignedUrl');
        });

        $this->postJson($route)->assertStatus(404);
    }

    /**
     * The regression that motivated the gate: a DNS outage whose message
     * contains "not found" used to be reported as permanent data loss.
     *
     * @dataProvider routes
     */
    public function test_an_outage_whose_message_says_not_found_is_not_reported_as_loss(
        string $route,
        string $expiryCall
    ): void {
        $user = \App\Models\User::factory()->create();
        $this->actingAs($user);

        $this->mock(HistoryService::class, function ($mock) use ($expiryCall) {
            $mock->shouldReceive('getRecord')->andReturn($this->record());
            $mock->shouldReceive($expiryCall)->andReturn(null);
        });

        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('exists')->andReturn(StorageService::PRESENCE_UNKNOWN);
            $mock->shouldReceive('generateSignedUrl')
                ->andThrow(new RuntimeException('cURL error 6: Host not found'));
        });

        $response = $this->postJson($route);

        $this->assertNotSame(404, $response->getStatusCode(),
            'A transient outage must never be reported as a permanently lost file.');
        $response->assertStatus(500);
    }

    /**
     * The mirror case: a genuine deletion reported as "NoSuchKey" used to be
     * retried forever instead of offering a re-upload.
     *
     * @dataProvider routes
     */
    public function test_a_deletion_whose_message_does_not_say_not_found_is_still_404(
        string $route,
        string $expiryCall
    ): void {
        $user = \App\Models\User::factory()->create();
        $this->actingAs($user);

        $this->mock(HistoryService::class, function ($mock) use ($expiryCall) {
            $mock->shouldReceive('getRecord')->andReturn($this->record());
            $mock->shouldReceive($expiryCall)->andReturn(null);
        });

        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('exists')->andReturn(StorageService::PRESENCE_MISSING);
            $mock->shouldNotReceive('generateSignedUrl');
        });

        $this->postJson($route)->assertStatus(404);
    }

    /**
     * Unverifiable presence must not block the download: if signing works the
     * user gets their file, because the probe is not the operation.
     *
     * @dataProvider routes
     */
    public function test_unknown_presence_still_delivers_the_file_when_signing_succeeds(
        string $route,
        string $expiryCall
    ): void {
        $user = \App\Models\User::factory()->create();
        $this->actingAs($user);

        $this->mock(HistoryService::class, function ($mock) use ($expiryCall) {
            $mock->shouldReceive('getRecord')->andReturn($this->record());
            $mock->shouldReceive($expiryCall)->andReturn(null);
        });

        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('exists')->andReturn(StorageService::PRESENCE_UNKNOWN);
            $mock->shouldReceive('generateSignedUrl')->andReturn($this->signedUrl());
        });

        $this->postJson($route)->assertStatus(200)->assertJsonStructure(['download_url']);
    }

    /**
     * A probe that itself throws is uncertainty, not evidence of loss.
     *
     * @dataProvider routes
     */
    public function test_a_failing_probe_never_claims_the_file_is_gone(
        string $route,
        string $expiryCall
    ): void {
        $user = \App\Models\User::factory()->create();
        $this->actingAs($user);

        $this->mock(HistoryService::class, function ($mock) use ($expiryCall) {
            $mock->shouldReceive('getRecord')->andReturn($this->record());
            $mock->shouldReceive($expiryCall)->andReturn(null);
        });

        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('exists')->andThrow(new RuntimeException('bucket unreachable'));
            $mock->shouldReceive('generateSignedUrl')->andReturn($this->signedUrl());
        });

        $this->postJson($route)->assertStatus(200)->assertJsonStructure(['download_url']);
    }

    /**
     * @dataProvider routes
     */
    public function test_ownership_is_still_enforced_before_storage_is_touched(
        string $route,
        string $expiryCall
    ): void {
        $owner = \App\Models\User::factory()->create();
        $other = \App\Models\User::factory()->create();
        $this->actingAs($other);

        $this->mock(HistoryService::class, function ($mock) use ($owner) {
            $mock->shouldReceive('getRecord')->andReturn($this->record(['user_id' => $owner->id]));
        });

        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldNotReceive('exists');
            $mock->shouldNotReceive('generateSignedUrl');
        });

        $this->postJson($route)->assertStatus(403);
    }

    public static function routes(): array
    {
        return [
            'translated file' => ['/history/redownload/7', 'updateExpiry'],
            'original file'  => ['/history/redownload-original/7', 'updateExpiry'],
        ];
    }
}
