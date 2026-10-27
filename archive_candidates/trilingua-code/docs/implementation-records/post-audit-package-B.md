# Post-audit Package B - Publication and audit integrity

Scope (approved): make review-status changes and their audit rows atomic; give
document blocks a durable `published_text` that reflects the downloadable file
(not the draft); protect draft editing and publication from stale submissions;
make the legacy backfill evidence-based; expose published content (never draft)
through the owner Final/Saved endpoint.

## Reproduced failures (before this package)

- `ReviewService::verify/flag/flagDocument/editText/updateBlock/applyBlockEdits`
  wrote the status change and its `translation_edit_log` row in two separate
  statements: a crash between them left a status change with no audit trail (or
  vice versa). A multi-block batch could also persist some blocks before failing.
- `saveAndRegenerate()` committed the storage pointer and `published_revision`,
  then wrote the `publish` audit row afterwards (was line 454). A crash between
  the two left a published file with no publish audit.
- Per-block published text was never persisted, so the owner/detail Final/Saved
  block fallback rendered `current_text`, which can be an UNPUBLISHED draft. A
  user could see draft wording presented as the saved/downloadable result.
- The owner `GET /history/{id}/blocks` endpoint returned `current_text`.
- No stale-submission protection: an admin acting on an old page could overwrite
  a newer admin draft text, or republish over a newer file.
- `ReviewController::show()` eager-loaded a whole-document `$documentBlocks`
  collection that the view never used.

## Changes

### New
- `database/migrations/2026_09_28_000006_add_published_text_to_translation_blocks_table.php`
  - adds nullable `translation_blocks.published_text`; runs the evidence-based
  backfill (see `LegacyPublishedTextBackfill`).
- `database/migrations/2026_09_28_000007_add_kind_to_storage_cleanup_outbox_table.php`
  - adds `storage_cleanup_outbox.kind` (`orphan` | `candidate`), backfilling
  existing rows to `orphan`.
- `app/Support/LegacyPublishedTextBackfill.php` - the exact backfill predicate,
  unit-testable and reused by the migration.
- `app/Exceptions/ReviewConflictException.php` - mapped to HTTP 409.

### Changed
- `app/Services/Admin/ReviewService.php`
  - Every status/editorial change and its audit row now commit in ONE short
    `DB::transaction`: `verify`, `flag`, `editText`, `verifyDocument`,
    `flagDocument`, `applyBlockEdits`. `applyBlockEdits` locks the history row
    (`lockForUpdate`) for the whole batch, so a mid-batch failure rolls back all
    blocks, the audit rows, and the draft-revision bump.
  - `saveAndRegenerate()` now:
    - accepts `expectedDraftRevision` / `expectedStoragePath` and refuses a stale
      submission (409) instead of overwriting newer state;
    - registers a durable publish CANDIDATE (`recordPublishCandidate`) BEFORE
      upload, so a crash between upload and commit cannot orphan the object;
    - commits the pointer, `published_revision`, the per-block `published_text`
      snapshot, the `publish` audit row, and the candidate clear in ONE
      transaction (after the Python/storage calls, never during);
    - records the superseded object as a durable cleanup intent (`recordPending`)
      instead of best-effort inline deletion.
  - No DB transaction is held open across a Python or storage call.
- `app/Services/StorageCleanupService.php`
  - `processPending()` only deletes `orphan` rows and re-checks live references
    immediately before deleting; a re-referenced path cancels its intent
    (marked done) rather than being deleted.
  - `recordPending()` re-arms a previously DONE row (firstOrCreate no longer
    silently leaves a reused path done).
  - New `recordPublishCandidate()`, `markCandidatesCommitted()`,
    `reclaimStalePublishCandidates()` (grace-period reclamation of candidates
    that were never committed).
- `app/Console/Commands/CleanupStorage.php` - also runs the stale-candidate pass
  (`--candidate-grace`, default 3600s).
- `app/Services/BlockService.php` - initial block persistence sets
  `published_text = ai_translated_text` (the file is generated from that text).
- `app/Models/TranslationBlock.php` - `published_text` is fillable.
- `app/Http/Controllers/Admin/DocumentReviewController.php`
  - `updateBlock` requires `expected_draft_revision`; `saveAndRegenerate`
    requires `expected_draft_revision` and accepts a nullable
    `expected_storage_path` (empty renders as null via ConvertEmptyStringsToNull
    for a record with no published pointer yet).
  - `ReviewConflictException` maps to HTTP 409; the publication message no longer
    claims the superseded file stays available.
- `app/Http/Controllers/HistoryController.php` - `blocks()` (owner Final/Saved)
  now returns `published_text` + `has_published` and NEVER `current_text`.
- `app/Http/Controllers/Admin/ReviewController.php` - `blocks()` returns draft
  `current_text` (labelled) plus `published_text`/`has_published`; the unused
  `$documentBlocks` eager load and its view key were removed.
- `resources/js/document-preview.js` - block fallback renders `published_text`
  in published mode and shows Published text preview unavailable when it is
  unknown; never substitutes a draft. `loadBlockFallback` reads `data-blocks-mode`.
- `resources/views/history-detail.blade.php` - translated host sets
  `data-blocks-mode=published` (original host unchanged).
- `resources/views/admin/review-document.blade.php` - converter host sets
  `data-blocks-mode=published`; the block-update form carries
  `expected_draft_revision`; the Save & Regenerate form carries
  `expected_draft_revision` and `expected_storage_path`.

## Legacy backfill (`published_text`)

A legacy row is populated ONLY when it is unambiguous: it is a document with a
downloadable `storage_path`, `draft_revision = published_revision = 0`, has NO
`edit`/`publish` row, and every block is still `pending`. In that case
`published_text = current_text` (the original AI output). Every other row stays
NULL (unknown); its downloadable file is preserved and the UI shows Published
text preview unavailable until reconciled. `review_status`,
`current_text == ai_translated_text`, and `published_revision >= draft_revision`
are deliberately NOT used as proof.

## Migration / rollback

- Apply: `php artisan migrate`. Up adds the column and runs the backfill.
- Rollback: `php artisan migrate:rollback` drops `published_text`; the file is
  untouched. Dropping the column DISCARDS the captured published snapshot, so
  re-applying re-runs the backfill (already-published rows will be left unknown
  and must be reconciled from the downloadable file).
- Before applying to an existing production database, inventory qualifying vs
  ambiguous document histories and take a backup; the backfill only fills
  unambiguous rows and never deletes a file.

## Tests

- `tests/Feature/Admin/ReviewPublishedTextTest.php` (new, 6 tests) - publish
  snapshot vs draft vs immutable AI text; owner endpoint published-only; initial
  translation sets published_text; legacy backfill populates only unambiguous
  rows; batch audit failure rolls back the whole edit; verify status rolls back
  with a failed audit.
- `tests/Feature/Admin/ReviewConcurrencyGuardTest.php` (new, 4 tests) - stale
  draft revision gives 409 with no overwrite; matching revision succeeds; stale
  pointer gives 409 keeps the previous file and cleans the candidate; stale
  revision fails before any storage call.
- Updated to the intended contract: `DocumentPreviewTest`, `AdminWriteHttpTest`,
  `ReviewDraftPublishHttpTest`, `ReviewDraftPublishIntegrityTest`.

Commands / results:

```
php artisan test tests/Feature/Admin            -> 100 passed (466 assertions)
php artisan test --filter=DocumentPreviewTest   -> passed
php -l (each changed PHP file)                  -> no syntax errors
node --check resources/js/document-preview.js   -> ok
```

## Remaining limits

- Live PostgreSQL / two-worker concurrency and real Supabase behaviour are NOT
  exercised here (see the release report); they remain release-blocking until a
  live environment runs them.
- Candidate reclamation relies on a grace period (default 3600s) that must be
  longer than a real regeneration; on fallback-local uploads the pre-upload
  candidate is keyed to the primary backend and a second candidate is added for
  the actual backend after upload (documented residual).
- Comparing the Final fallback text against the actual downloaded file requires a
  served-browser / human gate that has not been run.