<?php

namespace Tests\Feature\Auth;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class GuestRouteProtectionTest extends TestCase
{
    use RefreshDatabase;

    public function test_authenticated_users_are_redirected_away_from_guest_only_auth_pages(): void
    {
        $user = User::factory()->create();

        foreach ([
            '/login',
            '/register',
            '/forgot-password',
            '/reset-password/example-token',
        ] as $path) {
            $this->actingAs($user)
                ->get($path)
                ->assertRedirect(route('dashboard'));
        }
    }
}
