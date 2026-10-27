<?php

namespace Tests\Feature\Admin;

use App\Models\TranslationEditLog;
use App\Models\TranslationHistory;
use App\Models\User;
use App\Models\UserActivityLog;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class AuditViewRenderTest extends TestCase
{
    use RefreshDatabase;

    /**
     * The audit log view must render without a Blade parse error and show a
     * clean 5-column table (Date | Type | Actor | Action | Details) using the
     * app's own design system classes.
     */
    public function test_audit_log_page_renders_merged_review_and_account_entries(): void
    {
        $admin = User::factory()->create(['is_admin' => true, 'name' => 'Alice Admin']);
        $user  = User::factory()->create(['name' => 'Bob User']);

        $translation = TranslationHistory::create([
            'user_id'           => $user->id,
            'translation_type'  => 'text',
            'source_language'   => 'English',
            'target_language'   => 'Cebuano',
            'source_text'       => 'Hello world, this is a sample sentence for audit.',
            'translated_text'   => 'Kumusta kalibutan, kini usa ka sample nga sentence.',
            'status'            => 'completed',
            'review_status'     => 'verified',
            'created_at'        => now()->subDay(),
        ]);

        TranslationEditLog::create([
            'translation_history_id' => $translation->id,
            'admin_id'               => $admin->id,
            'action'                 => 'verify',
            'created_at'             => now()->subDay(),
        ]);

        UserActivityLog::create([
            'user_id'    => $user->id,
            'action'     => 'login_success',
            'ip_address' => '127.0.0.1',
            'created_at' => now()->subHours(2),
        ]);

        $this->actingAs($admin);

        $response = $this->get('/admin/audit');

        $response->assertOk();
        $response->assertSee('Activity Log');
        $response->assertSee('Verify');
        $response->assertSee('Login success');
        $response->assertSee('Alice Admin');
        $response->assertSee('Bob User');

        // Design-system classes must be present, not Bootstrap's.
        $response->assertSee('class="review-table"', false);
        $response->assertSee('class="review-table-card"', false);
        $response->assertDontSee('table-striped');
    }

    public function test_audit_log_page_renders_empty_state(): void
    {
        $admin = User::factory()->create(['is_admin' => true]);

        $this->actingAs($admin);

        $this->get('/admin/audit')
            ->assertOk()
            ->assertSee('No audit log entries found.');
    }

    public function test_audit_log_action_filter_respects_query_string(): void
    {
        $admin = User::factory()->create(['is_admin' => true, 'name' => 'Alice Admin']);
        $user  = User::factory()->create(['name' => 'Bob User']);

        UserActivityLog::create([
            'user_id'    => $user->id,
            'action'     => 'login_success',
            'ip_address' => '127.0.0.1',
            'created_at' => now()->subHours(2),
        ]);
        UserActivityLog::create([
            'user_id'    => $user->id,
            'action'     => 'logout',
            'ip_address' => '127.0.0.1',
            'created_at' => now()->subHour(),
        ]);

        $this->actingAs($admin);

        $this->get('/admin/audit?type=account&action=logout')
            ->assertOk()
            ->assertSee('Logout')
            ->assertDontSee('Login Success');
    }
}