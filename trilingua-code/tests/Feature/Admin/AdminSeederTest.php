<?php

namespace Tests\Feature\Admin;

use App\Models\User;
use Database\Seeders\AdminSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Hash;
use Tests\TestCase;

class AdminSeederTest extends TestCase
{
    use RefreshDatabase;

    public function test_creates_admin_and_reruns_without_changing_any_accounts(): void
    {
        $other = User::create(['name' => 'Other', 'email' => 'other@example.com', 'password' => 'existing-secret'])->fresh();
        $this->seed(AdminSeeder::class);
        $admin = User::where('email', 'admin@gmail.com')->firstOrFail();
        $this->assertTrue($admin->is_admin);
        $this->assertTrue(Hash::check('password', $admin->password));
        $original = $admin->getAttributes();
        $this->seed(AdminSeeder::class);
        $this->assertSame($original, $admin->fresh()->getAttributes());
        $this->assertSame($other->getAttributes(), $other->fresh()->getAttributes());
        $this->assertSame(2, User::count());
    }

    public function test_existing_email_is_not_promoted_or_password_reset(): void
    {
        $existing = User::create(['name' => 'Existing', 'email' => 'admin@gmail.com', 'password' => 'existing-secret'])->fresh();
        $original = $existing->getAttributes();
        $this->seed(AdminSeeder::class);
        $this->assertSame($original, $existing->fresh()->getAttributes());
    }
}
