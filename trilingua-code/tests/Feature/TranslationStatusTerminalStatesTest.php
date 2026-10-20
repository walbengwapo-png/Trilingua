<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Models\User;
use App\Services\StorageService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Str;
use Tests\TestCase;

/**
 * R4 status contract: a completed job must never report "processing", and must
 * never be "completed" without a working, owner-authorized download path.
 * Signed-URL failures fall back to the authenticated history.file route.
 */
class TranslationStatusTerminalStatesTest extends TestCase
{
    use RefreshDatabase;

    private function makeUser(): User
    {
        return User::factory()->create();
    }

    public function test_cancelled_job_stops_polling_even_with_stale_processing_cache(): void
    {
        $user = $this->makeUser();
        $job = TranslationJob::create([
            'user_id' => $user->id,
            'payload_hash' => hash('sha256', 'cancelled'),
            'original_name' => 'input.pdf',
            'original_ext' => '.pdf',
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'status' => TranslationJob::STATUS_CANCELLED,
        ]);
        Cache::put('translation_job_'.$job->uuid, ['status' => 'processing'], 60);

        $this->actingAs($user)->get('/translate/status/'.$job->uuid)
            ->assertOk()
            ->assertJsonPath('status', 'failed')
            ->assertJsonPath('error', 'Translation cancelled.')
            ->assertJsonPath('recoverable', false);
    }

    public function test_completed_job_without_history_reports_terminal_failure_not_processing(): void
    {
        $user = $this->makeUser();
        $this->actingAs($user);

        Cache::flush();
        $job = TranslationJob::create([
            'uuid'                      => (string) Str::uuid(),
            'user_id'                   => $user->id,
            'payload_hash'              => hash('sha256', 'payload'),
            'original_name'             => 'input.pdf',
            'original_ext'              => '.pdf',
            'source_lang'               => 'English',
            'target_lang'               => 'Cebuano',
            'pdf_column_mode'           => 'auto',
            'mode'                      => 'balanced',
            'file_size'                 => 10,
            'status'                    => TranslationJob::STATUS_COMPLETED,
            'original_storage_path'     => $user->id.'/originals/x.pdf',
            'original_storage_backend'  => 'supabase',
            'recoverable'               => true,
            'translation_history_id'    => null,
        ]);

        $this->get('/translate/status/'.$job->uuid)
            ->assertOk()
            ->assertJsonPath('status', 'failed')
            ->assertJsonMissingPath('download_url')
            ->assertJsonPath('recoverable', true)
            ->assertSee('could not be retrieved', false);
    }

    public function test_signed_url_failure_falls_back_to_the_authenticated_route(): void
    {
        $user = $this->makeUser();
        $this->actingAs($user);

        Cache::flush();
        $history = TranslationHistory::create([
            'user_id'             => $user->id,
            'translation_type'    => 'document',
            'original_filename'   => 'input.pdf',
            'translated_filename' => 'out.pdf',
            'source_language'     => 'English',
            'target_language'     => 'Cebuano',
            'storage_path'        => $user->id.'/translations/out.pdf',
            'storage_backend'     => 'supabase',
            'status'              => 'completed',
            'review_status'       => 'pending',
            'job_id'              => (string) Str::uuid(),
            'created_at'          => now(),
        ]);

        TranslationJob::create([
            'uuid'                    => $history->job_id,
            'user_id'                 => $user->id,
            'payload_hash'            => hash('sha256', 'payload'),
            'original_name'           => 'input.pdf',
            'original_ext'            => '.pdf',
            'source_lang'             => 'English',
            'target_lang'             => 'Cebuano',
            'pdf_column_mode'         => 'auto',
            'mode'                    => 'balanced',
            'file_size'               => 10,
            'status'                  => TranslationJob::STATUS_COMPLETED,
            'translation_history_id'  => $history->id,
        ]);

        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('generateSignedUrl')->once()->andThrow(new \RuntimeException('signer down'));
            // Readability must be proven before the fallback link is asserted.
            $mock->shouldReceive('exists')->once()->andReturn(StorageService::PRESENCE_PRESENT);
        });

        $this->get('/translate/status/'.$history->job_id)
            ->assertOk()
            ->assertJsonPath('status', 'completed')
            ->assertJsonPath('download_url', route('history.file', ['id' => $history->id]));
    }

    public function test_local_backend_completed_uses_the_authenticated_route(): void
    {
        $user = $this->makeUser();
        // Local branch: readability must be proven before asserting a link.
        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('exists')->andReturn(StorageService::PRESENCE_PRESENT);
        });
        $this->actingAs($user);

        Cache::flush();
        $history = TranslationHistory::create([
            'user_id'             => $user->id,
            'translation_type'    => 'document',
            'original_filename'   => 'input.pdf',
            'translated_filename' => 'out.pdf',
            'source_language'     => 'English',
            'target_language'     => 'Cebuano',
            'storage_path'        => $user->id.'/translations/local-out.pdf',
            'storage_backend'     => 'local',
            'status'              => 'completed',
            'review_status'       => 'pending',
            'job_id'              => (string) Str::uuid(),
            'created_at'          => now(),
        ]);

        $this->get('/translate/status/'.$history->job_id)
            ->assertOk()
            ->assertJsonPath('status', 'completed')
            ->assertJsonPath('download_url', route('history.file', ['id' => $history->id]));
    }

    public function test_failed_job_reports_recoverability(): void
    {
        $user = $this->makeUser();
        $this->actingAs($user);

        Cache::flush();
        $job = TranslationJob::create([
            'uuid'                      => (string) Str::uuid(),
            'user_id'                   => $user->id,
            'payload_hash'              => hash('sha256', 'payload'),
            'original_name'             => 'input.pdf',
            'original_ext'              => '.pdf',
            'source_lang'               => 'English',
            'target_lang'               => 'Cebuano',
            'pdf_column_mode'           => 'auto',
            'mode'                      => 'balanced',
            'file_size'                 => 10,
            'status'                    => TranslationJob::STATUS_FAILED,
            'recoverable'               => true,
            'original_storage_path'     => $user->id.'/originals/x.pdf',
            'original_storage_backend'  => 'supabase',
            'terminal_failed_at'        => now()->subMinutes(5),
        ]);

        $this->get('/translate/status/'.$job->uuid)
            ->assertOk()
            ->assertJsonPath('status', 'failed')
            ->assertJsonPath('recoverable', true)
            ->assertSee('Translation failed', false);
    }

    public function test_history_only_row_with_blank_storage_path_is_terminal_failed(): void
    {
        $user = $this->makeUser();
        $this->actingAs($user);

        Cache::flush();
        $history = TranslationHistory::create([
            'user_id'             => $user->id,
            'translation_type'    => 'document',
            'original_filename'   => 'input.pdf',
            'translated_filename' => 'out.pdf',
            'source_language'     => 'English',
            'target_language'     => 'Cebuano',
            'storage_path'        => null,
            'storage_backend'     => 'supabase',
            'status'              => 'completed',
            'review_status'       => 'pending',
            'job_id'              => (string) Str::uuid(),
            'created_at'          => now(),
        ]);

        $this->get('/translate/status/'.$history->job_id)
            ->assertOk()
            ->assertJsonPath('status', 'failed')
            ->assertJsonMissingPath('download_url')
            ->assertSee('unavailable', false);
    }
}
