# 0C — Secret Rotation Runbook

**Purpose:** Rotate all credentials implicated by the audit AFTER 0A evidence is captured and
0B containment is applied. Requires explicit approval per secret (sign-off) and a rollback plan
for each.

**General rules**
- Do NOT rotate more than one secret without re-running the application verification.
- All secrets rotated here will be written to a NEW `.env`; the old `.env` stays in the
  encrypted 0A evidence location (never in git).
- APP_KEY rotation is LAST because it invalidates every existing session cookie and any
  encrypted values.
- SESSION_DRIVER=file: sessions are cookie-backed/signed by APP_KEY; rotating APP_KEY logs
  everyone out — coordinate this with intended downtime.

---

## Pre-rotation checklist

- [ ] 0A evidence captured + checksummed + stored externally
- [ ] 0B containment applied (no public exposure)
- [ ] Recovery plan documented in `security/evidence/manifest.md` (how to restore from PITR/backup)
- [ ] Each secret's current value is in the evidence package (so it can be audited after rotation)
- [ ] Approval (this runbook reviewed + sign-off)

---

## Order of operations

### 1. Supabase project secrets

Regenerating a project's keys invalidates old JWTs immediately.

1. Dashboard → Project Settings → API Keys.
2. Regenerate the **service_role** key. Record the new value.
3. Regenerate the **anon** key. Record the new value.
4. Update `.env`: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET`.

Rollback: old keys stop working the moment the project regenerates them — there is NO rollback.
Plan a maintenance window.

Verify:
```powershell
php artisan tinker --execute="app('App\Services\StorageService')->generateSignedUrl('<some existing storage path>')"
```
Expect a working signed URL (200) rather than 400/403.

### 2. Database password (pooler)

1. Supabase → Project Settings → Database → Connection strings → Reset database password.
2. Update `.env`: `DB_PASSWORD`, keep `DB_HOST`/`DB_PORT`/`DB_DATABASE`/`DB_USERNAME` as-is.
3. Clear config cache and re-test connectivity.

Rollback: restore the previous `DB_PASSWORD` in `.env`; the old password remains valid until
the next reset in Supabase. (Supabase keeps the previous password briefly.)

Verify:
```powershell
php artisan config:clear
php artisan migrate:status   # connects; expect a healthy list, no credentials error
```

### 3. MISTRAL_API_KEY

Rotate in the Mistral console; update `.env`; restart the Python service.

Verify: run a small translation successfully (text mode against Python endpoint).

### 4. GOOGLE_CLIENT_SECRET

Rotate in Google Cloud Console (OAuth credential); update `.env`; re-test `/auth/google` flows.

Verify: OAuth redirect succeeds and callback exchanges the code without `invalid_grant`.

### 5. APP_KEY (LAST)

Rotating APP_KEY invalidates all session cookies, remember-me hashes are separate but
remember_token values in DB still work, and any `Crypt::encrypt*` values (none currently —
verify) become unreadable. All users will be logged out — expected.

```powershell
cd trilingua-code
# Get a fresh key
$newKey = php -r "echo 'base64:'.base64_encode(random_bytes(32)), PHP_EOL;"
# Write it into .env manually (replace APP_KEY=...),
# then clear caches so nothing holds the old key
php artisan config:clear
php artisan cache:clear
php artisan session:clear
```

Verify: `php artisan tinker --execute="echo env('APP_KEY') ? 'ok' : 'missing';"` and a fresh
login works end to end.

Rollback: restore prior APP_KEY (users logged back in with old cookies that are still valid).

---

## Post-rotation

- [ ] Old values destroyed (do not paste old secrets into git/history — leave them only in the
  encrypted evidence store)
- [ ] All live secrets are only in the local, ignored `.env`
- [ ] `.env.testing` APP_KEY regenerated independently (never reuse production)
- [ ] Re-run the full test suite (guard now in place — see step 2)
- [ ] Note any users' active sessions lost, in the incident log