<?php

namespace Tests\Feature\Admin;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Tests\TestCase;

class AdminProvisioningTest extends TestCase
{
    use RefreshDatabase;

    public function test_fresh_migration_and_seed_leave_no_known_admin_login(): void
    {
        // RefreshDatabase has already migrated the guarded test database.
        $this->artisan('db:seed', ['--force' => true])->assertSuccessful();
        $this->assertFalse(Auth::attempt(['email' => 'admin@example.com', 'password' => 'password']));
        $this->assertNull(User::where('email', 'admin@example.com')->first());
    }

    public function test_seeding_cannot_turn_an_existing_account_into_a_known_password_admin(): void
    {
        User::factory()->create([
            'email' => 'admin@example.com',
            'is_admin' => true,
            'password' => Hash::make('An-existing-admin-secret-1'),
        ]);

        $this->artisan('db:seed')->assertSuccessful();

        $admin = User::where('email', 'admin@example.com')->first();
        $this->assertNotNull($admin);
        $this->assertTrue($admin->is_admin);
        $this->assertTrue(
            Hash::check('An-existing-admin-secret-1', $admin->password),
            'Seeding must not change an existing administrator password.'
        );
        $this->assertFalse(
            Hash::check('password', $admin->password),
            'Seeding must never reset an administrator to the known default password.'
        );
    }

    public function test_admin_create_creates_a_first_admin(): void
    {
        $this->artisan('admin:create', [
            'email' => 'operator@example.com',
            '--password' => 'X9!kTq-bVn2$mzR4',
        ])->assertSuccessful();

        $admin = User::where('email', 'operator@example.com')->first();
        $this->assertNotNull($admin);
        $this->assertTrue($admin->is_admin);
        $this->assertTrue(Hash::check('X9!kTq-bVn2$mzR4', $admin->password));
    }

    public function test_admin_create_rejects_known_and_weak_passwords(): void
    {
        foreach (['password', 'short'] as $bad) {
            $this->artisan('admin:create', [
                'email' => 'badadmin@example.com',
                '--password' => $bad,
            ])->assertFailed();

            $this->assertNull(
                User::where('email', 'badadmin@example.com')->first(),
                "Weak password '{$bad}' must not create an account."
            );
        }
    }
}