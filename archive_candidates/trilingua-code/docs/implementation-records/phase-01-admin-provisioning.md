# Phase 1 — Admin provisioning (R1)

Date: 2026-09-28 · Branch: `walben`

## Before-state
- `2026_09_06_000003_seed_default_admin_user` inserted an admin template with a hard-coded default credential; if a matching user did not yet exist at seed time, it became a live `admin@example.com` / `password` account (`is_admin` = true).
- `DatabaseSeeder::run()` called that migration-style provisioning path unconditionally, so any `db:seed` could mint the known admin.
- The environment has an existing compromise history around `admin@example.com` (see `security/containment-runbook.md`, `security/evidence-runbook.md`); those records are outside this phase's scope and unmodified.

## Changed files
- `database/migrations/2026_09_06_000003_seed_default_admin_user.php` — rewritten as a deterministic no-op. No fixed credentials and no environment secrets are ever written by migrations.
- `database/seeders/DatabaseSeeder.php` — rewritten: seeds only `test@example.com`; never creates or mints an admin account.
- `app/Console/Commands/CreateAdminUser.php` — **new**: `admin:create {email} [--password=] [--force]`.
  - Rejects invalid emails.
  - Refuses to re-run when the user is already admin unless `--force`.
  - Password policy (minimum 12 chars, not `password`, not containing the email local-part); interactive `--password` prompt when omitted; the provided password is never echoed.
  - `is_admin` is written as `DB::raw('true')` — the same pattern the old migration used — because this stack's PDO binds PHP booleans as integers on Postgres (`SQLSTATE[42804] Datatype mismatch: column "is_admin" is of type boolean but expression is of type integer`). Tested green on sqlite.
- `tests/Feature/Admin/AdminProvisioningTest.php` — **new**, 4 tests, 17 assertions.

## Focused checks (all run/verified)
1. `php artisan test --filter=AdminProvisioningTest` → **4 passed (17 assertions)**.
2. `php artisan test` → **298 passed, 1 skipped** (1167 assertions). Baseline was 294/1; +4 from the new test.
3. Manual scratch run against a throwaway file-based sqlite (env-guarded, NOT the real app `.env`):
   - `admin:create operator@example.com --password=X9!kTq-bVn2$mzR4` → SUCCESS, `is_admin = true` in stored row.
   - `admin:create badadmin@example.com --password=password` → FAILURE (exit 1), no row created.

## Key decisions & notes
- No `admin:inventory` command: runbook provides a read-only inventory query (no hash/password columns exposed).
- The fresh-install tripwire is kept genuine: the test boots a **separate** `:memory:` connection, runs the real migration batch + seeder there, and asserts the known credential cannot authenticate and no `admin@example.com` row exists.
  - `migrate:fresh` and `Schema::dropAllTables()` cannot run on `:memory:` inside `RefreshDatabase` (sqlite `VACUUM` inside a transaction is rejected: `cannot VACUUM from within a transaction`); the dedicated connection avoids the trap entirely.
- Seed can never reset an existing administrator's password: covered by `test_seeding_cannot_turn_an_existing_account_into_a_known_password_admin` (existing admin keeps its distinct password; the known default still fails `Hash::check`).
- CLI is the only admin-provisioning path, and its exit code is asserted with `assertSuccessful()`/`assertFailed()` (these gave `status 0` in an earlier draft because a bogus strong password contained the email local-part and was *correctly* rejected — the assertion was checking the wrong password, not the command).

## Remaining risk
- `admin:create` was exercised against sqlite only; the Postgres boolean fix follows the proven `DB::raw('true')` pattern from the historical migration but is not yet verified against a live Postgres/Supabase connection. It must never be run against the real database outside a guarded, deliberate operation.