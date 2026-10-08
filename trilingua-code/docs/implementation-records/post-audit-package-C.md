# Post-audit Package C - Downloads and cleanup

Scope (approved): every completed-status source must return a download link only
when backend evidence proves the object is readable; a storage outage must never
be reported as a confirmed failure; superseded and uncommitted regeneration
candidates must be cleaned up durably without ever deleting live data.

## Reproduced failures (before this package)

- `TranslationController::buildHistoryCompletedPayload()` fell back to the
owner-authorized streaming route whenever the Supabase signer threw, WITHOUT
proving the object could be read. A completed job could therefore advertise a
download link that 404s.
- There was no way to distinguish a confirmed-missing output (terminal) from a
temporary storage outage (uncertain): a status-time outage risked either a
broken link or (if naively handled) flipping a completed job to failed.
- `StorageCleanupService::processPending()` deleted outbox paths without
re-checking live references at run time.
- `recordPending()` used firstOrCreate, so a path that already had a DONE row
could never be cleaned again.
- Superseded regenerated objects were deleted best-effort inline (log-only on
failure); a crash between upload and commit could orphan an object with no
durable record.

## Changes

- `app/Services/StorageService.php`
  - New `exists(string $backend, string $storagePath): string` returning
    `PRESENCE_PRESENT` / `PRESENCE_MISSING` / `PRESENCE_UNKNOWN`.
    - local: present only when the file exists AND is readable; missing when the
      file does not exist; unknown when it exists but is not readable.
    - supabase: an authenticated HEAD returns present on 2xx, missing on 404, and
      unknown on any other status or a connection error. Unknown is deliberately
      never treated as a confirmed failure.
- `app/Http/Controllers/TranslationController.php`
  - `buildHistoryCompletedPayload()` now calls `readableOrUnavailable()`;
    - present  -> owner-authorized streaming route (proven readable);
    - missing  -> terminal `failed` with `recoverable = false` (the output is
      confirmed gone);
    - unknown  -> the record STAYS completed (`download_available = false`, no
      `download_url`, an honest retry-soon message). The durable job row is never
      flipped to failed by a status-time outage.
- `app/Services/StorageCleanupService.php`
  - `processPending()` only deletes `kind = orphan` rows and re-checks live
    references immediately before each delete; a re-referenced path has its
    intent cancelled (marked done) instead of being deleted.
  - `recordPending()` re-arms a DONE row (new intent, attempts reset).
  - New `recordPublishCandidate()` (durable pre-upload candidate),
    `markCandidatesCommitted()` (atomic candidate clear inside the publish
    transaction), and `reclaimStalePublishCandidates(graceSeconds, limit)`
    (reclaims only candidates older than the grace period that are not
    live-referenced; a surviving candidate is never a committed object because
    the publish transaction deletes it atomically with the pointer write).
- `app/Console/Commands/CleanupStorage.php` - runs the stale-candidate pass with a
  configurable `--candidate-grace` (default 3600s).
- `app/Services/Admin/ReviewService.php` - superseded regenerated objects are
  recorded durably via `recordPending()` instead of an inline best-effort delete,
  so a failed delete stays retryable and a shared/re-referenced path is protected
  by the run-time live-reference re-check.
- `database/migrations/2026_09_28_000007_add_kind_to_storage_cleanup_outbox_table.php`
  - adds and backfills `storage_cleanup_outbox.kind`.

## Crash-window and concurrency reasoning

- The publish candidate row is written BEFORE the upload (keyed to the intended
  primary backend; a fallback-local object gets a second candidate after the
  upload). The publish transaction clears the candidate in the SAME statement
  batch that sets the pointer, so any surviving candidate is unambiguously
  never-committed and safe to reclaim. A candidate that is still being published
  is younger than the grace period and is protected by the live-reference check.
- `processPending` and `reclaimStalePublishCandidates` are idempotent: a missing
  object resolves to done; a real failure bumps attempts and stays pending.

## Tests

- `tests/Feature/TranslationStatusDownloadIntegrityTest.php` (new, 5 tests) -
  signer failure with a readable object returns the owner route; confirmed-missing
  returns terminal failure; an outage keeps the job completed without a link and
  does not flip DB state; local present/missing behave correctly.
- `tests/Feature/StorageCleanupServiceTest.php` (new, 6 tests) - live-referenced
  path intent is cancelled not deleted; orphan is deleted; a DONE row is re-armed;
  stale unreferenced candidate reclaimed while a live one is kept; grace period
  respected; committed candidates cleared.
- Updated to the new contract: `TranslationStatusTerminalStatesTest` (fallback now
  requires proven readability).

Commands / results:

```
php artisan test tests/Feature/TranslationStatusDownloadIntegrityTest.php -> 5 passed
php artisan test tests/Feature/StorageCleanupServiceTest.php              -> 6 passed
php artisan test tests/Feature/... (root Feature chunk)                   -> 104 passed
php artisan test tests/Feature/Admin                                     -> 100 passed
php artisan test tests/Unit                                               -> 131 passed
```

## Remaining limits

- The Supabase HEAD path is implemented and unit-shaped but NOT exercised against
  a live Supabase here; the handoff explicitly warns that an untested HEAD does
  not prove a working download. Treat the Supabase readability proof as unverified
  until a live environment runs it.
- A process-interruption / failed-deletion / shared-reference test matrix beyond
  the unit cases above requires the two-worker live environment.
- Grace-period tuning for candidate reclamation must exceed the worst-case real
  regeneration duration in production.