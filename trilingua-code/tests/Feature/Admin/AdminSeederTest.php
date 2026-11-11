<?php

namespace Tests\Feature\Admin;

use App\Models\User;
use Database\Seeders\AdminSeeder;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Schema;
use Tests\TestCase;

class AdminSeederTest extends TestCase
{
    protected function setUp(): void
    {
        parent::setUp();

        // TestCase verifies SQLite :memory: before this schema is created.
        Schema::create('users', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            $table->string('email')->unique();
            $table->string('password');
            $table->boolean('is_admin')->default(false);
            $table->timestamps();
        });
    }

    public function test_creates_admin_and_reruns_without_changing_any_accounts(): void
    {
        $other = User::create(['name' => 'Other', 'email' => 'other@example.com', 'password' => 'existing-secret']);
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
        $existing = User::create(['name' => 'Existing', 'email' => 'admin@gmail.com', 'password' => 'existing-secret']);
        $original = $existing->getAttributes();
        $this->seed(AdminSeeder::class);
        $this->assertSame($original, $existing->fresh()->getAttributes());
    }
}
