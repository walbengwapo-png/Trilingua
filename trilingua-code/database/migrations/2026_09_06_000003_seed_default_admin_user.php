<?php

use Illuminate\Database\Migrations\Migration;

return new class extends Migration
{
    /**
     * No automatic administrator provisioning.
     *
     * A known default credential (admin@example.com / password) previously
     * granted access to every admin review, user, job, and audit route on fresh
     * installs. First-admin creation is an explicit one-time operator action via
     * `php artisan admin:create {email}` — never a fixed, committed credential,
     * and never an environment secret read inside a migration (migrations must
     * be deterministic and safe to replay).
     *
     * This migration is intentionally a no-op. Accounts that already exist from
     * prior provisioning are NOT deleted here; deployment remediation for those
     * is covered by the runbook (inventory → rotate/disable uncertain accounts
     * → verify only the operator-authorized admin can log in).
     */
    public function up(): void
    {
        // Intentionally left in place (no-op). See class docblock.
    }

    public function down(): void
    {
        // Intentionally left in place.
    }
};