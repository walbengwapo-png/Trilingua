<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class TranslationPreferencesTest extends TestCase
{
    use RefreshDatabase;

    public function test_user_can_save_translation_and_accessibility_preferences(): void
    {
        $user = User::factory()->create(['theme' => 'light']);

        $response = $this->actingAs($user)->post('/settings/general', [
            'theme' => 'dark',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'translation_mode' => 'balanced',
            'timezone' => 'Asia/Manila',
            'date_format' => 'Y-m-d H:i T',
            'notifications' => [
                'translation_complete' => '1',
                'review_updates' => '0',
            ],
            'reduced_motion' => '1',
        ]);

        $response->assertRedirect();
        $response->assertSessionHas('general_success');
        $preferences = $user->fresh()->resolvedPreferences();
        $this->assertSame('dark', $user->fresh()->theme);
        $this->assertSame('balanced', $preferences['translation_mode']);
        $this->assertTrue($preferences['notifications']['translation_complete']);
        $this->assertFalse($preferences['notifications']['review_updates']);
        $this->assertTrue($preferences['reduced_motion']);
    }

    public function test_user_cannot_save_the_same_default_source_and_target_language(): void
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)->from('/settings')->post('/settings/general', [
            'theme' => 'light',
            'source_language' => 'Cebuano',
            'target_language' => 'Cebuano',
        ]);

        $response->assertRedirect('/settings');
        $response->assertSessionHasErrors('target_language');
    }
}
