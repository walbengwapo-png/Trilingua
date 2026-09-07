# 0B — Containment Runbook

**Purpose:** Immediately reduce exposure while evidence (0A) is still preserved. Each step is a
surgical, reversible change. Execute in the listed order and mark each box as done.

## Outline

1. Disable public exposure
2. Disable the Supabase Data API
3. Make the storage bucket private
4. Disable the default administrator (redline: rotate hash, never null)
5. Verification

---

## 1. Disable public exposure

Stop public network entry points so the app cannot be hit while remediation is in progress.

```powershell
# Stop Cloudflare named tunnel + revert .env (Managed/Props):
.\undeploy-named-tunnel.ps1

# Stop all local services (Laravel :8000, Python :5000, queue workers):
.\stop-demo.ps1
```

Manual checks:
- [ ] No `cloudflared` process remains (`get-process -Name *cloudflared*`)
- [ ] No listener on :8000 / :5000 (`netstat -ano | findstr ":8000 :5000"`)
- [ ] Any public DNS (e.g., Cloudflare `try.cloudflare.com` / named CNAME) removed or pointed away

> Note: `undeploy-named-tunnel.ps1` restores pre-deploy `.env` values from its backup file. If it
> fails halfway, do not re-run blindly — restore from the backup manually and then stop services.

## 2. Disable the Supabase Data API (PostgREST)

Laravel is the only client of the database, and nothing in the browser talks to PostgREST
(`connect-src 'self'` in CSP + `APP_URL`-relative API calls). Therefore the Data API should be
turned off entirely, which removes the `anon`/`authenticated` risk surface completely.

Manual steps (Supabase dashboard):
1. Project Settings → API → Data API.
2. Toggle the **Data API** (PostgREST) to **Off**/deprecated. (The PostgREST endpoint then
   returns 404 for `http://<ref>.supabase.co/rest/v1/*`.)
3. Confirm no RLS policies or broad grants are relied on for application auth afterwards —
   the app authenticates in Laravel and uses **service-role** signed URLs for storage only.

Why not "ownership policies"? Ownership policies are only safe with a real, verified mapping
between Supabase Auth identities and Laravel user IDs. That mapping does not exist here, so
disabling the Data API is the safer containment.

- [ ] Data API disabled
- [ ] `GET /rest/v1/<anything>` returns 404/403 (verify)

## 3. Make the storage bucket private

The `trailingua` bucket must reject public reads. All access must go through the service-role
key (Laravel `StorageService`) and short-lived signed URLs.

Manual steps (Supabase dashboard → Storage → Buckets → `trailingua` → Edit):
- Set **Public bucket** → **OFF**
- Under (Advanced) if available: allowed MIME types = the application allowlist
  (`application/msword`, `.docx` `application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
  `application/pdf`, `text/plain`, `text/markdown`, `text/rtf`,
  `application/vnd.oasis.opendocument.text`,
  `text/csv`, `application/vnd.ms-powerpoint`, `application/vnd.ms-excel`,
  `application/vnd.openxmlformats-officedocument.presentationml.presentation`,
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`)
- Max file size → 50 MB (51200 KB) to match server-side validation.

Verify an unauthenticated GET of `.../storage/v1/object/public/trailingua/<key>` returns 400/404.

- [ ] Bucket private
- [ ] Public object GET fails
- [ ] Signed URL GET still works (generate one via `php artisan tinker` + `StorageService::generateSignedUrl`)

## 4. Disable the default administrator (redline #1)

The seed account `admin@example.com` / `password` is a known compromise path. Do NOT null the
password column (schema originally requires `password NOT NULL`; instead the credential hash is
**rotated to a fresh random bcrypt hash**) and do NOT delete the row (evidence/audit).

### 4a. Generate a fresh random bcrypt hash (run locally, not in production)

```powershell
php -r "echo password_hash(bin2hex(random_bytes(32)), PASSWORD_BCRYPT), PHP_EOL;"
```

Save the generated hash into a password manager entry named
`REMEDIATION admin@example.com random hash (2026-09-07)`. You will NOT need to log in with it;
it simply makes the stored hash one you never control. Do not paste the generated hash into
chat/logs.

### 4b. Apply (Supabase SQL Editor — EXPLICIT transaction, then verify)

```sql
BEGIN;

-- Bump the hash to an unknown random value, demote, and invalidate remember-me tokens.
UPDATE users
SET is_admin        = false,
    password        = '<PASTE_GENERATED_HASH>',
    remember_token  = NULL,
    updated_at      = now()
WHERE email = 'admin@example.com';

-- Session invalidation: SESSION_DRIVER=file, so active sessions are not stored in this table;
-- they are invalidated by the APP_KEY rotation in 0C and remember-token nulling above.
-- If a DB session driver is ever enabled, also run:
-- DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE email='admin@example.com');

COMMIT;
```

### 4c. Verify (read-only)

```sql
SELECT id, email, is_admin, remember_token IS NULL AS remember_nulled,
       password <> '$2y$12$...NO_LONGER...' AS hash_rotated_below
FROM users WHERE email = 'admin@example.com';
```

Expected: `is_admin = false`, `remember_nulled = true`, and the stored hash does not match any
known plaintext.

- [ ] Admin demoted
- [ ] Hash rotated
- [ ] remember_token nulled
- [ ] No public access possible

> Until the deployment passes inspection, do NOT re-create any admin. Future admins are created
> via the secure `admin:create` bootstrap flow delivered with Phase 3 MFA work.

## 5. Verification sweep

- [ ] `http://<ref>.supabase.co/rest/v1/*` returns 404
- [ ] Public bucket GET returns 400/404
- [ ] Login page reachable only from localhost (no public tunnel)
- [ ] `SELECT count(*) FROM users WHERE is_admin = true` shows 0 admins (or only verified ones)