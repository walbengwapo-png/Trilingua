# TriLingua post-implementation integrity plan

**Status:** Implementation handoff for review and execution. This is a follow-up to `codex/IMPLEMENTATION_PLAN_EXISTING_SYSTEM_2026-09-28.md`, not a replacement for its product scope or release definition.  
**Baseline:** Current working tree in `C:\dev\Trilingua` on 2026-09-28. It contains substantial uncommitted work. Preserve unrelated changes and inspect the current diff before editing.  
**Objective:** Close the remaining contradictions in the existing user and admin workflows: accepted work must have a truthful durable state; publication, audit, and downloaded bytes must agree; removed or superseded objects must remain traceable until cleanup; visible status must describe what the system actually knows.  
**Scope:** Existing authentication and two roles, text/document translation, job intake/retry/reconciliation, history/download, admin review, storage cleanup, and the UI needed to represent those flows accurately. No new roles, providers, formats, scheduling, offline mode, redesign, or speculative abstraction.  
**Release verdict at baseline:** Not production-ready. The deterministic suites pass, but the failure paths below remain open and live-service/human validation is pending.

**Previously approved agent handoff to preserve:** The user approved a more specific implementation sequence after the original plan. It required non-blocking text translation with an explicit `saved:false` result on history failure; signed-URL fallback only when the object is readable; a published-text/legacy reconciliation contract for document previews; optimistic protection against concurrent admin publication; a neutral unavailable quality-review state instead of score `100`; and polling backoff. The later phase records must be checked against those commitments. This document restates the relevant ones so an implementing agent need not rely on an old chat attachment.

## 1. Evidence and operating rules

- Independent safe-environment guard: `php tests/assert-safe-test-env.php` passed (`APP_ENV=testing`, SQLite `:memory:`, no cached config).
- Independent `php artisan test`: **366 passed, 1 skipped (1506 assertions)**. The skip is the compiled-CSS `AuthCssRenderingTest`; its reason should be rechecked after building the production asset, not silently treated as a pass.
- Independent deterministic Python command from `trilingua-code/Model`: `python -m pytest tests -q --ignore=tests/test_concurrency_benchmark.py --ignore=tests/test_reference_gemini_workflow.py -m "not slow and not golden and not font_regression" -p no:cacheprovider` → **350 passed, 35 deselected**.
- `node --check resources/js/review-document.js` passed. The implementing agent's records report a successful Vite build; this audit did not rerun the asset build or perform a served-browser walkthrough.
- Current `phase-00` through `phase-07` records live in `trilingua-code/docs/implementation-records/`. Those records show what was attempted and tested; they do not override the behavior of the current source.
- Treat code findings below as source-confirmed paths with unproven frequency. Reproduce each with an isolated failure-injection or controlled concurrency test before changing the code. Do not report a test-mocked storage path as a real Supabase result.
- Work in **one sequence**. Finish each gate with focused checks, then run integrated tests and polish once at the end. Stop only for a material product decision or unavailable external dependency. Record exact commands, outcomes, and unresolved limits.
- Keep file content, credentials, tokens, and personal translation text out of logs and handoff records. Before applying any migration or repair to an existing database, inventory affected rows and write a reversible runbook.

## 2. Findings ordered by release risk

| ID | Risk | Problem and source evidence | Consequence |
| --- | --- | --- | --- |
| F1 | High | `TranslateDocumentJob::handle` calls `TranslationJob::markCompleted(...)` but ignores its boolean result, then writes a completed cache result and sends completion notifications (`app/Jobs/TranslateDocumentJob.php`, around lines 265–275). The model deliberately refuses a completion transition after another actor has made the row terminal. | A late worker can create history and tell the user/admin that work completed while the authoritative job remains failed or cancelled. |
| F2 | High | `Admin/JobController::retry` calls `markQueued(recovered: true)` before `dispatch($job)`; its catch path reports retry failure without restoring or reconciling the row. Upload and retranslation also mark rows queued before dispatch (`TranslationController::handleDocument`, `DocumentsController::retranslate`). | A queue insertion failure can leave a job displayed as queued even though no worker can receive it. The intake response and quota accounting may then disagree with actual work. |
| F3 | High | `ReviewService::saveAndRegenerate` saves the new file pointer and `published_revision`, then appends the `publish` audit entry outside that write's failure boundary (`app/Services/Admin/ReviewService.php`, around lines 436–454). Verify, flag, text edit, and multi-block draft edit also persist state/audit in separate writes. | An audit failure can return an error after publication succeeded, or leave review state and its audit trail inconsistent. Partial multi-block edits are possible if a later write fails. |
| F4 | High | On signed-URL generation failure, `TranslationController::buildHistoryCompletedPayload` returns an authenticated `/history/{id}/file` URL without checking object readability (around lines 590–620). `HistoryController::showFile` returns 404 if that object is missing. | `status` can say `completed` and offer a URL that cannot deliver bytes, violating the central completion gate. A signer outage and a missing object require different handling. |
| F5 | Medium | Review publication deletes the superseded object best-effort and merely logs a failure; failed deletion of an uncommitted candidate is also only logged (`ReviewService`, around lines 454–467 and 534–543). The history-deletion outbox is not used for these paths. | Objects without a live history pointer can remain in storage without a durable retry record. |
| F6 | Medium | The publish success response says the previous file is still available until another action (`DocumentReviewController`, around line 161), while `ReviewService` immediately attempts to delete it. The translation-page poller has no rejection handler for a failed `fetch` (`resources/views/translation.blade.php`, around lines 450–516). | Reviewers receive false retention information; network loss produces an unhandled promise rejection rather than an honest status-unavailable state. |
| F7 | Medium | Text translation catches history/notification/metrics persistence failure and still returns the translation response (`TranslationController::translate`, around lines 128–159) with no saved/unsaved signal. The approved handoff explicitly chose non-blocking translation with `saved:false` and an unsaved-result warning on history failure. | The user can see a successful translation that never appears in Saved Translations or admin review; the agreed user contract was not implemented. |
| F8 | Measure before optimization | Admin review paginates the editor but also loads all blocks into `$documentBlocks` (`Admin/ReviewController::show`, around lines 145–187); file paths read whole bytes into PHP memory, and the Python response is base64 JSON (`TranslationManager::translateDocument`). | Large documents may strain page load time and PHP memory. This is a measurable risk, not a proven performance failure; do not add virtualization or streaming machinery without profiling. |
| F9 | High | Document blocks expose `current_text` through owner/admin fallback endpoints and whole-document preview (`HistoryController::blocks`, `Admin/ReviewController::blocks/show`), although `current_text` can be an unpublished draft. The current migration adds only `draft_revision`/`published_revision`; it does not persist the published text of each block or reconcile legacy edited records. | A preview labeled Final/Saved can show draft wording that is absent from the actual downloadable file. A revision number alone cannot reconstruct the old published text after a block is edited. This misses the approved draft/publication contract. |
| F10 | Medium | `AIQualityReviewer.review` returns `QualityReview(score=100.0, summary="AI review unavailable...")` on provider failure (`Model/validators/ai_quality_reviewer.py`, around lines 313–319). Low/medium/high red–amber–green dots remain in `resources/css/views/admin.css`. | Review failure can appear as a perfect score, and threshold colors imply a pass/fail judgment despite no human calibration. The approved handoff required an explicit unavailable state and neutral presentation. |
| F11 | Validate contract | Both chunk splitters now normalize interior whitespace on short paths, while the approved handoff specified preserving interior whitespace per chunk and normalizing only aggregation. The deterministic test is green, but layout-sensitive output has not been checked with real files. | Test success alone does not establish that spacing changes preserve document fidelity. This is a plan-alignment and live-evidence gap, not proof of visible damage. |

## 3. Implementation sequence and acceptance gates

### Package A — Restore one authoritative job outcome (F1, F2)

**Trace first:** `TranslationController::handleDocument`, `DocumentsController::retranslate`, `Admin/JobController::retry`, `TranslationJob` transition helpers, `TranslateDocumentJob::handle`, `ReconcileTranslations`, queue configuration, cache writes, history insertion, and completion/failure notifications. Check the actual database queue driver's behavior when `dispatch()` throws and whether the enqueue outcome can be ambiguous.

**Required correction:**

1. Reproduce (a) enqueue failure after a row becomes queued; (b) completion attempted after a reconciler or other actor made the row terminal. Include upload, retranslation, and admin retry callers. Use the smallest shared transition/dispatch correction compatible with the existing state machine. Avoid a new queue framework.
2. Do not publish a completed cache state or completion notification when `markCompleted` refuses the transition. Resolve the authoritative row and handle any newly written history/output so users do not see contradictory states or duplicate visible results. Preserve valid data; cleanup must be durable if it cannot finish immediately.
3. A failed dispatch must not leave an indefinitely queued, undeliverable job. Make the result and recoverability truthful, retain a durable original where retry is promised, and make quota handling match the agreed acceptance boundary. Do not delete scratch input that a possibly dispatched worker still needs without first resolving that ambiguity.
4. Cover repeat admin Retry and competing workers. A state transition must be conditional in the database, not just checked on a stale model instance.

**Gate A:** For success, enqueue failure, timeout/reconciliation, retry, and late-worker completion, `translation_jobs`, queue row, history, cache/status response, notifications, quota, and file availability describe the same outcome. A worker cannot announce success after a refused completion transition. No stranded `queued` row claims that undelivered work is running.

### Package B — Make published content, review state, and audit consistent (F3, F9)

**Trace first:** `ReviewService::{verify,flag,editText,verifyDocument,applyBlockEdits,flagDocument,saveAndRegenerate}`, `DocumentReviewController`, `TextReviewController`, `TranslationEditLog`, block revision columns, `HistoryController::blocks`, `Admin/ReviewController::{show,blocks}`, and `document-preview.js`. Keep network/storage/Python calls **outside** short database transactions.

**Required correction:**

1. Reproduce an audit insert failure after the publish pointer would otherwise move; prove the current response and stored pointer disagree. Also inject failure in the middle of a multi-block edit and in a verify/flag cascade.
2. Commit each logically indivisible database change with its required audit row(s). For publication, the candidate object must be uploaded and read back before the short database commit; on a failed commit, preserve the old published pointer and enqueue cleanup for the uncommitted candidate if immediate removal fails.
3. Prevent two admins from silently publishing a stale snapshot over a newer draft or pointer. Use the existing revision markers and a conditional write/conflict response if sufficient; do not build a general document-versioning feature. Define what the loser sees and what happens to its uploaded candidate.
4. Keep `ai_translated_text` immutable. Preserve the previous published file until the new pointer and audit are confirmed. Ensure `Verify` refers only to the published revision and never silently approves an unpublished draft.
5. Reproduce a Save Edit followed by owner/admin fallback preview and compare its displayed text with the **actual downloaded file**. Implement the approved published-content contract with the smallest durable representation that can answer both questions: current draft text and text in the published file. A revision counter alone is insufficient. Every endpoint or pane labeled Final/Saved must render published text; the editor and explicitly labeled page-draft pane may render drafts.
6. For legacy documents, do not infer published text from edited `current_text`. Inventory edit evidence and backfill only unambiguous rows; flag ambiguous rows for reconciliation while leaving their last downloadable file intact. Prepare a reversible migration/runbook before touching an existing database. Validate initial translation, Save Edit, publish, repeat publish, and legacy edited rows.

**Gate B:** A failed publish response leaves the old file authoritative; a successful response has a readable new file and required audit entry. A required audit failure cannot create unlogged verified/flagged/edited/published state. A competing admin receives an explicit conflict or sees the latest state; no edits disappear silently. Owner/admin Final previews, fallback block previews, review status, and downloaded bytes represent the same published version; drafts remain visibly separate.

### Package C — Make completed downloads and storage cleanup truthful (F4, F5)

**Trace first:** `TranslationController::{status,buildCompletedPayload,buildHistoryCompletedPayload}`, `HistoryController::{showFile,redownload}`, `StorageService`, `ReviewService` cleanup, `StorageCleanupService`, and the outbox migration. Confirm how Supabase reports missing objects versus signer/network failure; do not infer this from mocks alone.

**Required correction:**

1. Test a valid object with signer outage, a missing object, and a storage read outage. Keep owner-authorized routing, but return `completed` only when the file is known retrievable under the system's chosen evidence rule. Expose temporary unavailability distinctly from permanently missing output where the backend can establish that distinction.
2. Reuse the existing durable cleanup mechanism for superseded or uncommitted regenerated objects whose immediate deletion fails. Protect any path still referenced by a surviving history row. Make retry idempotent, and verify it after simulated process interruption.
3. Check orphan paths recorded on failed document jobs: `translated_storage_path` is a recovery handle, but a job that cannot complete must not leave it permanently unowned without an operator-visible cleanup decision.

**Gate C:** Every `completed` response has a working owner-authorized download in the tested backend; missing output does not masquerade as success. Every storage object intentionally removed from the published path remains discoverable until deletion succeeds. Shared originals remain intact.

### Package D — Correct visible state and implement the agreed text partial-success contract (F6, F7)

**Required correction:**

1. Change the publish success and failure messages to match actual retention and revision behavior. Check the rendered admin review page, not only response JSON.
2. Give the translation-page poller a rejection path for network failure, preserving the job ID and showing status unavailable. Ensure an old in-flight response cannot clear or overwrite a newer submitted job after navigation, visibility changes, or a new submission. Back off the polling interval from 2 seconds toward a bounded 15-second cap during long jobs, as the approved handoff specified; do not reintroduce elapsed-time-based failure. While no history row exists, retain a job-specific way to check progress rather than relying solely on a generic Saved Translations link.
3. Implement the **already approved** text-history contract: keep a valid translated result when history insertion fails, return an explicit `saved:false` marker, and state in the UI that it will not appear in Saved Translations or admin review. Do not mark it saved or notify an admin of a nonexistent record. Cover ordinary saved success and injected history failure with focused tests.

**Gate D:** Reviewer/user copy matches stored state and downloadable bytes. Network interruption never asserts failure or silently loses the recoverable job ID. A text translation whose history write fails cannot appear as an ordinary saved success.

### Package E — Resolve quality-signal and spacing contract gaps (F10, F11)

1. Reproduce AI-review provider failure. Replace the fabricated perfect score with a typed unavailable state while leaving a valid translation usable. Trace every score consumer before changing the type: `QualityReview.passed`, `needs_retranslation`, block quality recording, API serialization, pipeline comparisons, metrics, admin/user templates, and tests. Guard calculations and sorting so `None` cannot crash them.
2. Remove pass/fail-looking threshold colors from uncalibrated score surfaces or otherwise make their triage-only meaning unmistakable under the approved neutral presentation. Show unavailable as unavailable, not `100` or a green dot. Verify text and document routes plus admin/user displays.
3. Compare both current splitters with the approved spacing contract: preserve interior whitespace inside chunks; allow aggregation to normalize for semantic equality. Check callers and real layout-sensitive files before deciding whether to restore that behavior or document a justified deviation for product review. Add focused regressions for `'0  0'`, multi-chunk text, and at least one rendered document case.

**Gate E:** Review outage never creates a perfect or verified-looking score; translation remains available; every consumer handles unavailable review. Spacing behavior is documented, tested, and checked against document fidelity, with any departure from the approved contract explicitly reviewed.

### Package F — Measured performance and final polish (F8)

1. Profile the served app with a representative large document and concurrent uploads: admin review HTML size/render time/memory, file download memory, worker memory, and queue wait. Record file size, block count, environment, and measurements without logging content.
2. Only if a limit is actually breached, make the smallest change at the measured bottleneck. Candidates to evaluate are lazy-loading the admin whole-document blocks and reducing full-byte copies; neither is automatically required.
3. Keep the existing visual language. Fix any observed clipped action, lost focus, misleading preview, or unusable narrow layout. Do not spend this phase on cosmetic redesign.

**Gate F:** Stated size/concurrency limits work on the deployment-shaped runtime or the limitation is documented as a release blocker. No new unmeasured dependency or broad rewrite is introduced.

### Package G — Production evidence, after code gates

Run the integrated Laravel and deterministic Python suites, asset build, view compilation, and targeted failure-injection checks. Then use a served environment with deployment-shaped queue, PostgreSQL, storage, and Python provider configuration for:

- Guest, user, and admin route/ownership matrix; another user's job, file, notification, and review URL remain inaccessible.
- Real queue two-worker slow-job, crash, retry, reconciler, and dispatch-failure scenarios. Compare every authoritative state and user-visible result.
- Real Supabase and local-fallback upload, read, signed link, authenticated file route, regeneration, delete, and scheduled outbox retry.
- Keyboard-only and screen-reader review controls; mobile translation/history/review; network interruption; long document preview and download.
- Representative files for supported formats and language pairs. Open generated DOCX/PDF/PPTX/XLSX/ODT in target applications; have a human judge meaning and layout against **pre-agreed** thresholds. Do not equate an AI-review signal with translation accuracy.

The benchmark module `Model/tests/test_concurrency_benchmark.py` rewrites `Model/tests/concurrency_report.json` at import/collection time. Keep it excluded from normal deterministic CI; run it only in a controlled benchmark workspace with its artifact accounted for. Record every skip/deselection separately from passes.

**Final gate:** No High finding remains. Tests and live checks are reported with exact commands, environment, pass/fail/skip counts, and artifact/openability results. Production readiness may be claimed only after code integrity, operational, browser, storage/provider, and human quality/layout gates have passed. Missing live evidence remains an explicit release blocker, even with green mocked suites.

## 4. Handoff record format

For each package, write a short implementation record under `trilingua-code/docs/implementation-records/` containing: problem reproduced; root cause and all affected callers; files changed; behavior before/after; tests and exact results; rollback or data-repair notes if relevant; remaining uncertainty. At the end, provide one concise release report that separates **verified automated**, **verified live**, **human-reviewed**, and **unverified** claims. Do not call a static inspection a browser test or a mocked storage call a Supabase integration test.
