<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    use WithoutModelEvents;

    /**
     * Seed the application's database.
     *
     * Development-only test account. Admin accounts are NEVER created or
     * modified here: first-admin creation is an explicit operator action via
     * `php artisan admin:create {email}`. This also guarantees seeding can
     * never turn an existing account into a known-password admin.
     */
    public function run(): void
    {
        User::updateOrCreate([
            'email' => 'test@example.com',
        ], [
            'name' => 'Test User',
        ]);
    }
}