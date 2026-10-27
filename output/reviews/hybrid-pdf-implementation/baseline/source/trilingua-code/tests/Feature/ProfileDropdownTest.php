<?php

namespace Tests\Feature;

use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Models\UserActivityLog;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ProfileDropdownTest extends TestCase
{
    use RefreshDatabase;

    public function test_header_dropdown_includes_profile_item_linking_to_profile_page(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)
            ->get('/dashboard')
            ->assertOk()
            ->assertSee('Profile')
            ->assertSee(route('profile'));
    }

    public function test_profile_page_renders_user_details(): void
    {
        $user = User::factory()->create([
            'name' => 'Jane Doe',
            'email' => 'jane@example.com',
        ]);

        $this->actingAs($user)
            ->get('/profile')
            ->assertOk()
            ->assertSee('Jane Doe')
            ->assertSee('jane@example.com')
            ->assertSee('Member')
            ->assertSee('Email & Password')
            ->assertDontSee('Admin Dashboard');
    }

    public function test_profile_page_shows_admin_role_and_google_account_type(): void
    {
        $user = User::factory()->create([
            'name' => 'Bob Admin',
            'is_admin' => true,
            'google_id' => 'google-abc-123',
        ]);

        $this->actingAs($user)
            ->get('/profile')
            ->assertOk()
            ->assertSee('Bob Admin')
            ->assertSee('Administrator')
            ->assertSee('Google')
            ->assertSee('Admin Dashboard');
    }

    public function test_profile_page_renders_translation_and_activity_summaries(): void
    {
        $user = User::factory()->create(['name' => 'Carla User']);

        TranslationHistory::create([
            'user_id' => $user->id,
            'translation_type' => 'document',
            'original_filename' => 'report.pdf',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'status' => 'completed',
            'review_status' => 'verified',
            'quality_score' => 92,
            'created_at' => now()->subDays(2),
        ]);

        TranslationHistory::create([
            'user_id' => $user->id,
            'translation_type' => 'text',
            'source_text' => 'Hello world sample sentence.',
            'source_language' => 'English',
            'target_language' => 'Filipino',
            'status' => 'completed',
            'review_status' => 'pending',
            'created_at' => now()->subDay(),
        ]);

        UserActivityLog::create([
            'user_id' => $user->id,
            'action' => 'login_success',
            'ip_address' => '127.0.0.1',
            'created_at' => now()->subDays(3),
        ]);
        UserActivityLog::create([
            'user_id' => $user->id,
            'action' => 'account_updated',
            'ip_address' => '127.0.0.1',
            'created_at' => now()->subDay(),
        ]);
        UserActivityLog::create([
            'user_id' => $user->id,
            'action' => 'login_failed',
            'ip_address' => '127.0.0.1',
            'created_at' => now(),
        ]);

        $this->actingAs($user)
            ->get('/profile')
            ->assertOk()
            ->assertSee('Translation Summary')
            ->assertSee('Activity Summary')
            ->assertSee('Language pairs')
            ->assertSee('Documents')
            ->assertSee('report.pdf')
            ->assertSee('Hello world')
            ->assertSee('Verified')
            ->assertSee('Successful login')
            ->assertSee('Account updated')
            ->assertSee('Failed login')
            ->assertSee('Last login');
    }

    public function test_admin_profile_shows_work_summary_instead_of_translation_summary(): void
    {
        $admin = User::factory()->create([
            'name' => 'Rhoda Admin',
            'is_admin' => true,
        ]);

        $doc = TranslationHistory::create([
            'user_id' => $admin->id,
            'translation_type' => 'document',
            'original_filename' => 'contract.pdf',
            'translated_filename' => 'contract_translated.pdf',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'status' => 'completed',
            'review_status' => 'verified',
            'created_at' => now()->subDays(2),
        ]);

        $text = TranslationHistory::create([
            'user_id' => $admin->id,
            'translation_type' => 'text',
            'source_text' => 'Sample paragraph for the admin review log.',
            'source_language' => 'English',
            'target_language' => 'Filipino',
            'status' => 'completed',
            'review_status' => 'pending',
            'created_at' => now()->subDay(),
        ]);

        // One pending item remains in the global queue.
        TranslationHistory::create([
            'user_id' => $admin->id,
            'translation_type' => 'text',
            'source_text' => 'Still waiting in the queue.',
            'source_language' => 'English',
            'target_language' => 'Filipino',
            'status' => 'completed',
            'review_status' => 'pending',
            'created_at' => now(),
        ]);

        TranslationEditLog::create([
            'translation_history_id' => $doc->id,
            'admin_id' => $admin->id,
            'action' => 'verify',
            'created_at' => now()->subDays(2),
        ]);
        TranslationEditLog::create([
            'translation_history_id' => $text->id,
            'admin_id' => $admin->id,
            'action' => 'edit',
            'created_at' => now()->subDay(),
        ]);
        TranslationEditLog::create([
            'translation_history_id' => $text->id,
            'admin_id' => $admin->id,
            'action' => 'flag',
            'created_at' => now()->subHours(2),
        ]);

        $this->actingAs($admin)
            ->get('/profile')
            ->assertOk()
            ->assertSee('Admin Work Summary')
            ->assertSee('Reviews')
            ->assertSee('Items reviewed')
            ->assertSee('Verifications')
            ->assertSee('Edits')
            ->assertSee('Flags')
            ->assertSee('This month')
            ->assertSee('Pending queue')
            ->assertSee('Verify')
            ->assertSee('Edit')
            ->assertSee('Flag')
            ->assertSee('contract_translated.pdf')
            ->assertDontSee('Translation Summary')
            ->assertDontSee('Activity Summary');
    }

    public function test_settings_accepts_section_param_and_remembers_it(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)
            ->get('/settings?section=account')
            ->assertOk()
            ->assertSee('Account Settings');

        $this->assertSame('account', session('_settings_section'));
    }
}