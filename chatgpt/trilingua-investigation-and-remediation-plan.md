# Trilingua Investigation and Remediation Plan

**Date:** 2026-09-07  
**Scope:** Investigation and planning only. No application source or configuration changes were made as part of this audit.

## Executive conclusion

Trilingua has a strong prototype-level feature set: multilingual text and document translation, asynchronous processing, history, notifications, user settings, and an administrator review workflow with block-level editing and metrics. The Python translation pipeline and its test coverage are particularly promising.

It is **not safe to deploy to production yet**. The highest-risk blockers are exposed Supabase access, committed credentials, a predictable default administrator account, unsafe test-environment isolation, and document-job durability defects.

## Immediate incident: possible production database reset

During the audit, the repository's documented PHP test command was run. Although `.env.testing` and `phpunit.xml` specify an in-memory SQLite database, Laravel's cached configuration caused the test process to connect to the real Supabase PostgreSQL database.

Laravel feature tests use `RefreshDatabase`, which may execute destructive migration-reset operations. A read-only inspection immediately afterward showed one user and zero records in translation history, blocks, edit logs, metrics, notifications, activity logs, queued jobs, and failed jobs.

This does **not** prove data loss because no baseline count was available. Treat it as a production incident until Supabase Point-in-Time Recovery (PITR), backups, and API/database logs establish otherwise.

### Immediate containment

1. Pause public access and avoid further database writes until the incident is assessed.
2. Check Supabase backups/PITR for 2026-09-07 and compare restored data to the current database.
3. Review database/API logs for migrations, destructive SQL, and suspicious access.
4. Add a test bootstrap guard that aborts unless `APP_ENV=testing`, SQLite, and `:memory:` are all active.
5. Explicitly reject the known production database host during tests.

## Current functional flow

```text
Guest
  -> login / registration / Google OAuth / password reset
  -> dashboard
  -> text translation (synchronous result)
     OR document translation (queued job)
  -> history / notifications / file download
  -> bookmark, prioritize, rename, retranslate, delete

Administrator
  -> dashboard and queue
  -> text/document review
  -> block-level edit or regeneration
  -> users, audit log, metrics, CSV exports
```

This overall flow is sensible. The main user-flow issues are unreliable long-running job status, inconsistent upload capabilities between UI and server, weak recovery when storage fails, and insufficient privacy communication/controls.

## Critical security findings

| Priority | Finding | Risk | Required remediation |
|---|---|---|---|
| P0 | Supabase public tables have RLS disabled and permissive `anon`/`authenticated` grants. | Anyone with the anon key can potentially bypass Laravel authorization and read, modify, or delete application data. | Disable the Data API if it is not needed. Otherwise revoke broad grants, enable RLS, and create narrow ownership policies. |
| P0 | The `trailingua` object-storage bucket is public with no size or MIME restrictions. | Sensitive document retrieval can bypass Laravel ownership checks. | Make the bucket private, use short-lived signed URLs, set allowed MIME types and limits, and enforce storage policies. |
| P0 | Active-looking Supabase, Mistral, and other credentials are tracked in Git history. | Database/API/provider compromise; past commits remain accessible after ordinary deletion. | Rotate all credentials, invalidate sessions, scrub history with `git filter-repo`, force-push in coordination with collaborators, and add secret scanning. |
| P0 | A migration creates `admin@example.com` with password `password`. | Immediate administrative-account takeover if deployed. | Disable/delete the account now; remove seeded production credentials; bootstrap first admin through a one-time secret/CLI flow; require MFA. |
| P0 | PHP tests can use production configuration. | Tests can mutate or reset live data. | Add hard environment assertions, clear config cache before tests, and use disposable CI databases only. |
| P1 | CSP permits `unsafe-inline` and `unsafe-eval`. | Weakens XSS protection. | Bundle scripts, use nonces where needed, remove unsafe directives after report-only rollout. |
| P1 | All proxies are trusted. | Spoofed forwarded IP/protocol headers can compromise rate limits and audit accuracy if the origin is reachable. | Trust only known proxy ranges and firewall the origin. |
| P1 | Python translation service endpoints lack service authentication. | Cache control, provider discovery, or translation endpoints may be exposed if network boundaries change. | Require an internal service credential/private network, add rate limits, and disable development reload in production. |
| P1 | Upload checks rely mainly on extension/MIME metadata. | Malware, archive bombs, memory exhaustion, and cost abuse. | Add content sniffing, malware quarantine/scanning, archive/page/cell limits, and per-user quotas. |
| P1 | Source/translation content may be logged or retained in plaintext cache files. | Privacy exposure for sensitive documents. | Minimize logs, cache hashes rather than raw text when possible, encrypt/expire sensitive caches, and stop tracking runtime artifacts. |

## Functional correctness findings

| Priority | Finding | User impact | Required remediation |
|---|---|---|---|
| P0 | Document job deduplication cache key is overwritten with boolean `true`, although the controller expects a job ID. | A duplicate submission can receive `job_id: true` and poll an invalid job. | Persist a canonical job record before dispatch; never change the cache value type; return the canonical existing job ID. |
| P0 | Deduplication excludes document hash and output-affecting options. | Different documents/options can incorrectly share a job. | Use SHA-256 of file content plus language pair, mode, and document options under a unique database constraint. |
| P0 | Storage failure fallback keeps completed output only in one-hour cache, then removes the temporary file. | A completed translation can become permanently unavailable after cache expiry. | Persist a durable private fallback, retry remote storage, and mark jobs complete only once output is durable. |
| P1 | UI limits conflict with backend capabilities: 5,000 vs 8,000 text chars; 10 MB vs 50 MB; UI excludes supported PPTX/XLSX. | Users are blocked from supported capabilities and receive contradictory behavior. | Define one server-owned capability contract serialized to the frontend; add contract tests. |
| P1 | Browser polling ends around six minutes while translation may take ten minutes. | User sees timeout while a job may later finish. | Build durable server-side job state and a persistent job center with backoff, reconnect, resume, and status history. |
| P1 | Translate control is re-enabled immediately after enqueue; multiple jobs overwrite shared UI state. | Confusing concurrent-job behavior and lost status context. | Keep an active job lock or provide a proper multi-job queue with individual cards/status. |
| P1 | Retranslation file-size fallback is defeated by type-cast precedence. | Old records without size can behave as zero-byte uploads. | Cast after applying fallback and add regression coverage. |
| P1 | User filenames reach paths, storage keys, headers, and `innerHTML`. | Potential DOM/header/path handling vulnerabilities. | Use generated opaque object keys, sanitize display names, use DOM `textContent`, and generate safe download headers. |
| P1 | History record deletion occurs before remote object cleanup. | Storage failures orphan sensitive files. | Use tombstone/outbox deletion, retry workers, and periodic orphan reconciliation. |
| P2 | Toggle/notification routes return success for error paths. | API clients cannot reliably distinguish forbidden/missing/invalid actions. | Return correct 403/404/422 status codes and define idempotent behavior. |
| P2 | Authenticated users can revisit auth pages; name/password validation is inconsistent and overly restrictive. | Confusing navigation and exclusion of legitimate names. | Apply guest middleware, redirect signed-in users, use Unicode-friendly names, and centralize password policy. |

## Performance and operational reliability

### Document processing

Large documents are repeatedly read into memory and returned as base64 JSON. A 50 MB file is read by Laravel and Python, expanded by base64, decoded again by PHP, then read again for storage. At concurrent load this can exhaust worker memory.

Plan:

1. Stream original and translated artifacts through private object storage.
2. Pass object references to workers instead of document bytes in JSON.
3. Return job metadata rather than base64 output payloads.
4. Set format-specific size/complexity limits.
5. Measure memory/latency and configure queue concurrency accordingly.

### Database and query efficiency

History and dashboard views load broad datasets and perform some filtering/aggregation in PHP. Translation counts are queried in a loop, creating N+1 behavior. Admin filter fields need targeted indexes.

Plan:

1. Paginate and aggregate in SQL.
2. Use `withCount`, selected columns, and indexed database aggregates.
3. Add composite indexes only after validating real query plans with `EXPLAIN ANALYZE`.
4. Cache only non-sensitive aggregate dashboard data.

### Queue reliability

The document job lacks a clear retry, timeout, backoff, heartbeat, and dead-letter policy. Some exceptions are transformed into status results, which can bypass Laravel failed-job visibility.

Plan:

1. Set explicit attempts, timeout, backoff, and retry classification.
2. Record job heartbeats and progress.
3. Maintain failed-job/dead-letter visibility and administrator retry controls.
4. Add stale-job reconciliation on a schedule.
5. Alert on queue age, provider errors, storage failures, and translation latency.

## Accessibility and ease of use

The application has a reasonable responsive layout and some ARIA/live-region support. It still needs a formal accessibility pass.

Red flags:

- No skip-to-content link.
- Some simulated buttons use `div role="button"` instead of native controls.
- Dropdown/modal focus management is incomplete.
- Some administrative inputs rely on placeholders rather than permanent labels.
- Reduced-motion support is inconsistent.
- Long-running job status is fragile and errors during polling are not actionable.
- There is no public landing/privacy page that explains data handling or provider use.

Plan:

1. Use native controls and semantic labels.
2. Add skip navigation, visible focus, focus trap/return, and reduced-motion support.
3. Test against WCAG 2.2 AA with axe, keyboard-only flows, contrast checks, and screen-reader smoke tests.
4. Add a public landing page describing supported formats/languages, privacy, retention, and third-party translation processing.
5. Build a durable job center with cancel/retry/resume actions.

## Missing features and why they matter

| Feature | Justification |
|---|---|
| Privacy center | Users need retention details, third-party AI disclosure, data export, account deletion, and explicit document deletion for potentially sensitive files. |
| Persistent job center | Document translation is long-running and cannot depend on one browser polling session. |
| Cancel/retry/resume | Provider, network, and storage failures are normal for asynchronous document processing. |
| Email verification, admin MFA, session/device management | Administrators can access all user translations; password-only access is insufficient. |
| Role-based administration | A single boolean admin role combines reviewer, support, and operational authority. |
| User glossary/terminology | Backend terminology capability exists, but users cannot ensure consistent domain-specific translations. |
| Translation feedback/correction | User quality reports should feed the existing review and metrics workflows. |
| Source-language detection | Confidence-based detection with manual override reduces wrong-direction translations. |
| Backup/PITR and restore drills | The discovered test-isolation incident demonstrates the need for proven recovery procedures. |
| CI/CD release gates | Tests, dependency audits, secret scanning, migrations, E2E flows, accessibility, and performance checks should block unsafe releases. |

## Dependency and test health

- Composer audit: 37 advisories across 11 packages, including 12 high-severity findings.
- Production npm audit: high-severity SheetJS `xlsx` issues and a moderate `@xmldom/xmldom` issue.
- Full npm tree: 11 issues, including 2 critical and 7 high.
- Python tests: 277 passed, 2 skipped.
- PHP tests: 147 passed, 129 failed, 1 skipped.

The PHP failures are not all confirmed product defects. Many are caused by the production-configuration leak, database type differences, and stale tests. Confirmed test drift includes tests using an outdated job `handle()` signature, expecting a removed session method, and mocking an obsolete translation service abstraction.

## Delivery roadmap

### Phase 0 — containment (today)

1. Investigate and, if needed, restore Supabase data.
2. Pause public exposure.
3. Rotate exposed credentials and invalidate sessions.
4. Remove default-admin access.
5. Disable/restrict Supabase API access and make storage private.
6. Preserve logs and inventory leaked secrets.
7. Add hard database test guards.

### Phase 1 — production blockers (next 1–3 days)

1. Scrub credentials and generated data from Git history.
2. Repair job identity, deduplication, durable output storage, and recovery.
3. Harden filenames, downloads, uploads, proxy trust, CSP, cookies, and Python service access.
4. Establish retries, failure visibility, and stale-job recovery.
5. Upgrade vulnerable dependencies.
6. Create isolated CI/test infrastructure and repair stale PHP tests.

### Phase 2 — reliability and user workflow (one sprint)

1. Deliver persistent job center, progress, retry, cancellation, and resume.
2. Unify frontend/backend capabilities.
3. Implement privacy controls, retention, export, and deletion.
4. Optimize database queries and indexing.
5. Complete WCAG remediation and browser end-to-end coverage.

### Phase 3 — product maturity

1. Add glossary, feedback/correction, and language detection.
2. Add MFA and role-based administrative permissions.
3. Add operational dashboards, SLOs, load tests, failure injection, and restore drills.
4. Remove obsolete services and split oversized pipeline modules.

## Final readiness assessment

| Area | Assessment |
|---|---|
| Functional breadth | Strong prototype |
| Translation pipeline | Promising |
| Security | Critical deployment blocker |
| Data durability | High risk |
| Performance | Acceptable for light text use; unsafe for concurrent large documents |
| Usability | Good foundation; unreliable long-job experience |
| Accessibility | Partial foundation; formal compliance work required |
| Maintainability | Mixed; strong Python tests but weak PHP test trust and repository hygiene |
| Production readiness | Not ready until Phase 0 and Phase 1 are complete |

## Reference points in the repository

- `trilingua-code/app/Http/Controllers/TranslationController.php`
- `trilingua-code/app/Jobs/TranslateDocumentJob.php`
- `trilingua-code/app/Http/Controllers/HistoryController.php`
- `trilingua-code/app/Http/Controllers/DocumentsController.php`
- `trilingua-code/app/Http/Middleware/SecurityHeaders.php`
- `trilingua-code/bootstrap/app.php`
- `trilingua-code/database/migrations/2026_09_06_000003_seed_default_admin_user.php`
- `trilingua-code/phpunit.xml`
- `trilingua-code/Model/server.py`
