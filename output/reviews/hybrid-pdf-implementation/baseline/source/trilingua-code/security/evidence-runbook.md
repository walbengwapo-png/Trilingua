# 0A — Evidence Preservation Runbook

**Purpose:** Capture a defensible baseline of Trilingua production data and logs BEFORE any
modification (disabling the admin, rotating keys, or fixing code). Verbatim output is evidence
in support of the 2026-09-07 possible-production-database-reset investigation.

**Guidance (redline):** Store ALL raw captured material in an **encrypted, external location
outside the git repository** (e.g., an encrypted local volume, VeraCrypt container, or a private
encrypted cloud vault). Never write raw logs or data dumps into the repository. Only the redacted
manifest in `security/evidence/manifest.md` (paths, SHA-256 checksums, descriptions) is committed.

**Windows hardening:** after each capture, compute `Get-FileHash -Algorithm SHA256`.

---

## 0. Verify environment

- Confirm you are connecting to the intended Supabase project (project ref in URL).
- Do NOT make any writes during this step. Every query below is read-only.

## 1. Database baseline (Supabase SQL Editor / psql with read-only role)

Run against the production database and save output to `db_baseline_YYYYMMDD_HHMMSS.sql`:

```sql
-- Incident investigation baseline: 2026-09-07
SELECT 'users'            AS tbl, count(*) FROM users
UNION ALL SELECT 'translation_history', count(*) FROM translation_history
UNION ALL SELECT 'translation_blocks', count(*) FROM translation_blocks
UNION ALL SELECT 'translation_edit_log', count(*) FROM translation_edit_log
UNION ALL SELECT 'translation_metrics', count(*) FROM translation_metrics
UNION ALL SELECT 'notifications', count(*) FROM notifications
UNION ALL SELECT 'user_activity_log', count(*) FROM user_activity_log
UNION ALL SELECT 'jobs', count(*) FROM jobs
UNION ALL SELECT 'failed_jobs', count(*) FROM failed_jobs
UNION ALL SELECT 'sessions', count(*) FROM sessions
ORDER BY tbl;

-- Default admin row (main investigate whether it was created/nuked)
SELECT id, email, is_admin, created_at, updated_at,
       (email_verified_at IS NOT NULL) AS verified
FROM users WHERE email = 'admin@example.com';

-- Max/most recent activity that would indicate a reset boundary
SELECT max(created_at) AS latest_history FROM translation_history;
SELECT max(created_at) AS latest_activity FROM user_activity_log;
SELECT max(id) AS max_user_id FROM users;
```

Run the pg_dump snapshot (read-only) and store it with the manifest entry:

```bash
pg_dump --no-owner --no-privileges -Fc -h <POOLER_HOST> -p 6543 -d postgres -U <USER> -f evidence/db_baseline_YYYYMMDD_HHMMSS.dump
```

## 2. Storage baseline (Supabase Storage)

List every object in the `trailingua` bucket (API or dashboard) so we know what must exist:

```bash
curl -s "https://<REF>.supabase.co/storage/v1/object/list/trailingua?limit=1000&offset=0" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY"
```

Save JSON and note object names + sizes. Repeat with `offset` increments until empty array.

## 3. Logs to export (Supabase dashboard)

Export, save, and checksum each:

- **API logs** — window 2026-09-07 (matching the incident), plus 24h before/after.
- **Database logs** — look for `migrate`, `DROP`, `TRUNCATE`, `DELETE`, `REFRESH`, and
  connections from unexpected IPs.
- **Auth logs** — sign-in attempts, password resets, admin@example.com usage.
- **Storage logs** — object create/delete events on `trailingua`.

## 4. Local process evidence

Before stopping anything, snapshot:

```bash
# Running listeners / processes (Windows)
netstat -ano | findstr ":8000 :5000"
tasklist /fo csv

# Any cloudflared tunnel process + its URL log
get-process -Name *cloudflared* -ErrorAction SilentlyContinue | select Id, Path
Get-Content storage/demo/*.log -ErrorAction SilentlyContinue
```

Save the git state at the exact capture time:

```bash
git -C C:\dev\Trilingua log --all --oneline --decorate -50
git -C C:\dev\Trilingua status
git -C C:\dev\Trilingua rev-parse HEAD
```

## 5. Finalize the manifest

Copy/move everything to the external encrypted location, then compute checksums:

```powershell
$files = Get-ChildItem <external-evidence-dir> -Recurse -File
$files | ForEach-Object { Get-FileHash $_.FullName -Algorithm SHA256 } | Export-Csv manifest-rows.csv
```

Create/update `security/evidence/manifest.md` in the repo using `manifest.template.md` — only
paths, sizes, SHA-256, and a one-line description per artifact. No raw data in the repo.

## 6. Decision inputs

Use this baseline to decide:

- If `users` shows the admin or other rows that now exist, and history/blocks/metrics/logs are
  empty → data loss is confirmed and `translation_history` etc. need PITR restore.
- Diff against current live counts (re-run section 1 later) to scope the blast radius.
- Preserve this evidence at least until the incident is formally closed.