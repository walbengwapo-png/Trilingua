# Phase 2 — Timeout ladder & recoverable admin retry (R2 + R3)

Date: 2026-09-28 · Branch: `walben`

## Before-state
- Timeout values disagreed: `config/queue.php` default `retry_after=900`; `.env.example` and `.env` echoed 900/1500 inconsistently; `TranslateDocumentJob::$timeout=1300`; Python HTTP ~1200; launch scripts used `queue:listen --timeout=1500`; `ReconcileTranslations` defaulted `--processing-timeout=900`. A 900s lease could make an active job visible to a second worker or let the reconciler fail a healthy row while the original worker still ran (duplicate provider work / competing writes / false-failure polling).
- State transitions in `TranslationJob` were unconditional `save()`-style writes: a late worker or reconciler could overwrite an already-terminal row.
- `TranslateDocumentJob` deleted `$tempPath` on terminal failure, then `Admin/JobController::retry` replayed the *serialized `failed_jobs.payload`*, whose temp file was gone — an admin Retry that "succeeded" then failed identically.

## Changed files
- `config/timeouts.php` — **new** single source of truth, ordered ladder: `python_service 1200 < job 1300 < worker 1500 < retry_after 1800 < reconcile_processing 2100`, `check_stale` advisory 2100.
- `config/queue.php` — `retry_after` default 900 → 1800.
- `.env.example` — `DB_QUEUE_RETRY_AFTER=1800`; added `TRANSLATION_JOB_TIMEOUT=1300`, `QUEUE_WORKER_TIMEOUT=1500`, `RECONCILE_PROCESSING_TIMEOUT=2100`, `QUEUE_CHECK_STALE_THRESHOLD=2100`.
- `.env` — `DB_QUEUE_RETRY_AFTER` 1500 → 1800 (contains real secrets; never logged).
- `app/Console/Commands/ValidateDeploymentTimeouts.php` — **new** `deployment:validate-timeouts`: prints the ladder table and fails (exit 1) on any pairwise violation, so an override cannot silently restore an unsafe ordering.
- `app/Console/Commands/ReconcileTranslations.php` — default `--processing-timeout=2100`; **live-worker evidence gate** `hasLiveWorkerEvidence()`: searches `jobs.payload` for the job uuid (string `LIKE`, no `unserialize`) AND requires a fresh `reserved_at` within `retry_after` before failing a processing row.
- `bootstrap/app.php` — scheduler passes explicit `--processing-timeout=`/`--threshold=` from `config('timeouts.*')`.
- `start-all.bat`, `start-demo.ps1` — added `deployment:validate-timeouts` preflight before workers start.
- `app/Models/TranslationJob.php` — rewritten MTM-safe monotonic transitions: `markQueued(recovered:false)`, `markProcessing`, `noteProgress`, `markCompleted`, `markTerminallyFailed($e,$recoverable)`, `reconcileMarkFailed($reason)` — every write conditional on `whereIn(status, ACTIVE_STATUSES)` at the DB layer; `markQueued(recovered:true)` may revive a failed row only; `isTerminal()`, `isTerminalFailedRecoverable()`; casts for `recoverable`/`terminal_failed_at`.
- `database/migrations/2026_09_28_000001_add_recoverability_to_translation_jobs_table.php` — **new**: nullable `recoverable` boolean, nullable `terminal_failed_at` timestamp.
- `app/Jobs/TranslateDocumentJob.php` — `$timeout` from `config('timeouts.job')`; `presetUuid` ctor param (wins in `uuid()`); `resolveInputPath()` reconstructs the worker-local input from `StorageService::read(backend, original_storage_path)` when scratch is missing, throws unrecoverable when neither exists; `isRecoverable()`; `backfillOriginalStorage()` now persists `original_storage_path`/`original_storage_backend` back onto the state row; terminal path calls `markTerminallyFailed($e, $this->isRecoverable())`.
- `app/Http/Controllers/Admin/JobController.php` — `index()` enriches failed rows with `recoverable` via uuid join (no payload unserialize); `retry()` matches `failed_jobs.uuid` → `translation_jobs.uuid`, requires `isTerminalFailedRecoverable()`, re-dispatches `TranslateDocumentJob` with `presetUuid` + same `translationJobId` *only after* `markQueued(recovered:true)` succeeds, deletes the `failed_jobs` row; flashes `queue-job-retried` / `queue-job-not-recoverable` / `queue-job-retry-failed`.
- `resources/views/admin/jobs.blade.php` — flash banners; Recoverable/Unavailable badge column; Retry button rendered only for recoverable rows. `resources/css/views/admin.css` — `.notice--success`/`.notice--error`.

## New tests (21 cases, +66 assertions)
- `tests/Unit/TranslationJobStateTransitionTest.php` — monotonicity: completed rows immune to late `markCompleted`/`markTerminallyFailed`/recovery `markQueued`; `markQueued` requires an explicit recovery for failed rows; `markProcessing` ignores terminal rows; `reconcileMarkFailed` never clobbers completed rows and records `recoverable` from the durable original.
- `tests/Unit/ValidateDeploymentTimeoutsTest.php` — default ladder passes; `retry_after < worker` and `reconcile < retry_after` overrides exit 1 naming the offending key.
- `tests/Feature/AdminTranslationReconciliationTest.php` — a processing job with a **fresh** `jobs.reserved_at` is left processing; a lapsed reservation + stale heartbeat is failed (with `terminal_failed_at`); no queue row = no live-worker evidence → failed.
- `tests/Feature/Admin/AdminJobRetryTest.php` — recoverable replay pushes a `TranslateDocumentJob` with the same uuid/preset/durable original, clears `failed_jobs`, returns row to queued; unrecoverable and unmatched rows refused with nothing pushed; non-admin 403; index renders both badges.
- `tests/Unit/TranslateDocumentJobRecoveryTest.php` — missing scratch reconstructed from Supabase original; same for a local-backend original; missing-scratch-plus-no-durable terminates as failed with `recoverable=false` and "cannot be replayed".

## Focused checks (all run/verified)
1. `php artisan test --filter="TranslateDocumentJobTest|TranslationReconciliationScheduleTest"` → 4 passed (schedule string still matches).
2. `deployment:validate-timeouts` against real `.env`/config → ladder printed, "Timeout ladder is safe", exit 0.
3. New Phase 2 tests → 21 passed.
4. `php artisan test` → **319 passed, 1 skipped (1233 assertions)**. Prior phase was 298/1 (1167) → +21 cases, +66 assertions.

## Key decisions & notes
- Evidence gate chosen over mid-call heartbeat: a blocking Python HTTP call cannot safely emit heartbeats, so the reconciler consults queue-lease evidence (`jobs.payload` uuid string + fresh `reserved_at`) before transitioning processing rows, and only fails rows once their lease has lapsed past `retry_after` with a stale heartbeat.
- Retry is keyed on the shared uuid and the durable original — never on `unserialize(failed_jobs.payload)`. `markQueued(recovered:true)` is DB-conditional (failed only) and runs *before* dispatch, so a double-clicked retry cannot dispatch twice.
- `job $timeout` (1300) default is now read from config in the constructor (was a hard-coded property default); `quiescent` gap-analysis retained: no isolated change on this stack.
- `noteError()` kept as a compat no-op-style helper; terminal code paths use `markTerminallyFailed`.
- `.env` remains tracked in-repo and holds live secrets; this phase only changed one timeout value there. No credentials are echoed.

## Remaining risk
- Two-worker real-duration crossing test from the R2 spec (item 5) is not run; automated coverage relies on shortened clock/config. Staging check deferred to release.
- `StorageService::read` reconstruction is mocked in tests; the real Supabase `read` against the fallback persistent backend is verified only by the existing storage suite.