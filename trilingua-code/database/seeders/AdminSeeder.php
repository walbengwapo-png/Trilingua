<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

class AdminSeeder extends Seeder
{
    /** Run explicitly with: php artisan db:seed --class=AdminSeeder */
    public function run(): void
    {
        // Explicit recovery credential; never reset an existing account.
        $admin = User::firstOrCreate(['email' => 'admin@gmail.com'], [
            'name' => 'Admin',
            'password' => 'password',
            'is_admin' => DB::raw('true'),
        ]);

        if (!$admin->wasRecentlyCreated) {
            $this->command?->warn('admin@gmail.com already exists; account and password unchanged.');
        }
    }
}
