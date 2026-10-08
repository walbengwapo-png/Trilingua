<?php

namespace Tests\Feature\Admin;

use App\Models\TranslationBlock;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Services\Admin\ReviewService;
use App\Services\StorageService;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

/**
 * R5 HTTP surface: the API contract admin JS depends on — Verify refuses
 * unpublished drafts, Save & Regenerate publishes and always returns a working
 * download link, and one-off file routes stream backend-aware bytes.
 */
class ReviewDraftPublishHttpTest extends TestCase
{
    use RefreshDatabase;

    private function makeAdmin(): User
    {
        return User::factory()->create(['is_admin' => true]);
    }

    private function makeUser(): User
    {
        return User::factory()->create(['is_admin' => false]);
    }

    private function makeDocRecord(User $submitter, array $overrides = []): TranslationHistory
    {
        $record = TranslationHistory::create(array_merge([
            'user_id' => $submitter->id,
            'translation_type' => 'document',
            'original_filename' => 'contract.pdf',
            'translated_filename' => 'contract_ceb.pdf',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'original_storage_path' => '1/originals/contract.pdf',
            'original_storage_backend' => StorageService::BACKEND_SUPABASE,
            'storage_path' => '1/translations/v1.pdf',
            'storage_backend' => StorageService::BACKEND_SUPABASE,
            'status' => 'completed',
            'review_status' => 'pending',
            'quality_score' => 60,
        ], $overrides));

        TranslationBlock::create([
            'translation_history_id' => $record->id,
            'block_index' => 0,
            'block_type' => 'paragraph',
            'source_text' => 'Hello world',
            'ai_translated_text' => 'Kumusta kalibutan',
            'current_text' => 'Kumusta kalibutan',
            'quality_score' => 90,
            'status' => 'pending',
        ]);

        return $record;
    }

    private function stubSupabasePublish(bool $localFallback = false): \Mockery\LegacyMockInterface
    {
        $storage = \Mockery::mock(StorageService::class);
        $storage->shouldReceive('read')->andReturn('original-bytes');

        if ($localFallback) {
            $storage->shouldReceive('uploadWithFallback')->once()->andReturn([
                'backend' => StorageService::BACKEND_LOCAL,
                'storage_path' => '1/translations/fb.pdf',
                'signed_url' => null,
                'signed_url_expires_at' => now()->toIso8601String(),
            ]);
            // The ORIGINAL is still a Supabase object and keeps a signed link.
            $storage->shouldReceive('generateSignedUrl')->once()->andReturn([
                'signed_url' => 'https://supabase.test/original',
                'signed_url_expires_at' => now()->toIso8601String(),
            ]);
        } else {
            $storage->shouldReceive('uploadWithFallback')->once()->andReturn([
                'backend' => StorageService::BACKEND_SUPABASE,
                'storage_path' => '1/translations/new.pdf',
                'signed_url' => 'https://supabase.test/new',
                'signed_url_expires_at' => now()->toIso8601String(),
            ]);
            $storage->shouldReceive('generateSignedUrl')->once()->andReturn([
                'signed_url' => 'https://supabase.test/original',
                'signed_url_expires_at' => now()->toIso8601String(),
            ]);
        }

        $this->app->instance(StorageService::class, $storage);

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')->once()->andReturn([
            'body' => 'regenerated-bytes',
            'download_filename' => 'contract_regenerated.pdf',
            'mime_type' => 'application/pdf',
        ]);
        $this->app->instance(TranslationManager::class, $manager);

        Http::fake();

        return $storage;
    }

    public function test_verify_document_rejects_unpublished_draft_over_http(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $block = $record->blocks->first();

        app(ReviewService::class)->updateBlock($record->id, $block->id, $admin->id, 'Draft only');

        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/verify-document")
            ->assertStatus(422)
            ->assertJson(function ($json) {
                $json->where('error', function ($error) {
                    return is_string($error) && str_contains(strtolower($error), 'save & regenerate');
                });
                return true;
            });

        $this->assertSame('edited', $record->fresh()->review_status);
    }

    public function test_verify_document_succeeds_when_draft_is_published(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());

        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/verify-document")
            ->assertOk()
            ->assertJson(['success' => true, 'status' => 'verified']);

        $this->assertSame('verified', $record->fresh()->review_status);
        $this->assertSame('verified', $record->blocks->first()->fresh()->status);
    }

    public function test_save_edit_response_marks_draft(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $block = $record->blocks->first();

        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/blocks/{$block->id}/update", [
                'expected_draft_revision' => 0,
                'current_text' => 'Draft only',
            ])
            ->assertOk()
            ->assertJson([
                'success' => true,
                'status' => 'edited',
                'draft' => true,
            ])
            ->assertJsonPath('message', fn ($m) => str_contains($m, 'Save & Regenerate'));

        $this->assertTrue($record->fresh()->hasUnpublishedEdits());
    }

    public function test_save_regenerate_supabase_returns_signed_url(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $this->stubSupabasePublish(localFallback: false);

        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/save-regenerate", [
                'expected_draft_revision' => 0,
                'expected_storage_path' => '1/translations/v1.pdf',
            ])
            ->assertOk()
            ->assertJson([
                'success' => true,
                'new_download_url' => 'https://supabase.test/new',
                'storage_backend' => 'supabase',
                'published' => true,
                'draft' => false,
            ]);
    }

    public function test_save_regenerate_local_fallback_returns_authenticated_route(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());
        $this->stubSupabasePublish(localFallback: true);

        $response = $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/save-regenerate", [
                'expected_draft_revision' => 0,
                'expected_storage_path' => '1/translations/v1.pdf',
            ])
            ->assertOk()
            ->assertJson([
                'success' => true,
                'storage_backend' => 'local',
                'published' => true,
                'draft' => false,
            ]);

        $url = $response->json('new_download_url');
        $this->assertNotNull($url);
        $this->assertStringContainsString('/admin/review/' . $record->id . '/file', $url);
        $this->assertSame('local', $record->fresh()->storage_backend);
    }

    public function test_python_failure_returns_422_and_keeps_previous_file(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser());

        $storage = \Mockery::mock(StorageService::class);
        $storage->shouldReceive('read')->andReturn('original-bytes');
        $this->app->instance(StorageService::class, $storage);

        $manager = \Mockery::mock(TranslationManager::class);
        $manager->shouldReceive('regenerateDocument')
            ->once()
            ->andThrow(new \App\Exceptions\TranslationException('Python reconstruction failed'));
        $this->app->instance(TranslationManager::class, $manager);

        Http::fake();

        $this->actingAs($admin)
            ->postJson("/admin/review/{$record->id}/save-regenerate", [
                'expected_draft_revision' => 0,
                'expected_storage_path' => '1/translations/v1.pdf',
            ])
            ->assertStatus(422)
            ->assertJson(function ($json) {
                $json->where('error', fn ($error) => is_string($error) && str_contains($error, 'Python reconstruction failed'));
                return true;
            });

        $fresh = $record->fresh();
        $this->assertSame('1/translations/v1.pdf', $fresh->storage_path);
        $this->assertSame(0, (int) $fresh->published_revision);
    }

    public function test_save_regenerate_rejects_non_document(): void
    {
        $admin = $this->makeAdmin();
        $user = $this->makeUser();
        $text = TranslationHistory::create([
            'user_id' => $user->id,
            'translation_type' => 'text',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'source_text' => 'Hello',
            'translated_text' => 'Kumusta',
            'status' => 'completed',
            'review_status' => 'pending',
        ]);

        $this->actingAs($admin)
            ->postJson("/admin/review/{$text->id}/save-regenerate")
            ->assertStatus(422);
    }

    public function test_original_file_route_streams_local_backend_source(): void
    {
        $admin = $this->makeAdmin();
        $record = $this->makeDocRecord($this->makeUser(), [
            'original_storage_backend' => StorageService::BACKEND_LOCAL,
            'original_storage_path' => '1/originals/local-contract.pdf',
        ]);

        $storage = \Mockery::mock(StorageService::class);
        $storage->shouldReceive('read')
            ->with(StorageService::BACKEND_LOCAL, '1/originals/local-contract.pdf')
            ->once()
            ->andReturn('%PDF-1.4 local original bytes');
        $this->app->instance(StorageService::class, $storage);

        $response = $this->actingAs($admin)
            ->get("/admin/review/{$record->id}/original-file");

        $response->assertOk()
            ->assertHeader('Content-Type', 'application/pdf')
            ->assertHeader('Content-Disposition', 'inline; filename="contract.pdf"');
        $this->assertStringContainsString('%PDF-1.4 local original bytes', $response->streamedContent());
    }
}