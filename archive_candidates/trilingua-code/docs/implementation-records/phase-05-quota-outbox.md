# Phase 05 — Quota atomicity (R6) + deletion integrity/outbox (R7)

**Status:** Complete
**Full suite:** 366 passed / 1 skipped (1506 assertions) — no regressions
**Correction-gate suite:** `UploadQuotaAtomicityTest` 12 passed, `HistoryDeletionOutboxTest` 7 passed,
`TranslationControllerTest|DocumentsControllerTest|TranslationJobDedupTest` 7 passed; full `php artisan test` green.
**Windows note:** on this host `UploadedFile->move()` holds the destination directory
until the request object is released. That lock leaves Windows "pending-delete"
phantom entries that `scandir()` lists even though the underlying file is gone
(`file_exists()`/`fopen()` already fail). The leak assertions therefore measure
**real orphaned bytes** (`is_file()`), not enumeration phantoms, with a short
patience window; the upload-refusal path also asserts deterministic invariants
(429 + no job row + no history row).

## What R6/R7 change

### Daily quota is now charged at ACCEPTANCE into a durable per-user/day ledger
- `daily quota = accepted engine work`. A submission is charged **after** the
  reuse/dedup short-circuits and **before** the original upload + job creation.
  Failed accepted submissions keep their charge (the accepted row may still be
  retried by reconciliation); a refused, race-lost, or never-accepted submission
  does not.
- Ledger table `translation_quota` keyed `(user_id, quota_day)`; a new calendar
  day starts clean with no cleanup step.
- `QuotaService::reserve()` = `firstOrCreate` + a single **atomic conditional
  UPDATE** (`files < max AND bytes <= max - bytes`) — the WHERE is re-evaluated
  under the row lock, so concurrent submissions serialize at the boundary line.
  Accepts an optional `$forDay` so callers pin the charge day.
- `QuotaService::refund()` is now a single **atomic conditional UPDATE** guarded
  by `files > 0` with a byte `CASE` clamp: it can never refund more than the
  recorded charge and can never overwrite a concurrent reservation (each refund
  decrements exactly one charged file under the row lock). It takes the
  caller-captured charge day, so a refund that straddles midnight still lands on
  the exact ledger that was charged.
- **Acceptance boundary rule (applies to upload and re-translate):** a job is
  ACCEPTED only when its row reaches `STATUS_QUEUED`. If anything fails BEFORE
  that point — including the `create()` reaching the active-job partial unique
  index — there is no accepted job, so the partial row is deleted, the
  reservation is refunded (to the pinned day), the scratch dir is cleaned, and a
  lost race returns the winner instead of an error. If failure happens AFTER the
  row is queued, the charge stands and queue/reconciliation own the row.
  (Previously the `TranslationJob::create` INSERT sat OUTSIDE the try, so a real
  race at the partial unique index escaped as an uncaught 500 with the budget
  still consumed.)
- `TranslationController::handleDocument` now calls `reserve()` (was a
  read-then-insert check against history rows); `DocumentsController::retranslate`
  charges the same budget (dedup short-circuits are still free) and now handles
  the race seam the same way (`QueryException` → winner return or refund).
- Old `exceedsUploadQuota()` / `cleanupUploadDir()` removed; all scratch cleanup
  funnels through `FileCleanup::dir()` (guarded, non-fatal, with a short rmdir
  retry for Windows handle timing).

### History deletion is now transactional + durable, with an outbox retry
- `HistoryService::deleteRecord()` runs a **single** `DB::transaction` that
  deletes children + record and, in the same commit, `recordPending()`s every
  unique `(backend, path)` object the batch stops referencing. A storage outage
  can no longer strand objects whose owner row is gone.
- `hasLiveReference()` protects a shared object (e.g. a retranslate original)
  referenced by any surviving row; batch-deleted ids are excluded.
- `HistoryController::destroy` returns after `processPending()` — a best-effort
  immediate pass; failures stay pending.
- `storage_cleanup_outbox` is idempotent (unique backend/path), missing objects
  resolve to done, real failures bump `attempts` (clamped at 1,000,000 so an
  endlessly failing backend can never overflow the counter on either engine)
  and keep the row pending.
- `translations:cleanup-storage` artisan command retries pending entries;
  scheduled `->everyFiveMinutes()->withoutOverlapping()` in `bootstrap/app.php`.
- `StorageService::delete()` local branch is now observable: a real unlink
  failure throws instead of silently succeeding via `@unlink` — the outbox then
  keeps the entry for retry.

## Tests added (19, +2 assertions to existing quota test)
- `tests/Feature/UploadQuotaAtomicityTest.php` (12)
  - reserve charges files+bytes; obeys file and byte caps; refund returns
    capacity and never goes negative; refund targets the charged day across a
    midnight boundary; yesterday does not count toward today; quota is per-user.
  - refused upload → 429, no job row, no history row; **real duplicate-submission
    race** (winner row appears inside the loser's `creating` event, tripping the
    partial unique index) → winner returned + loser fully refunded for upload and
    for re-translate; **job creation failure after reservation** → 500, refunded,
    zero rows, no real scratch leak; completed result reuse is never charged;
    retranslate consumes the same quota and refuses a capped second attempt
    cleanly.
- `tests/Feature/HistoryDeletionOutboxTest.php` (7)
  - delete removes rows and cleans all unique objects; shared original survives
    while any other row references it; backend failure leaves a pending row that
    `translations:cleanup-storage` retries to done; missing object resolves to
    done; foreign/absent record returns 404 and changes nothing; a local unlink
    failure keeps the entry pending and retryable; **400+ persistent failures
    keep the entry pending with a clamped counter that never overflows** and the
    same entry resolves to done once storage recovers.
- `tests/Feature/TranslationControllerTest.php` — quota test now seeds the ledger
  row (`translation_quota`), not history rows.

## Remaining scope (corrected)
The R6/R7 work above is complete and verified. The remaining packages from the
plan are implemented as one sequence: User-experience truthfulness U1–U4
(long-running translation status, accurately scoped admin draft preview,
accessible review controls + precise draft/published feedback, rendered
desktop/mobile + file-preview checks) then R8 (Python spacing contract,
deterministic Python suite, honest quality-score wording, representative
real-service and human meaning/layout validation). The two-role architecture and
existing features are preserved.

**Explicitly NOT in scope** (previously mislisted): live-path auth/policy,
job-policy reviewer contracts, password-reset/session UX, notifications/consent,
scheduling, or offline work. None of these are to be implemented.

Plan reference: `codex/IMPLEMENTATION_PLAN_EXISTING_SYSTEM_2026-09-28.md`.

## Remaining limits (honest)
- Quota/outbox tests run against SQLite `:memory:` via `RefreshDatabase`.
  Production target is PostgreSQL + the real Supabase/queue backends; the
  atomic refund/outbox SQL is portable (single-statement updates), but
  concurrency under actual Postgres row-locking has NOT been load-tested.
- The duplicate-race tests simulate the interleave deterministically (the
  winner's row is injected at the loser's `creating` event); no real two-worker
  concurrency run has been performed.
- Refund cross-midnight coverage proves the pinned-day mechanics; no live
  clock-boundary run.
- `php artisan test` is the only CI gate executed; no external lint/Pint run.