<?php

namespace Tests\Feature\Admin;

use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Models\UserActivityLog;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Auth;
use Tests\TestCase;

class UserListViewsTest extends TestCase
{
    use RefreshDatabase;

    private function seedData(): array
    {
        $admin = User::factory()->create(['is_admin' => true, 'name' => 'Alice Admin']);
        $user = User::factory()->create([
            'name'  => 'Bob User',
            'email' => 'bob@example.com',
        ]);

        $text = TranslationHistory::create([
            'user_id' => $user->id,
            'translation_type' => 'text',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'source_text' => 'Hello world sample sentence.',
            'translated_text' => 'Kumusta kalibutan nga sample.',
            'status' => 'completed',
            'review_status' => 'verified',
            'quality_score' => 88,
            'reviewed_by' => $admin->id,
            'reviewed_at' => now()->subHours(3),
            'created_at' => now()->subDay(),
        ]);

        TranslationHistory::create([
            'user_id' => $user->id,
            'translation_type' => 'document',
            'original_filename' => 'contract.pdf',
            'translated_filename' => 'contract_ceb.pdf',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'status' => 'completed',
            'review_status' => 'pending',
            'created_at' => now()->subDay(),
        ]);

        TranslationEditLog::create([
            'translation_history_id' => $text->id,
            'admin_id' => $user->id,
            'action' => 'verify',
            'previous_text' => null,
            'new_text' => null,
            'created_at' => now()->subHours(3),
        ]);

        UserActivityLog::create([
            'user_id'         => $user->id,
            'attempted_email' => 'bob@example.com',
            'action'          => 'login_success',
            'ip_address'      => '127.0.0.1',
            'user_agent'      => 'phpunit',
            'created_at'      => now()->subDay(),
        ]);

        return [$admin, $user];
    }

    public function test_admin_can_view_the_user_list(): void
    {
        [$admin, $user] = $this->seedData();

        Auth::login($admin);

        $this->get('/admin/users')
            ->assertOk()
            ->assertSee('Users')
            ->assertSee('Bob User')
            ->assertSee('bob@example.com')
            ->assertSee('Alice Admin');
    }

    public function test_admin_can_view_user_detail_page(): void
    {
        [$admin, $user] = $this->seedData();

        Auth::login($admin);

        $this->get("/admin/users/{$user->id}")
            ->assertOk()
            ->assertSee('Bob User')
            ->assertSee('bob@example.com')
            ->assertSee('Total Translations')
            ->assertSee('Recent Translations')
            ->assertSee('Recent Account Activity');
    }

    public function test_admin_can_view_user_translations_page(): void
    {
        [$admin, $user] = $this->seedData();

        Auth::login($admin);

        $this->get("/admin/users/{$user->id}/translations")
            ->assertOk()
            ->assertSee("Bob User's Translations", false)
            ->assertSee('contract_ceb.pdf')
            ->assertSee('Hello world sample sentence.');
    }

    public function test_non_admin_cannot_access_user_list(): void
    {
        [$admin, $user] = $this->seedData();
        Auth::login($user);

        $this->get('/admin/users')->assertForbidden();
        $this->get("/admin/users/{$user->id}")->assertForbidden();
    }
}