<?php

namespace Tests\Feature;

use App\Models\User;
use App\Services\HistoryService;
use App\Support\LoginDestination;
use App\Support\UserMessages;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Foundation\Http\Middleware\ValidateCsrfToken;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use Illuminate\Support\Facades\Schema;
use Tests\TestCase;

class ExperienceRecoveryTest extends TestCase
{
    protected function setUp(): void
    {
        parent::setUp();
        $this->withoutVite();
        config(['app.debug' => false]);
        Schema::create('users', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            $table->string('email')->unique();
            $table->string('password');
            $table->boolean('is_admin')->default(false);
            $table->string('theme')->default('light');
            $table->rememberToken();
            $table->timestamps();
        });
        Schema::create('user_activity_log', function (Blueprint $table) {
            $table->id();
            $table->unsignedBigInteger('user_id')->nullable();
            $table->string('attempted_email')->nullable();
            $table->string('action');
            $table->string('ip_address')->nullable();
            $table->text('user_agent')->nullable();
        });
    }

    private function enforceCsrf(): void
    {
        $this->app->bind(ValidateCsrfToken::class, fn ($app) => new class($app, $app['encrypter']) extends ValidateCsrfToken {
            protected function runningUnitTests() { return false; }
        });
    }

    public function test_expired_login_refreshes_form_without_flashing_password(): void
    {
        $this->enforceCsrf();
        $this->post('/login', ['email' => 'reader@example.test', 'password' => 'private-password'])
            ->assertRedirect(route('login'))
            ->assertSessionHas('notice', 'login_form_expired')
            ->assertSessionHas('_old_input', ['email' => 'reader@example.test']);
        $this->get('/login')->assertOk()->assertSee('Your sign-in page expired.')
            ->assertDontSee('private-password')->assertHeader('Cache-Control', 'no-store, private');
        $this->assertGuest();
    }

    public function test_expired_json_request_keeps_419_and_does_not_redirect(): void
    {
        $this->enforceCsrf();
        $this->postJson('/login', ['email' => 'reader@example.test', 'password' => 'private-password'])
            ->assertStatus(419)->assertJsonPath('code', 'session_expired')
            ->assertDontSee('CSRF')->assertDontSee('private-password');
    }

    public function test_login_with_fresh_token_succeeds_and_discards_stale_destination(): void
    {
        $this->enforceCsrf();
        $user = User::create(['name' => 'Reader', 'email' => 'reader@example.test', 'password' => 'test-password']);
        $this->withSession(['_token' => 'fresh-token', 'url.intended' => url('/deleted-page')])
            ->post('/login', ['_token' => 'fresh-token', 'email' => $user->email, 'password' => 'test-password'])
            ->assertRedirect(route('dashboard'))->assertSessionMissing('url.intended');
        $this->assertAuthenticatedAs($user);
    }

    public function test_invalid_credentials_and_attempt_limit_are_preserved(): void
    {
        User::create(['name' => 'Reader', 'email' => 'reader@example.test', 'password' => 'correct-password']);
        for ($i = 0; $i < 5; $i++) {
            $this->from('/login')->post('/login', ['email' => 'reader@example.test', 'password' => 'wrong'])
                ->assertRedirect('/login')->assertSessionHasErrors('email');
        }
        $this->postJson('/login', ['email' => 'reader@example.test', 'password' => 'wrong'])
            ->assertStatus(429)->assertJsonPath('code', 'rate_limited');
        $this->assertGuest();
    }

    public function test_intended_destinations_only_allow_same_origin_pages(): void
    {
        $request = Request::create(url('/login'));
        $request->setLaravelSession($this->app['session.store']);
        foreach (['/history/76/view', '/documents', '/history?type=text'] as $target) {
            $request->session()->put('url.intended', $target);
            $this->assertSame(url($target), LoginDestination::take($request));
            $this->assertFalse($request->session()->has('url.intended'));
        }
        foreach (['/history/76', '/translate/status/uuid', '/no-such-page', '/admin/jobs',
            '//evil.test/dashboard', 'https://evil.test/dashboard', url('/login'),
            'http://user@localhost/dashboard', '/\\evil.test/dashboard'] as $target) {
            $request->session()->put('url.intended', $target);
            $this->assertSame(route('dashboard'), LoginDestination::take($request), $target);
        }
        $request->setUserResolver(fn () => new User(['is_admin' => true]));
        $request->session()->put('url.intended', '/admin/jobs');
        $this->assertSame(url('/admin/jobs'), LoginDestination::take($request));
    }

    public function test_recent_text_and_document_links_open_page_and_preview_api_remains_json(): void
    {
        $user = new User(['name' => 'Reader', 'email' => 'reader@example.test']);
        $user->id = 7;
        $this->actingAs($user);
        $record = ['id' => 76, 'user_id' => 7, 'translation_type' => 'text', 'source_text' => 'Original text',
            'translated_text' => 'Translated text', 'created_at' => '2026-11-14T12:00:00Z', 'source_language' => 'English', 'target_language' => 'Cebuano'];
        $document = array_merge($record, ['id' => 77, 'translation_type' => 'document', 'original_filename' => 'Guide.pdf']);
        $html = view('dashboard', ['stats' => [], 'recentRecords' => [$record, $document], 'error' => false])->render();
        $this->assertStringContainsString('href="'.route('history.view', 76).'"', $html);
        $this->assertStringContainsString('href="'.route('history.view', 77).'"', $html);
        $this->assertStringNotContainsString('href="'.route('history.detail', 76).'"', $html);
        $this->mock(HistoryService::class)->shouldReceive('getRecordWithTranslations')->with(76)->andReturn($record);
        $this->get('/history/76/view')->assertOk()->assertSee('Translation Details')->assertSee('Translated text');
        $this->getJson('/history/76')->assertOk()->assertJsonPath('id', 76)->assertJsonPath('translated_text', 'Translated text');
    }

    public function test_translation_details_still_reject_another_owner(): void
    {
        $user = new User(['name' => 'Reader']);
        $user->id = 7;
        $this->actingAs($user);
        $this->mock(HistoryService::class)->shouldReceive('getRecordWithTranslations')->with(76)
            ->andReturn(['id' => 76, 'user_id' => 99]);
        $this->get('/history/76/view')->assertForbidden()->assertSee('You do not have access');
        $this->getJson('/history/76')->assertForbidden();
    }

    public function test_notification_links_open_details_and_keep_admin_review_destination(): void
    {
        Schema::create('translation_history', function (Blueprint $table) {
            $table->id(); $table->unsignedBigInteger('user_id');
            $table->string('original_filename')->nullable(); $table->string('translated_filename')->nullable();
            $table->text('source_text')->nullable();
        });
        Schema::create('notifications', function (Blueprint $table) {
            $table->uuid('id')->primary(); $table->string('type');
            $table->morphs('notifiable'); $table->text('data');
            $table->timestamp('read_at')->nullable(); $table->timestamps();
        });
        $user = User::create(['name' => 'Reader', 'email' => 'reader@example.test', 'password' => 'test-password']);
        \Illuminate\Support\Facades\DB::table('translation_history')->insert([
            'id' => 76, 'user_id' => $user->id, 'original_filename' => 'Guide.pdf',
        ]);
        $user->notifications()->create(['id' => '11111111-2222-4333-8444-555555555555',
            'type' => \App\Notifications\PriorityRequestRaised::class, 'data' => ['translation_id' => 76]]);
        $this->actingAs($user)->getJson('/notifications/data')
            ->assertOk()->assertJsonPath('notifications.0.url', route('history.view', 76));
        $user->is_admin = true;
        $this->getJson('/notifications/data')->assertOk()
            ->assertJsonPath('notifications.0.url', route('admin.review.show', 76));
    }

    public function test_errors_keep_status_retry_header_and_safe_reference(): void
    {
        Route::get('/_test-error/{status}', function (int $status) {
            abort($status, 'SQLSTATE private details', $status === 429 ? ['Retry-After' => 60] : []);
        });
        foreach ([403 => 'access_denied', 404 => 'page_missing', 419 => 'session_expired',
            429 => 'rate_limited', 500 => 'server_error', 503 => 'service_unavailable'] as $status => $code) {
            $response = $this->getJson('/_test-error/'.$status)->assertStatus($status)->assertJsonPath('code', $code)
                ->assertDontSee('SQLSTATE');
            if ($status === 429) $response->assertHeader('Retry-After', '60');
            if ($status >= 500) $this->assertMatchesRegularExpression('/^[a-f0-9-]{36}$/', $response->json('reference'));
        }
        $this->get('/_test-error/500')->assertStatus(500)->assertSee('Reference:')->assertDontSee('SQLSTATE');
        $this->get('/missing-page')->assertNotFound()->assertSee('Open dashboard')->assertDontSee('team has been notified');
    }

    public function test_readable_document_errors_preserve_reference_and_machine_exception(): void
    {
        $id = '11111111-2222-4333-8444-555555555555';
        $exception = new \App\Exceptions\DocumentJobUncertainException($id);
        $this->assertStringStartsWith('Document status is temporarily unavailable.', $exception->getMessage());
        $display = UserMessages::readable(['message' => $exception->getMessage()]);
        $this->assertStringContainsString('Do not upload the file again.', $display);
        $this->assertStringContainsString($id, $display);
        $this->assertStringNotContainsString('Operator reconciliation', $display);
        $this->assertSame(UserMessages::get('pdf_save_failed')['message'], UserMessages::readable(
            json_encode(['message' => 'Saved PDF validation failed: Block 15: missing rendered text'])));
        foreach (['SQLSTATE secret', '<html>private error</html>', 'C:\\private\\secret.txt'] as $raw) {
            $this->assertSame(UserMessages::get('action_failed')['message'], UserMessages::readable($raw));
        }
    }
}
