<?php

namespace App\Console\Commands;

use App\Models\User;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;

class CreateAdminUser extends Command
{
    protected $signature = 'admin:create
                            {email : Administrator email address}
                            {--password= : Password (interactive prompt if omitted)}
                            {--force : Update an existing account to admin with this password}';

    protected $description = 'Create (or promote) a single administrator with an operator-supplied password.';

    public function handle(): int
    {
        $email = strtolower(trim((string) $this->argument('email')));

        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
            $this->error('Invalid email address.');

            return self::FAILURE;
        }

        $existing = User::where('email', $email)->first();
        if ($existing !== null && $existing->is_admin && !$this->option('force')) {
            $this->error("User {$email} is already an administrator. Use --force only to reset its password deliberately.");

            return self::FAILURE;
        }

        $password = $this->option('password')
            ?? $this->secret('Password for the new administrator');
        $password = (string) $password;

        if (!$this->isAcceptablePassword($password, $email)) {
            $this->error('Password is too weak or matches a known default. Use a unique, non-obvious password of at least 12 characters.');

            return self::FAILURE;
        }

        User::updateOrCreate(
            ['email' => $email],
            [
                'name'     => $existing?->name ?? ucfirst((string) strstr($email, '@', true)),
                'is_admin' => DB::raw('true'),
                'password' => Hash::make($password),
            ]
        );

        $this->info("Administrator {$email} is ready.");
        // Never echo the password.

        return self::SUCCESS;
    }

    private function isAcceptablePassword(string $password, string $email): bool
    {
        if (strlen($password) < 12) {
            return false;
        }
        if (strtolower($password) === 'password') {
            return false;
        }
        if (stripos($password, strstr($email, '@', true) ?: '') !== false) {
            return false;
        }

        return true;
    }
}