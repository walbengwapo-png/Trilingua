<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Tests\TestCase;

class TranslationStatusAuthorizationTest extends TestCase
{
    use RefreshDatabase;

    public function test_status_endpoint_requires_authentication(): void
    {
        Cache::put('translation_job_' . 'some-job', [
            'status' => 'completed',
            'user_id' => 1,
        ]);

        $this->get('/translate/status/some-job')
            ->assertRedirect(route('login'));
    }

    public function test_owner_can_poll_in_flight_job_from_cache(): void
    {
        $user = User::factory()->create();

        Cache::put('translation_job_' . 'abc-123', [
            'status' => 'processing',
            'user_id' => $user->id,
        ]);

        $this->actingAs($user)
            ->get('/translate/status/abc-123')
            ->assertOk()
            ->assertJsonPath('status', 'processing');
    }

    public function test_another_user_cannot_poll_in_flight_job(): void
    {
        $owner = User::factory()->create();
        $intruder = User::factory()->create();

        Cache::put('translation_job_' . 'abc-123', [
            'status' => 'completed',
            'download_url' => 'https://example.test/secret.pdf',
            'user_id' => $owner->id,
        ]);

        $this->actingAs($intruder)
            ->get('/translate/status/abc-123')
            ->assertNotFound();
    }

    public function test_owner_can_poll_completed_job_with_db_record(): void
    {
        $user = User::factory()->create();

        TranslationHistory::create([
            'user_id' => $user->id,
            'original_filename' => 'sample.docx',
            'translated_filename' => 'sample_translated.docx',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'status' => 'completed',
            'job_id' => 'def-456',
        ]);

        Cache::put('translation_job_' . 'def-456', [
            'status' => 'completed',
            'download_url' => 'https://example.test/signed-url',
            'user_id' => $user->id,
        ]);

        $this->actingAs($user)
            ->get('/translate/status/def-456')
            ->assertOk()
            ->assertJsonPath('status', 'completed');
    }

    public function test_another_user_cannot_poll_completed_job_with_db_record(): void
    {
        $owner = User::factory()->create();
        $intruder = User::factory()->create();

        TranslationHistory::create([
            'user_id' => $owner->id,
            'original_filename' => 'sample.docx',
            'translated_filename' => 'sample_translated.docx',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'status' => 'completed',
            'job_id' => 'def-456',
        ]);

        Cache::put('translation_job_' . 'def-456', [
            'status' => 'completed',
            'download_url' => 'https://example.test/signed-url',
            'user_id' => $owner->id,
        ]);

        $this->actingAs($intruder)
            ->get('/translate/status/def-456')
            ->assertNotFound();
    }

    public function test_unknown_job_id_returns_404(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)
            ->get('/translate/status/never-existed')
            ->assertNotFound();
    }
}