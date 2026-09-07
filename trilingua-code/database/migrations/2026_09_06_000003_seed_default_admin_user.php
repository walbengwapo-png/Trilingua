<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;

return new class extends Migration
{
    /**
     * Create the default administrator on installations that do not yet have it.
     *
     * The existence check makes this safe for databases where the account was
     * created previously through DatabaseSeeder or manually.
     */
    public function up(): void
    {
        if (DB::table('users')->where('email', 'admin@example.com')->exists()) {
            return;
        }

        DB::table('users')->insert([
            'name' => 'Admin User',
            'email' => 'admin@example.com',
            'password' => Hash::make('password'),
            // PostgreSQL requires a boolean value rather than Laravel's
            // integer-bound boolean parameter; `true` is valid in SQLite too.
            'is_admin' => DB::raw('true'),
            'created_at' => now(),
            'updated_at' => now(),
        ]);
    }

    /**
     * Do not remove an account that may have since been used or customized.
     */
    public function down(): void
    {
        // Intentionally left in place.
    }
};
