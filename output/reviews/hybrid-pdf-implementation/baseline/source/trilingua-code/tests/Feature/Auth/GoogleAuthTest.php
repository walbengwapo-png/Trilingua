<?php

namespace Tests\Feature\Auth;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Socialite\Facades\Socialite;
use Laravel\Socialite\Two\GoogleProvider;
use Laravel\Socialite\Two\User as SocialiteUser;
use Mockery;
use Tests\TestCase;

class GoogleAuthTest extends TestCase
{
    use RefreshDatabase;

    private function mockGoogleUser(string $id = 'google-123', string $email = 'gmail.user@gmail.com', ?string $name = 'Gmail User'): void
    {
        $socialiteUser = Mockery::mock(SocialiteUser::class);
        $socialiteUser->shouldReceive('getId')->andReturn($id);
        $socialiteUser->shouldReceive('getEmail')->andReturn($email);
        $socialiteUser->shouldReceive('getName')->andReturn($name);
        $socialiteUser->shouldReceive('getAvatar')->andReturn(null);

        $provider = Mockery::mock(GoogleProvider::class);
        $provider->shouldReceive('user')->andReturn($socialiteUser);

        Socialite::shouldReceive('driver')->with('google')->andReturn($provider);
    }

    public function test_redirect_when_not_configured_sends_back_to_login(): void
    {
        // Simulate a deployment where GOOGLE_CLIENT_ID is not configured.
        config(['services.google.client_id' => null]);

        $this->get(route('auth.google.redirect'))
            ->assertRedirect(route('login'))
            ->assertSessionHasErrors('email');
    }

    public function test_callback_creates_a_new_user_and_signs_them_in(): void
    {
        $this->mockGoogleUser();

        $this->get(route('auth.google.callback'))
            ->assertRedirect(route('dashboard'));

        $this->assertAuthenticated();

        $user = User::where('email', 'gmail.user@gmail.com')->first();
        $this->assertNotNull($user);
        $this->assertSame('google-123', $user->google_id);
        $this->assertSame('Gmail User', $user->name);
    }

    public function test_callback_links_existing_account_by_email(): void
    {
        $user = User::factory()->create([
            'name'     => 'Existing',
            'email'    => 'gmail.user@gmail.com',
            'password' => bcrypt('secret-password'),
        ]);

        $this->mockGoogleUser();

        $this->get(route('auth.google.callback'))
            ->assertRedirect(route('dashboard'));

        $this->assertAuthenticatedAs($user);
        $this->assertSame('google-123', $user->fresh()->google_id);
    }

    public function test_callback_keeps_google_id_for_repeat_logins(): void
    {
        $this->mockGoogleUser();

        $this->get(route('auth.google.callback'))->assertRedirect(route('dashboard'));
        $this->post(route('logout'));

        $this->mockGoogleUser();

        $this->get(route('auth.google.callback'))->assertRedirect(route('dashboard'));

        $this->assertSame(1, User::where('email', 'gmail.user@gmail.com')->count());
        $this->assertAuthenticated();
    }
}