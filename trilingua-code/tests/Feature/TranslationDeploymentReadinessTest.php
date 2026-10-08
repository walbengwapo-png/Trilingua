<?php

namespace Tests\Feature;

use App\Models\User;
use App\Services\QuotaService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Queue;
use Mockery;
use Tests\TestCase;

class TranslationDeploymentReadinessTest extends TestCase
{
    use RefreshDatabase;

    public function test_startup_refuses_pending_migrations_and_accepts_applied_schema(): void
    {
        $this->artisan('deployment:validate-timeouts', ['--check-migrations' => true])->assertSuccessful();
        DB::table('migrations')->where('migration', '2026_09_28_000004_create_translation_quota_table')->delete();
        $this->artisan('deployment:validate-timeouts', ['--check-migrations' => true])
            ->expectsOutputToContain('2026_09_28_000004_create_translation_quota_table')
            ->assertFailed();
    }

    public function test_startup_refuses_missing_migration_repository(): void
    {
        DB::statement('DROP TABLE migrations');
        $this->artisan('deployment:validate-timeouts', ['--check-migrations' => true])
            ->expectsOutputToContain('Migration repository missing')->assertFailed();
    }

    public function test_quota_exception_cleans_upload_and_returns_logged_reference(): void
    {
        Queue::fake();
        Log::spy();
        $before = glob(storage_path('app/uploads/*'), GLOB_ONLYDIR) ?: [];
        $quota = Mockery::mock(QuotaService::class);
        $quota->shouldReceive('reserve')->once()->andThrow(new \RuntimeException('quota database unavailable'));
        $this->app->instance(QuotaService::class, $quota);
        $response = $this->actingAs(User::factory()->create())->postJson('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => UploadedFile::fake()->createWithContent('quota.docx', 'PK'.str_repeat('A', 256)),
        ]);
        $response->assertStatus(500)->assertJsonStructure(['error', 'request_id']);
        $reference = $response->json('request_id');
        $this->assertMatchesRegularExpression('/^[0-9a-f-]{36}$/', $reference);
        // Windows may retain an empty directory while UploadedFile holds its handle.
        $leftovers = array_diff(glob(storage_path('app/uploads/*'), GLOB_ONLYDIR) ?: [], $before);
        foreach ($leftovers as $directory) {
            $this->assertSame([], array_values(array_filter(glob($directory.'/*') ?: [], 'is_file')), 'Quota failure must not leave uploaded bytes.');
        }
        Queue::assertNothingPushed();
        Log::shouldHaveReceived('error')->with('Unexpected error in translation controller', Mockery::on(
            fn ($context) => $context['request_id'] === $reference
                && $context['stage'] === 'quota_reservation'
                && $context['exception_class'] === \RuntimeException::class
        ))->once();
    }
}
