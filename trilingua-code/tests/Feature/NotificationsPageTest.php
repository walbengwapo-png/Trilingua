<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\User;
use App\Notifications\PriorityRequestRaised;
use App\Notifications\TranslationAwaitingReview;
use App\Notifications\TranslationCompleted;
use App\Notifications\TranslationFailed;
use App\Services\HistoryService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Notifications\DatabaseNotification;
use Illuminate\Pagination\LengthAwarePaginator;
use Illuminate\Support\Facades\Notification;
use Tests\TestCase;

/**
 * GET /notifications — full notifications page + admin notification fan-out.
 */
class NotificationsPageTest extends TestCase
{
    use RefreshDatabase;

    private function makeUser(bool $admin = false): User
    {
        return User::factory()->create(['is_admin' => $admin]);
    }

    private function makeDoc(User $user): TranslationHistory
    {
        return TranslationHistory::create([
            'user_id'             => $user->id,
            'translation_type'    => 'document',
            'original_filename'   => 'contract.pdf',
            'translated_filename' => 'contract_ceb.pdf',
            'source_language'     => 'English',
            'target_language'     => 'Cebuano',
            'status'              => 'completed',
        ]);
    }

    public function test_page_renders_for_authenticated_user(): void
    {
        $user = $this->makeUser();

        $response = $this->actingAs($user)->get('/notifications');

        $response->assertOk();
        $response->assertSee('Notifications');
    }

    public function test_page_requires_auth(): void
    {
        $this->get('/notifications')->assertRedirect(route('login'));
    }

    public function test_page_renders_unread_filter(): void
    {
        $user  = $this->makeUser();
        $doc   = $this->makeDoc($user);

        $user->notify(new TranslationAwaitingReview($doc, $user->name));
        $user->unreadNotifications()->update(['read_at' => now()]);
        $user->notify(new TranslationAwaitingReview($doc, $user->name));

        $response = $this->actingAs($user)->get('/notifications?unread=1');

        $response->assertOk();
        $response->assertSee('Unread');
        $this->assertSame(1, DatabaseNotification::whereNull('read_at')->count());
    }

    public function test_mark_all_read_endpoint_works(): void
    {
        $user = $this->makeUser();
        $doc  = $this->makeDoc($user);

        $user->notify(new TranslationAwaitingReview($doc, $user->name));
        $user->notify(new TranslationAwaitingReview($doc, $user->name));

        $this->actingAs($user)->postJson('/notifications/read', [])
            ->assertOk()
            ->assertJson(['success' => true]);

        $this->assertSame(0, $user->unreadNotifications()->count());
    }

    public function test_awaiting_review_notifies_all_admins(): void
    {
        Notification::fake();

        $admin1 = $this->makeUser(true);
        $admin2 = $this->makeUser(true);
        $user   = $this->makeUser(false);
        $doc    = $this->makeDoc($user);

        \App\Support\AdminNotifier::awaitingReview($doc, $user->name);

        Notification::assertSentTo($admin1, TranslationAwaitingReview::class);
        Notification::assertSentTo($admin2, TranslationAwaitingReview::class);
        Notification::assertNotSentTo($user, TranslationAwaitingReview::class);
    }

    public function test_priority_request_notifies_all_admins(): void
    {
        Notification::fake();

        $admin = $this->makeUser(true);
        $user  = $this->makeUser(false);
        $doc   = $this->makeDoc($user);

        \App\Support\AdminNotifier::priorityRequestRaised($doc, $user->name);

        Notification::assertSentTo($admin, PriorityRequestRaised::class);
        Notification::assertNotSentTo($user, PriorityRequestRaised::class);
    }

    public function test_toggling_priority_on_sends_admin_notification(): void
    {
        Notification::fake();

        $admin = $this->makeUser(true);
        $user  = $this->makeUser(false);
        $doc   = $this->makeDoc($user);

        $this->actingAs($user)->postJson("/history/{$doc->id}/priority");

        Notification::assertSentTo($admin, PriorityRequestRaised::class);
    }

    public function test_get_bookmarked_compiles_boolean_literal_not_int(): void
    {
        // Postgres has no boolean = integer operator. Passing a PHP true to
        // where() would be bound as int 1 and blow up on Supabase; the query
        // must emit a real `true` literal instead.
        $sql = \App\Models\TranslationHistory::where('user_id', 1)
            ->where('is_bookmarked', '=', \Illuminate\Support\Facades\DB::raw('true'))
            ->toSql();

        $this->assertStringContainsString('"is_bookmarked" = true', $sql);
        $this->assertStringNotContainsString('"is_bookmarked" = ?', $sql);
    }

    public function test_get_bookmarked_page_loads_after_bookmark_toggle(): void
    {
        $user = $this->makeUser();
        $doc  = $this->makeDoc($user);

        $this->actingAs($user)->postJson("/history/{$doc->id}/bookmark")->assertOk();

        $response = $this->actingAs($user)->get('/bookmarks');

        $response->assertOk();
        $response->assertDontSee('Unable to load bookmarks.');
    }

    public function test_history_bookmark_buttons_are_wired_with_data_id(): void
    {
        // Regression: the history page bookmark buttons used to be a visual-only
        // toggle that never hit the backend. They must carry data-id so the JS
        // can POST /history/{id}/bookmark, and must reflect the saved state.
        $user = $this->makeUser();
        $bookmarked   = $this->makeDoc($user);
        $notBookmarked = $this->makeDoc($user);

        $bookmarked->update([
            'is_bookmarked'  => true,
            'bookmarked_at'  => now(),
        ]);

        $paginator = new LengthAwarePaginator(
            collect([$bookmarked, $notBookmarked]),
            2,
            50,
            1,
        );

        $this->mock(HistoryService::class, function ($mock) use ($paginator) {
            $mock->shouldReceive('getHistoryPaginated')
                 ->once()
                 ->andReturn($paginator);
        });

        $response = $this->actingAs($user)->get('/history');

        $response->assertOk();
        $response->assertSee('data-id="' . $bookmarked->id . '"', false);
        $response->assertSee('data-id="' . $notBookmarked->id . '"', false);
        $response->assertSee('bookmark-btn--active', false);
        $response->assertSee('Bookmark (persisted)', false);
        $response->assertSee("/history/' + encodeURIComponent(id) + '/bookmark", false);
    }

    public function test_history_priority_buttons_are_wired_with_data_id(): void
    {
        $user = $this->makeUser();
        $pending = $this->makeDoc($user);
        $verified = $this->makeDoc($user);
        $verified->update(['review_status' => 'verified']);

        $paginator = new LengthAwarePaginator(
            collect([$pending, $verified]),
            2,
            50,
            1,
        );

        $this->mock(HistoryService::class, function ($mock) use ($paginator) {
            $mock->shouldReceive('getHistoryPaginated')
                 ->once()
                 ->andReturn($paginator);
        });

        $response = $this->actingAs($user)->get('/history');

        $response->assertOk();
        // Pending record gets a wired priority button with data-id.
        $response->assertSee('data-id="' . $pending->id . '"', false);
        $response->assertSee('priority-btn', false);
        $response->assertSee('Request priority review', false);
        $response->assertSee("/history/' + encodeURIComponent(id) + '/priority", false);
    }

    public function test_admin_awaiting_review_notification_links_to_review_show(): void
    {
        $admin = $this->makeUser(true);
        $user  = $this->makeUser(false);
        $doc   = $this->makeDoc($user);

        $admin->notify(new TranslationAwaitingReview($doc, $user->name));

        $response = $this->actingAs($admin)->get('/notifications');

        $response->assertOk();
        $response->assertSee('href="' . route('admin.review.show', $doc->id) . '"', false);
        $response->assertDontSee('href="' . route('history.detail', $doc->id) . '"', false);
    }

    public function test_admin_priority_notification_links_to_review_show(): void
    {
        $admin = $this->makeUser(true);
        $user  = $this->makeUser(false);
        $doc   = $this->makeDoc($user);

        $admin->notify(new PriorityRequestRaised($doc, $user->name));

        $response = $this->actingAs($admin)->get('/notifications');

        $response->assertOk();
        $response->assertSee('href="' . route('admin.review.show', $doc->id) . '"', false);
    }

    public function test_user_completed_notification_links_to_saved_translations_with_open(): void
    {
        $user = $this->makeUser();
        $doc  = $this->makeDoc($user);

        $user->notify(new TranslationCompleted($doc));

        $response = $this->actingAs($user)->get('/notifications');

        $response->assertOk();
        $response->assertSee('href="' . route('history', ['open' => $doc->id]) . '"', false);
        $response->assertDontSee('href="' . route('history.detail', $doc->id) . '"', false);
    }

    public function test_failed_notification_links_to_saved_translations_page(): void
    {
        $user = $this->makeUser();

        $user->notify(new TranslationFailed('broken.pdf', 'Something broke'));

        $response = $this->actingAs($user)->get('/notifications');

        $response->assertOk();
        $response->assertSee('href="' . route('history') . '"', false);
    }

    public function test_notifications_data_includes_target_url(): void
    {
        $admin = $this->makeUser(true);
        $user  = $this->makeUser(false);
        $doc   = $this->makeDoc($user);

        $admin->notify(new PriorityRequestRaised($doc, $user->name));
        $user->notify(new TranslationCompleted($doc));

        $this->actingAs($admin)->getJson('/notifications/data')
            ->assertOk()
            ->assertJsonFragment(['url' => route('admin.review.show', $doc->id)]);

        $this->actingAs($user)->getJson('/notifications/data')
            ->assertOk()
            ->assertJsonFragment(['url' => route('history', ['open' => $doc->id])]);
    }

    public function test_history_page_passes_open_query_param(): void
    {
        $user = $this->makeUser();

        $this->mock(HistoryService::class, function ($mock) {
            $mock->shouldReceive('getHistoryPaginated')
                 ->once()
                 ->andReturn(new LengthAwarePaginator(collect(), 0, 50, 1));
        });

        $response = $this->actingAs($user)->get('/history?open=42');

        $response->assertOk();
        $this->assertSame(42, $response->viewData('openId'));
    }
}
