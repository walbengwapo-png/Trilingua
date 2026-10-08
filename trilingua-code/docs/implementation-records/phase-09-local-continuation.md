# Phase 09 — Local continuation without a new Supabase project

**Date:** 2026-09-29  
**Scope:** Finish the interrupted local corrections, then advance independent release work. The existing Supabase project and its data were not changed. No new project, bucket, or database was created.

## Corrections and evidence

| Area | Change | Reason |
| --- | --- | --- |
| Completed downloads | Inject `CompletedDownloadResolver` into `TranslationController` and use it for re-translation reuse in `DocumentsController`; remove the separate URL fallback there. | The resolver was called through an undeclared property, making completed dedup return HTTP 500. Reuse could also promise a link for a missing file. |
| Queue reconciliation | Check for a fresh queue reservation before failing a stale `created`/`queued` row. | A worker can reserve an old queued job just before marking it processing; the reconciler must not fail it in that window. A focused test failed before this fix and passed after it. |
| Storage presence | Use Supabase's object-info endpoint and treat only a structured `NoSuchKey` response as confirmed missing. | The previous HEAD request let Guzzle turn 404 into an exception, and a bare 404 cannot distinguish a missing key from a missing bucket. Other errors remain uncertain. See [Supabase Storage error codes](https://supabase.com/docs/guides/storage/debugging/error-codes). |
| Python service token | Load only the exact `PYTHON_SERVICE_TOKEN` and `APP_ENV` keys from the shared environment. Accept the legacy name only for local runs. | Broad `APP_` loading pulled Laravel's `APP_KEY` into the Python process and broke the deterministic suite; a legacy-only production configuration would otherwise start while Laravel used a different key. |
| Direct Ollama Cloud | Attach `OLLAMA_API_KEY` as a Bearer token only for `https://ollama.com`; fail early if direct cloud access lacks a key. Keep local Ollama unauthenticated. | The selected direct-cloud route had no authentication. This follows [Ollama's API authentication documentation](https://github.com/ollama/ollama/blob/main/docs/api/authentication.mdx). No live provider call was made. |
| Guest copy | Remove the NLLB-200 and “instantly” claims. | The configured primary provider is GPT-OSS, and documents may take minutes. |

Focused tests cover missing downloads, a fresh lease on a stale waiting job, idempotent legacy history backfill, structured Supabase presence errors, direct-cloud headers, and production token policy.

## Checks

- `php tests/assert-safe-test-env.php`: passed; tests use SQLite `:memory:`.
- `php artisan test --compact`: **471 passed, 1787 assertions**.
- `php artisan deployment:validate-timeouts`: passed.
- `npm run build`: passed; Vite reports large preview dependency chunks, requiring measurement before any optimization decision.
- Python deterministic suite: **371 passed, 35 deselected**.

## Release boundary

No local PostgreSQL server, `psql`, `pg_dump`, or Docker runtime was found on this host. The hosted Supabase database was not migrated. The earlier read-only inventory recorded seven pending migrations; a restore and migration dry run on an isolated PostgreSQL database remain required. A separate **staging** bucket is needed for real storage checks, but a new Supabase **production** project is not.

PostgreSQL queue races, live Supabase Storage responses, provider translation, 50 MB uploads, browser flows, all 54 format-direction cells, human meaning/layout review, credential rotation, and deployment remain unverified. No production-ready or pilot-ready claim follows from these local checks.
