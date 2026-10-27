<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

/** Assertions reproduce the observed defects; passing means the defect exists. */
class AuditProbesTest extends TestCase
{
    use RefreshDatabase;

    private function payload(string $text = 'Hello there.'): array
    {
        return ['text' => $text, 'source_lang' => 'English', 'target_lang' => 'Cebuano', 'mode' => 'fast'];
    }

    public function test_zero_string_is_rejected(): void
    {
        Http::fake();
        $this->actingAs(User::factory()->create())->postJson('/translate', $this->payload('0'))->assertStatus(422);
        Http::assertNothingSent();
    }

    public function test_empty_success_envelope_creates_completed_history(): void
    {
        Http::fake(['*' => Http::response([], 200)]);
        $this->actingAs(User::factory()->create())->postJson('/translate', $this->payload())
            ->assertOk()->assertJsonPath('translated', '')->assertJsonPath('success', true)->assertJsonPath('saved', true);
        $this->assertDatabaseHas('translation_history', ['status' => 'completed', 'translated_text' => '']);
    }

    public function test_explicit_failed_envelope_creates_completed_history(): void
    {
        Http::fake(['*' => Http::response(['success' => false, 'error_message' => 'offline failure'], 200)]);
        $this->actingAs(User::factory()->create())->postJson('/translate', $this->payload())
            ->assertOk()->assertJsonPath('success', false)->assertJsonPath('saved', true);
        $this->assertDatabaseHas('translation_history', ['status' => 'completed', 'translated_text' => '']);
    }

    public function test_internal_python_error_is_returned_to_user(): void
    {
        Http::fake(['*' => Http::response(['detail' => 'offline internal diagnostic /private/backend/path'], 500)]);
        $this->actingAs(User::factory()->create())->postJson('/translate', $this->payload())
            ->assertStatus(500)->assertJsonPath('error', 'offline internal diagnostic /private/backend/path');
    }
}
