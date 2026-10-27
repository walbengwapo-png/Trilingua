# TriLingua existing-system correction plan

**Status:** Implementation proposal for review by the implementing agent and product owner.  
**Baseline:** Current working tree in `C:\dev\Trilingua` on 2026-09-28. It contains substantial pre-existing uncommitted changes; inspect the current diff before editing, preserve unrelated work, and treat this plan as a map rather than a substitute for tracing callers.  
**Objective:** Make the existing two-role web system (regular user and admin) logically consistent, recoverable, secure, and demonstrably ready for deployment. Improve only UI/UX that affects comprehension, accessibility, or correct completion of existing flows.  
**Out of scope:** New roles, new translation providers, new document formats, a visual redesign, speculative abstractions, quality/accuracy claims based only on automated scores, deployment or data migration without a separate deployment review.

## 1. Operating contract for the implementing agent

1. Reproduce each failure with a focused test or controlled scenario before changing code. Trace every caller of a shared method and apply a root-cause fix at the common layer where appropriate.
2. Implement in the order below. One phase must have passing acceptance checks before the next phase alters its assumptions. A code change passing unit tests is not equivalent to a real provider, storage, browser, or deployment check.
3. Keep the current Laravel/Python boundary: Laravel owns users, authorization, queue state, review, history, and storage; Python owns translation, analysis, and reconstruction. Reuse `StorageService`, `TranslationJob`, and existing routes before introducing new classes or dependencies.
4. Preserve document bytes, original source, existing translations, review audit history, and ownership rules during fixes. Avoid rewriting unrelated pages or translation logic.
5. Capture a short implementation record per phase: files changed, behavior before/after, commands run, failures observed, remaining limitations. Do not report a feature as working solely because a mocked test passed.
6. Before any migration or repair against an existing database, inventory affected rows and provide a reversible runbook. Never print credentials, tokens, uploaded content, or user documents in the report.

## 2. Confirmed architecture and baseline evidence

- `routes/web.php` has authenticated regular-user routes and a nested `admin` middleware group. `users.is_admin` is the only application role flag; there is no separate translator or reviewer account type.
- `TranslationController` accepts text synchronously and documents through `TranslateDocumentJob`. `DocumentsController::retranslate` dispatches the same job type. `TranslationJob` is the durable status row, with cache used as a secondary polling path.
- `StorageService` supports Supabase and a configured durable local fallback. `HistoryController` handles owner-only file streaming; admin review has separate preview and regeneration paths.
- `ReviewService` owns status changes, block edits, and audit rows. `DocumentReviewController` also persists on-screen edits before calling regeneration.
- Prior read-only checks: `php tests/assert-safe-test-env.php` passed; `php artisan test` reported **294 passed, 1 skipped**; selected deterministic Python pipeline/review/regeneration tests reported **123 passed**. Broader Python test discovery stopped on `tests/test_properties.py::test_chunk_content_round_trip` with input `0  0`. These results describe the checked working tree, not production behavior. Re-run after implementation.
- No live provider, storage, browser, multi-worker, deployment, human translation-quality, or full format/language-pair verification has been completed for this assessment.

## 3. Release-risk findings: problem, consequence, correction

### R1 — Critical: automatic administrator with a known password

**Evidence:** `trilingua-code/database/migrations/2026_09_06_000003_seed_default_admin_user.php` inserts `admin@example.com` with password `password` on fresh migration. `database/seeders/DatabaseSeeder.php` also creates or updates that address with the same password and `is_admin=true` when seeding runs.

**Problem and justification:** A known credential grants access to every admin review, user, job, and audit route. Removing only the migration leaves the seeder able to reset an account to the known password. Existing deployed databases will not be repaired by changing old migration source alone.

**Implementation:**

1. Remove known-credential provisioning from both production migration behavior and general seeding. Keep explicit test-only fixtures in tests/factories. For already-applied migrations, add a safe forward remediation path; do not assume edits to an old migration rerun in deployed databases.
2. Specify a controlled first-admin procedure using a one-time operator action or environment-provided secret that is not committed. Do not create a permanent default credential or rely on a hidden UI route.
3. Inventory existing environments for the address without logging password hashes. Rotate or disable accounts whose provenance is uncertain, and document operator action for an existing real admin using that address. This step needs an environment-specific deployment decision; do not silently delete a live account.
4. Add a fresh-install check that no known admin password works and a seed check that seeding cannot turn an existing account into a known-password admin.

**Gate:** Fresh migration and ordinary seeding expose no fixed admin login; existing-environment remediation is documented and verified by an authorized operator before public exposure.

### R2 — High: queue lease, worker timeout, and reconciliation disagree

**Evidence:** `config/queue.php` defaults `DB_QUEUE_RETRY_AFTER=900`; `.env.example` repeats 900. `TranslateDocumentJob::$timeout=1300`, Python HTTP timeout defaults to 1200, and `start-all.bat`/`start-demo.ps1` launch `queue:listen` with `--timeout=1500`. `bootstrap/app.php` schedules `translations:reconcile --fail` every five minutes; `ReconcileTranslations` defaults `--processing-timeout=900` and only updates the heartbeat at milestone writes. A single Python translation call can occupy most of the service timeout with no new heartbeat.

**Problem and justification:** After 900 seconds, the database queue may make an active job available to another worker. The scheduled reconciler may also mark its durable row failed while the original worker is still running. This can cause duplicate provider work, competing uploads/history rows, false failure in polling, and conflicting notifications. Changing only `retry_after` leaves the scheduled false-failure path.

**Implementation:**

1. Define one documented timeout ordering across Laravel HTTP, job `$timeout`, worker `--timeout`, database `retry_after`, and reconciliation thresholds. The queue lease must exceed the effective worker timeout with margin. The reconcile threshold must not classify an expected long provider call as a dead worker.
2. Prefer an actual lease/heartbeat-safe mechanism. If no mid-call heartbeat can be emitted safely during blocking Python HTTP, use a conservative processing timeout greater than the maximum expected job execution plus margin; the scheduler must check worker/queue evidence before transitioning to failed. Keep manual report-only inspection available.
3. Apply the same values to both launch scripts, `.env.example`, config defaults, and deployment instructions. Validate real production values at startup or with a diagnostic command so an override cannot silently restore the unsafe ordering.
4. Ensure terminal state transitions are monotonic: an old worker or reconciler cannot overwrite an already completed or failed row without explicit recovery. Review `markProcessing`, `noteError`, `markQueued`, `markCompleted`, and reconciliation writes for conditional updates or locks.
5. Exercise two workers with a controlled slow Python response crossing the old 900-second boundary. Confirm one execution, one history row, one stored output, and accurate status throughout. Use a shortened test clock/config where possible for automated coverage; keep a real-duration staging check for release.

**Gate:** No active job becomes visible to a second worker or gets reconciled as failed during legitimate processing; dead workers eventually become observable and recoverable.

### R3 — High: admin Retry uses a deleted upload

**Evidence:** `TranslateDocumentJob` deletes `$tempPath` on terminal failure, then records the failed queue job. `Admin/JobController::retry` invokes `queue:retry` on the serialized payload. `handle()` first checks `file_exists($this->tempPath)`.

**Problem and justification:** An admin can click Retry, receive a success flash, and run the same failure again. This is both an operational dead end and misleading UI. Original bytes may exist in `original_storage_path`, but the job does not restore them before checking the temp path.

**Implementation:**

1. At job start, if the temp file is absent, use `original_storage_backend` and `original_storage_path` with `StorageService::read` to reconstruct a fresh opaque worker-local input. Reject recovery when no durable original exists; never silently continue with an empty file.
2. Make the retry action check recoverability and the `queue:retry` outcome. Show a precise success or failure message. Do not display an actionable Retry control for a job that cannot be reconstructed, unless the action is explicitly a re-upload flow (which is out of scope here).
3. Keep recovered temp-file cleanup tied to a confirmed terminal outcome; consider what another retry will read after cleanup. Ensure replays are idempotent against any already-created output/history.
4. Cover missing-temp/durable-original, missing-both, Supabase-original, local-original, repeated retry, and owner/admin authorization. Verify failed-job and `translation_jobs` statuses do not disagree after replay.

**Gate:** A recoverable failed job replays to one usable result; an unrecoverable job is clearly identified and does not claim it was retried.

### R4 — High: completed document without persisted history or valid link

**Evidence:** `TranslateDocumentJob` catches failure from history/block persistence as non-fatal, then calls `markCompleted(..., $history?->id)`. `TranslationController::status` returns `processing` when a completed job lacks a usable history payload. Local-fallback links require a history ID.

**Problem and justification:** A completed state can be unresolvable to the user, remain apparently processing, or point to no authenticated file route. The uploaded output may be stranded in storage. This breaks the central submit → finish → download → review sequence.

**Implementation:**

1. Define completion invariant: translated object is durably stored, a history row links the owner/job/file, required review blocks and sidecar are persisted or explicitly marked unavailable, and the download route can resolve the object.
2. Wrap database history/block/metric writes in an appropriate transaction, while recognizing object storage cannot join the DB transaction. On DB failure, do not mark completed. Retain enough durable paths in `translation_jobs` to reconcile or clean up the uploaded object; record a recoverable failure and expose accurate polling status.
3. Make retry of a partially persisted attempt idempotent: use job UUID and existing history association to resume rather than creating a second row/object. Validate uniqueness where necessary at the database layer.
4. Have `status` distinguish a terminal completion-integrity error from genuinely in-progress work. Never return `completed` without an owner-authorized download path that works.
5. Verify with injected history insert, block insert, storage upload, signed-URL generation, and notification failures. Notification or metrics failure may remain non-fatal if the user can still retrieve the file; document that boundary explicitly.

**Gate:** Every completed document has exactly one owner-visible history record and a working download path; all other terminal outcomes are accurately marked failed/recoverable.

### R5 — High: review edits, audit, status, and published document can diverge

**Evidence:** `DocumentReviewController::saveAndRegenerate` calls `applyBlockEdits` before `ReviewService::saveAndRegenerate`; the latter writes blocks/status before downloading, reconstructing, and uploading. Individual `Save Edit` also changes `current_text` and document status without regenerating the file. `verifyDocument` and `flagDocument` cascade status across blocks independently of file regeneration.

**Problem and justification:** A user can download an older file while admin text, audit entries, and status say `edited` or `verified`. Failure during regeneration makes that divergence permanent until manually retried. There is no atomic transaction across a database and object storage, so wrapping everything in one DB transaction alone is insufficient.

**Recommended existing-feature contract (product vision checkpoint):** `Save Edit` persists a **review draft**; `Save & Regenerate` publishes a new downloadable file; only a successfully published version may be represented as containing the edits. Verification should identify what version was reviewed. This contract should be approved or corrected by the product owner before implementation because it changes the meaning of the current review badge.

**Implementation after contract approval:**

1. Separate draft block state from the published file state using the smallest durable marker/version needed. Preserve immutable AI text and append-only edit logs. Avoid adding a general versioning framework unless the accepted contract requires it.
2. On regeneration, validate block IDs and collect a consistent snapshot of current text. Reconstruct from the original through Python, upload to a new unique storage key with `uploadWithFallback`, and verify the new object is readable before switching the history file pointer. Commit pointer and published review state together in DB. If commit fails, retain or schedule cleanup of the new object; the old published file remains authoritative.
3. Use `StorageService::read($history->original_storage_backend, ...)` for the original and backend-aware reads for admin preview. Persist `storage_backend` when a regenerated output lands on local fallback. Return the authenticated history route for local files and a valid signed URL for Supabase files.
4. Update `Save Edit`, `Verify`, `Flag`, and `Save & Regenerate` responses and visible labels to distinguish draft content, published content, and review disposition without inventing an extra role. When regeneration fails, show that edits remain saved as draft and the previous file remains downloadable; do not show a success message for publication.
5. Cover missing original, Python error, upload error, DB commit error, concurrent admin edits, repeat submission, local fallback, owner download, admin preview, and audit trail order. Verify the user sees the correct file and status after each outcome.

**Gate:** Admin draft, audit, review state, and actual downloaded file are never represented as the same version when they differ; failed regeneration cannot replace or lose the last usable file.

### R6 — Medium: upload quota can be bypassed by concurrent accepted work

**Evidence:** `TranslationController::exceedsUploadQuota` counts completed document history rows for the current day; `DocumentsController::retranslate` has a separate intake path.

**Problem and justification:** Concurrent uploads see the same completed count and can all be accepted. The cap limits completed results rather than work sent to the engine, so it does not bound resource consumption.

**Implementation:**

1. Confirm the intended policy with the product owner: whether re-translation consumes the same daily file/byte quota, and whether failed accepted submissions consume it. The recommendation is to count accepted work because that is what consumes provider and queue capacity.
2. Enforce a single intake calculation for uploads and, if policy includes them, re-translations. Count accepted `translation_jobs` plus applicable legacy completed history without double counting jobs that already have history.
3. Serialize per-user acceptance with a short DB row lock or equivalent atomic reservation. Keep file hashing/storage work outside the lock where safe; create the accepted job/reservation within the protected section. A rejected request must clean its temporary file and must not dispatch a job.
4. Test simultaneous requests at both count and byte limits, duplicate submissions, midnight/timezone boundary, and a failed or cancelled job according to the approved policy.

**Gate:** Concurrent acceptance cannot exceed the defined quota; deduped work is not charged twice.

### R7 — Medium: deleting history can strand storage objects

**Evidence:** `HistoryService::deleteRecord` deletes parent and child DB rows, then `HistoryController::destroy` best-effort deletes storage entries. A storage error is only logged. Local deletion currently suppresses an `unlink` failure.

**Problem and justification:** After the row is gone, cleanup loses its durable object list; user data may remain stored without a visible owner record. Retrying a delete request cannot find the removed row.

**Implementation:**

1. Record deletion intent and the unique backend/path pairs durably in the same DB transaction that removes or marks the history. Use a minimal outbox/cleanup table or a durable queued job with equivalent crash-safe persistence; do not rely on post-response memory or logs.
2. Perform idempotent deletes asynchronously or immediately with retry. Treat already-missing objects as success. Make local `unlink` failures observable rather than silently successful.
3. Preserve ownership and cascade scope for child translations. Avoid deleting a shared original object while another surviving child still references it; verify actual reference relationships before deleting each unique path.
4. Test remote and local failure, process crash between DB commit and object deletion, repeated cleanup, child deletion, and owner visibility after deletion.

**Gate:** Every removed record's storage paths remain discoverable until deletion is confirmed; cleanup can be retried safely.

### R8 — Medium: red Python property test and unverified quality claims

**Evidence:** `Model/tests/test_properties.py::test_chunk_content_round_trip` expects `'0  0'` to normalize to `'0 0'`, while `Chunk_Splitter` returns the original short string. `quality_score` and issues are surfaced in admin/user views, but no human calibration establishes that score as translation accuracy.

**Problem and justification:** A red test weakens release confidence, but changing a layout-sensitive chunker to satisfy a possibly incorrect test may damage document fidelity. Numeric scores can imply a validated precision they do not have.

**Implementation:**

1. State the text contract for the chunker: exact spacing preservation or normalized semantic text. Examine callers and format expectations; fix the test or implementation to match, with a focused regression for repeated spaces and a real document case.
2. Run the deterministic Python suite separately from live-provider/benchmark tests. Do not let benchmark tests rewrite user artifacts during normal CI. Record any intentionally skipped live dependencies.
3. Audit where quality scores are displayed. Until calibrated, label them as automated review signals rather than verified accuracy; avoid threshold colors that imply pass/fail unless backed by human evaluation.
4. Conduct a controlled acceptance matrix: supported format × source/target language pairs, a small representative sample of short/long, structured, scanned, and layout-sensitive documents, human judgments for meaning and layout, and actual download/open checks. Define pass thresholds from the results before claiming production quality.

**Gate:** Deterministic tests pass with a documented spacing contract; product copy does not overclaim; human-evaluated samples meet accepted quality/layout criteria.

## 4. UI/UX corrections tied to existing workflows

These observations come from source code. The implementing agent must inspect rendered desktop/mobile pages and keyboard behavior before changing styling.

### U1 — Translation page reports a false timeout

**Evidence:** `resources/views/translation.blade.php::pollJobStatus` stops after 300 polls at two-second intervals and displays “Translation timed out.” Python HTTP can run for 1200 seconds; queue waiting and file work add time. `TranslationController::status` already has durable job state.

**Solution:** The browser must not infer job failure from elapsed polling time. Use durable `failed`/`completed` status for terminal claims. On long waits or intermittent network loss, show “still processing/status unavailable” and a route to the existing Saved Translations or status view; persist the job ID in the current page/session if needed so refresh does not discard the user's ability to check. Avoid a new tracking feature if a small existing-route link suffices.

**Acceptance:** Simulated 11–25 minute job never displays a false failure; real failure displays the server error; refresh/navigation preserves a way to locate the result; polling does not issue overlapping requests or run without bound after navigation.

### U2 — Admin Draft preview implies a whole document but renders one page

**Evidence:** `Admin/ReviewController::show` paginates editor blocks at 25; `resources/js/review-document.js::renderDraft` reads only DOM `.doc-block` elements. The page labels the pane “Draft” under “Translated Document” without explaining its scope.

**Recommended minimal correction:** Label it “Current page draft preview” and show the current block/page range. Preserve the existing full saved-file preview. A full-document draft preview is a separate product decision because it requires merging all persisted blocks with unsaved edits from the current page and may be expensive for large documents.

**Acceptance:** A reviewer with >25 blocks can tell which subset is previewed; switching pages does not silently imply unsaved edits were carried forward; beforeunload warning and unsaved count work for navigation and form submits.

### U3 — Review controls and output state need accessible, precise feedback

**Evidence:** The block editor textarea has no associated `<label>`; review tabs switch `is-active` and panel display but do not expose a selected state or panel relationship. `Save Edit` marks block state as edited while the saved file can remain old. The Jobs page advertises Retry even when input is unavailable.

**Solution:** Give every block textarea a unique programmatic label (e.g. block index/type), expose tab selection and controlled panel IDs using an appropriate button/tab pattern, retain visible focus, and give Save/Regenerate/Retry distinct accurate success/failure messages. Do this alongside R3/R5 so UI wording reflects real server state. Avoid a new component library or global redesign.

**Acceptance:** Keyboard-only reviewer can reach and identify every action; screen reader can identify the current preview and block editor; failed regeneration/retry cannot show success; statuses describe whether edits are draft or included in the downloadable file.

### U4 — Verify rendered layout and preview behavior before cosmetic changes

**Evidence:** `document-preview.js` lazy-loads DOCX/XLSX/PPTX conversion and falls back to DB blocks; that fallback is content-only and should not be mistaken for a faithful file rendering. The admin review page additionally loads a full block list for the document view despite paginating the editor.

**Solution:** On desktop and narrow mobile widths, inspect translation, history detail, admin queue/jobs, review document, and error states. Test PDF, DOCX, XLSX, PPTX, plain text, and fallback previews with actual files. Label a block fallback as a text preview with possible layout differences. Measure large-document load time and memory before changing the query or adding virtualized UI.

**Acceptance:** No clipped primary actions, hidden focus, misleading preview fidelity claim, unusable long-document review, or broken download link. Any visual refinement must serve a demonstrated issue and retain the existing visual language.

## 5. Work packages and dependency order

| Order | Package | Depends on | Deliverable | Acceptance evidence |
| --- | --- | --- | --- | --- |
| 0 | Baseline and safeguards | None | Current diff inventory, isolated test environment, failure reproductions, deployment values | No unrelated files overwritten; failing cases reproduced |
| 1 | Admin provisioning (R1) | 0 | Safe migration/seed behavior and existing-environment runbook | Fresh install/seed tests and operator audit |
| 2 | Job timing and retry (R2–R3) | 0 | Consistent timeout configuration, safe reconciliation, recoverable replay | Two-worker slow-job and retry tests |
| 3 | Completion integrity (R4) | 2 | Idempotent history/storage completion and honest polling | Failure-injection matrix; one usable result |
| 4 | Review publication (R5) | 3 and product review-state decision | Backend-aware, failure-safe regeneration and accurate statuses | Admin/user downloads and failure cases |
| 5 | Quota and deletion (R6–R7) | 3 | Atomic intake and durable cleanup | Concurrent quota and object-delete recovery tests |
| 6 | UI/UX corrections (U1–U4) | 2–5 for truthful state | Existing screens communicate actual job, file, and review state | Browser, mobile, keyboard, format previews |
| 7 | Release evidence (R8) | All | Green deterministic suites and real-service/human validation report | Defined acceptance thresholds met |

## 6. Detailed verification matrix

**Role and authorization:** Guest cannot use protected routes; regular user cannot access admin actions or another user's job/history/file; admin can review and retry only through admin routes; changing sessions does not bypass ownership; notification links resolve only to accessible records.

**Text:** Each language pair rejects same-source/target, handles empty/oversized input, returns a translation or honest provider failure, and has an explicit policy for history failure. Admin text verify/edit/flag preserves prior text in the audit trail. Copy/download reflects current persisted text.

**Documents:** For each supported format (`docx`, `pdf`, `txt`, `md`, `rtf`, `odt`, `csv`, `pptx`, `xlsx`) test validation, queue acceptance, dedup, completion, history visibility, original/translated download, and openability. Test local and Supabase backends, malformed extension/content, maximum size, concurrent duplicate submissions, and re-translation. Do not assert language quality solely from API success.

**Queue/state:** Test queued wait, long translation, worker crash, lease expiry, reconciliation, transient provider failure, terminal failure, retry with and without durable original, output-storage failure, history/block failure, repeated retry, completed-result reuse, and deleted history. At every state, compare queue job, `translation_jobs`, history, cache, polling payload, admin jobs page, and user notification.

**Review:** Test block edit vs file version, multiple blocks, pagination, flag/verify, original missing, Python reconstruction failure, Supabase/local read and write, failed upload, DB failure after upload, concurrent admins, and repeat save. Verify audit rows are append-only and immutable AI text remains unchanged.

**UI/accessibility:** Test desktop and mobile viewport widths; keyboard-only translation and review; text field labels, tabs, errors, progress, and focus; reload/navigation with unsaved changes; delayed jobs and network interruptions; PDF/Office/text/fallback previews. Compare displayed status with actual downloaded bytes.

**Operations:** Validate `.env`/launch-time timeout ordering without exposing secrets, run migrations against a fresh DB and a copy of the current schema, check failed-job recovery procedure, and confirm cleanup/reconciliation are observable. Staging must use the same queue/storage configuration class as deployment.

## 7. Product-owner vision checkpoints for plan review

The implementing agent should bring these decisions back before coding the dependent package; the rest of the plan can proceed independently.

1. **Review meaning:** Does `Save Edit` mean a saved draft, or must every edit immediately update the downloadable document? Recommended: saved draft, then explicit `Save & Regenerate` publishes it. This is the least disruptive interpretation of the existing two buttons.
2. **Text history failure:** Must a successful text translation always be saved for later and appear in admin review, or may the user receive an explicitly unsaved result? Recommended: if history is a promised core feature, surface an honest partial-success state and provide a retry path; do not silently claim it was saved.
3. **Quota policy:** Do re-translations and failed accepted jobs consume daily count/bytes? Recommended: accepted engine work counts; identical deduped requests do not count again.
4. **Quality presentation:** Is the automatic score intended only for admin triage, or user-facing quality indication? Recommended: admin triage until human calibration supports user-facing interpretation.
5. **Preview scope:** Is current-page draft preview sufficient? Recommended: label it precisely now; commission a full-document draft preview only if reviewer testing shows it is needed.

These are product semantics, not routine implementation choices. The agent can implement R1–R4 and collect evidence while these are reviewed.

## 8. Release definition of done

- R1–R5 have passing failure-injection tests and staging verification; no fixed admin credential remains in any supported setup path.
- Queue lease, worker timeout, Python timeout, and reconciliation are ordered and documented. One long job produces one usable result.
- No `completed` response lacks a working owner-authorized download. Retry and deletion failures are visible and recoverable.
- Review page, history page, status badges, and downloaded bytes agree on what is draft, published, verified, or failed.
- Quota is enforced under concurrency; object cleanup survives storage failures.
- Laravel and deterministic Python suites pass; any skips are listed. Real service/format/language-pair tests and representative human meaning/layout review meet accepted criteria.
- Desktop/mobile and keyboard verification covers the named screens; the admin draft preview and long-running translation state make no false claims.
- A deployment runbook covers migrations, admin credential remediation, queue/storage settings, worker restart, rollback, and monitoring. The product owner reviews the vision checkpoints and accepts the remaining quality/risk limits before calling the system production-ready.
