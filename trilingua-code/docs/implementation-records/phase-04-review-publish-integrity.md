# Phase 4 — Review edit/publish integrity (R5)

Date: 2026-09-28 · Branch: `walben`

## Before-state
- Save Edit and Save & Regenerate were **synonyms**: both opened a write on the live file, so a half-finished stack of edits could become the "current" downloadable document, and a failed regeneration could leave the review blocked mid-transition.
- Verify was allowed even while un-published edits were outstanding (approved decision → must be refused).
- Legacy records born in the old regime carried `review_status='edited'` with no way to tell whether the file actually contained the edits.
- Reads of translated files were single-backend (Supabase) even when the pointer said `local`; there was no way to stream the original file.

## Contract
- **Save Edit = draft.** Writes are persisted and audited, but the downloadable file is untouched.
- **Save & Regenerate = publish.** Only a *successfully* uploaded, read-back-verified, DB-committed new object becomes the current downloadable file. On any failure (Python, upload, read-back, DB commit) the previous file stays authoritative and the edits remain a draft.
- **Verify is refused while `draft_revision > published_revision`.**
- Legacy `edited` rows are reconciliation-flagged (`draft_revision=1`, `published_revision=0`) — never silently claimed as published.

## Changed files
- `database/migrations/2026_09_28_000003_add_review_revisions_to_translation_history_table.php` — **new**: `draft_revision`/`published_revision` (unsigned big integers, default 0) + backfill of records with `review_status='edited'` to `draft_revision=1` (reconciliation flag). No versioning framework.
- `app/Models/TranslationHistory.php` — fillable + integer casts for both revisions; `hasUnpublishedEdits(): bool` (`draft_revision > published_revision`).
- `app/Services/Admin/ReviewService.php`:
  - `verifyDocument` refuses while `hasUnpublishedEdits()` (message points at Save & Regenerate).
  - `updateBlock` routes through `applyBlockEdits`, which bumps `draft_revision` by the number of changed blocks and flips `review_status` to `edited`.
  - `saveAndRegenerate(int $historyId, int $adminId, array $blockIdToText, ?string $note = null)` — **signature changed** (was index-keyed overrides). Flow: guard (document type + original present) → `applyBlockEdits` → reload a fresh history instance (the publish instance must see the draft bump) → consistent snapshot keyed by `block_index` → `storage->read(original_storage_backend ?: 'supabase', original_storage_path)` → sidecar overlay (now `ksort`-ed by `block_index`) → reconstruction-only `regenerateDocument` → temp write → `uploadWithFallback` to `{uid}/translations/{uuid}.{ext}` → read-back verify → **single DB save** committing pointer + backend + filename + `signed_url_expires_at` + `reviewed_by/at` + `published_revision = draft_revision` → `action='publish'` audit row → best-effort delete of the superseded object (only after commit).
  - Failures: `cleanupUploadedObject()` guards the candidate on read-back or commit failure; original-read/python/upload failures leave everything untouched (draft preserved).
- `app/Http/Controllers/Admin/DocumentReviewController.php`:
  - `wrap` also maps `\InvalidArgumentException` → 422.
  - `saveAndRegenerate` delegates fully to the service and returns backend-aware links: supabase → signed URL; local → `route('admin.review.document.file')`. New `originalDownloadUrl()` mirror (supabase → signed URL; local → new `admin.review.original-file` route).
  - New `showOriginalFile(TranslationHistory)` streams the original via backend-aware `read` with MIME sniffing. `showTranslatedFile` reads via `read(storage_backend ?: 'supabase', storage_path)`.
  - `updateBlock` response now carries `draft => true` + guidance message.
- `routes/web.php` — `GET /admin/review/{translation}/original-file` → `admin.review.original-file`.
- `resources/views/admin/review-document.blade.php` — `$hasDraft` computed; header "Unpublished edits"/"Published" badge; conditional draft-warning paragraph (`id="draft-warning"`); block badge shows "Draft edit" when a draft is outstanding; toast prefers `data.message`; regen handler sets `suppressLeavePrompt` only on success, calls `markPublished()` (marks textareas saved, swaps badges, hides the warning via stable id) and no longer auto-reloads the page.

## New tests
- `tests/Feature/Admin/ReviewDraftPublishIntegrityTest.php` (10 cases): draft-vs-published separation; verify rejection (service); durable publish (+ supersede delete); read-back verification in the success path; Python failure keeps draft + last usable file; upload failure keeps previous file authoritative; read-back failure cleans up candidate (`RuntimeException`); DB commit failure cleans up candidate via a `TranslationHistory::saving` poison listener; original read honors the recorded backend; repeat submission with zero edits registers zero edited blocks but republishes.
- `tests/Feature/Admin/ReviewDraftPublishHttpTest.php` (9 cases): verify-document 422 over HTTP with an outstanding draft; verify succeeds after publish; updateBlock returns `draft=>true`; save-regenerate supabase → signed URL; save-regenerate local-fallback → authenticated `admin.review.document.file` route; Python failure → 422 + pointer untouched; non-document rejected; original-file route streams local originals inline with correct MIME/Disposition.

## Focused checks (all run/verified)
1. R5 batch (6 files, including updated `AdminWriteHttpTest`, `ReviewBlocksPersistenceTest`, `DocumentReviewWriteActionsTest`, `ReviewRoutesTest`) → **64 passed (301 assertions)**.
2. `php artisan test` → **347 passed, 1 skipped (1400 assertions)**. Prior phase was 327/1 (1271) → +20 cases, +129 assertions.
3. `php -l` clean on controller, service, model, migration, and all changed/new test files.
4. Blade render verified for both badge states (published vs unpublished draft) with markup-precise assertions in `ReviewRoutesTest`.

## Key decisions & notes
- Single DB write publishes pointer + published state; **no wrapping transaction** (same sqlite savepoint constraint as Phase 3). The audit row is appended after the save; a failure there leaves a valid published file with a missing audit row (acceptable: file predicate is the pointer move, audit is observability).
- The publish instance is re-loaded **after** `applyBlockEdits` — the stale instance bug (publishing `published_revision = 0`) was caught by the tests.
- Precedence: previous file is deleted only after commit and only when the key differs (superseded-object cleanup is best-effort; a stranded object is harmless orphan storage, never an authoritative pointer).
- Legacy `edited` records are flagged as drafts purely for reconciliation — the download keeps pointing at whatever the file holds; admins must re-publish to confirm.
- CSS/JS risk retired: `markPublished` now hides `#draft-warning` by stable id instead of the earlier fragile `.review-form-note`+margin heuristic.

## Remaining risk
- Read-back verification calls storage synchronously in the request; on a very slow backend a publish could exceed the worker timeout. Boundary: timeout ladder full check happens in Phase 8.
- `markPublished` behavior is verified only at the unit/render level; a manual browser pass on the review-document page is still on the Phase 8 surface checklist.