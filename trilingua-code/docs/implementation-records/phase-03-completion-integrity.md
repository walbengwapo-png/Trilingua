# Phase 3 — Completion integrity (R4)

Date: 2026-09-28 · Branch: `walben`

## Before-state
- `TranslateDocumentJob` caught history-insert and block/metric persistence failures as **non-fatal** (`Log::error` + continue), then called `markCompleted(..., $history?->id)` with a null history id. A completed state could therefore exist with no owner-visible history row.
- `TranslationController::status` returned **`processing`** ("still in progress") for a job whose `translation_history_id` was blank or unresolvable — a completed job could poll forever instead of surfacing a terminal error.
- `buildHistoryCompletedPayload` returned `null` on signed-URL generation failure; branch 2 then fell through to an unguarded `/history/{id}/file` fallback regardless of `storage_path`, and a blank-storage path returned `completed` pointing at a route that 404s.
- A `queue:retry`/admin retry after a partial history failure would re-upload a second translated object and insert a second history row.

## Changed files
- `database/migrations/2026_09_28_000002_add_translated_paths_to_translation_jobs_table.php` — **new**: `translated_storage_path`, `translated_storage_backend` on `translation_jobs`. Object storage cannot join a DB transaction, so the durable key is recorded on the state row immediately after upload, giving a retry an idempotent resume handle and a cleanup path for a stranded object.
- `app/Jobs/TranslateDocumentJob.php`:
  - Completion invariant: history row + review blocks are now **required**. History insert must return a non-null row; a block-persistence failure deletes the freshly inserted history (compensating write) and the job fails **terminally, recoverable**, never completed. Metrics persistence stays explicitly non-fatal (user can still retrieve the file).
  - `durableTranslatedUpload()`: a retry whose state row already records a translated object **reuses it** (no second upload).
  - Resume not-insert: an existing user-scoped history row keyed by the job UUID is reused instead of creating a second row.
  - `persistRequiredBlocks()` replaces the old swallow-errors `persistDocumentBlocks()`.
- `app/Http/Controllers/TranslationController.php`:
  - `status()`: a completed-but-unresolvable job now returns **`failed`** with `recoverable` (never `processing`); failed jobs carry `recoverable`; history-only rows with blank `storage_path` return **`failed`** instead of a broken `completed` download.
  - `buildHistoryCompletedPayload()`: signed-URL failure **falls back to the authenticated `history.file` route** (owner-authorized streaming via `StorageService::read`, works for every backend) and no longer returns null for a resolvable record.

## New tests (13 cases)
- `tests/Unit/TranslateDocumentJobHistoryIntegrityTest.php` — history-insert failure → terminal/recoverable, object path recorded, no completed, no history row; block-persistence failure → same + history insert compensated (0 rows); retry resumes the recorded object **and** the existing history row (no second object upload, no second history row).
- `tests/Feature/TranslationStatusTerminalStatesTest.php` — completed-without-history → `failed` (not processing) + `recoverable:true`; signed-URL failure → `completed` via `/history/{id}/file`; local backend → same route; failed job reports `recoverable`; history-only row with blank storage → `failed`.
- Updated `TranslateDocumentJobTest`/`TranslateDocumentJobRecoveryTest`: completion tests now exercise the real history insert (fixture seeds the owning user) and required-block path.

## Focused checks (all run/verified)
1. `php artisan test` → **327 passed, 1 skipped (1271 assertions)**. Prior phase was 319/1 (1233) → +8 cases, +38 assertions.
2. `php -l` clean on the job, controller, and new migration.

## Key decisions & notes
- The implementation uses a **driver-agnostic compensating delete** instead of a wrapping `DB::transaction` for the history+blocks sequence. On this stack SQLite has no savepoints (`Grammar::supportsSavepoints()` false), so a *throwing* nested `DB::transaction` poisons the connection and cascades failures into every later test in the process ("There is already an active transaction"); on Postgres `BlockService::persistBlocks` already runs its own real transaction. Net effect (history insert is removed if blocks cannot persist) is identical on every driver; documented in the record.
- Fixture lesson: `translation_history` has a real FK to `users`, so job tests that create history rows must seed the owning user (unit mocks used to return `null` and never exercised the insert).
- No DB-level unique index added on `translation_history.job_id`: dispatch of one active job per payload is already enforced by the R2 partial unique index on `translation_jobs`, the worker is single-threaded per job, and `find-first-then-insert` covers a retried run; an index against live prod data could fail on historical duplicates.
- Notifications/metrics remain non-fatal by design (plan item 5); history + blocks are the completion boundary.

## Remaining risk
- The compensating-delete window (row exists for the instant between insert and a failing block write) is narrow but real; the row never reaches a UI while the job is still active, and a delete failure only leaves a stale-but-valid downloadable record.
- Real-`BlockService` failure under dual-worker concurrency is covered by mocks; staging still needs the R2 long-duration two-worker check before release.