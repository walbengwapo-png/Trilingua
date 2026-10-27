# TriLingua post-audit: remaining work handoff

**Snapshot:** 2026-09-28, `C:\dev\Trilingua` working tree. This is a continuation of [IMPLEMENTATION_PLAN_POST_AUDIT_2026-09-28.md](IMPLEMENTATION_PLAN_POST_AUDIT_2026-09-28.md), not a new product scope. Preserve the extensive existing uncommitted changes. Do not reset, broad-stage, overwrite, or delete unrelated files. No new roles, formats, providers, or cosmetic redesign.

## Where the implementation stands

| Package | Current evidence | Status |
| --- | --- | --- |
| A — authoritative job outcome | `DispatchOutcome`, `DispatchOutcomeClassifier`, intake/worker/reconciler changes and 13 focused tests exist. Safe-environment guard passed. `php artisan test --filter=DispatchOutcomeClassificationTest` passed 13 tests/34 assertions. Full `php artisan test` passed **383**, skipped **1**, 1549 assertions on this snapshot. | **Code present; automated local gate passes.** Two-worker PostgreSQL/real-queue behavior remains a live gate, not proven by SQLite tests. The prior agent's “384/384 green” counts the skipped test as green; the accurate result is 383 passed, 1 skipped. |
| B — publication and audit | `ReviewService` still persists verify/flag and their audit separately; multi-block edits have no enclosing transaction; publish saves the pointer and then logs `publish`. No `published_text` column or migration exists. Owner block endpoint exposes `current_text`. | **Not complete. Start here.** |
| C — downloads and cleanup | Signed-URL failure still falls back to a completed owner route without read-back. Review deletion failures are only logged. Existing cleanup outbox is present for history deletion, but `processPending()` does not recheck live references before deleting an outbox path. | **Not complete.** |
| D — visible state/text history | Text translation catches history failure but returns the result without `saved:false`. Translation page polls every 2 seconds and has no fetch rejection branch before `.finally()`. | **Not complete.** |
| E-A — quality signal | AI reviewer provider exception still returns `score=100.0`. | **Not complete.** |
| E-B — spacing evidence | Prior phase-07 record chose normalized spacing and deterministic tests pass. Its assertion of no layout damage has no representative rendered-document evidence. | **Evidence/decision pending.** Do not silently change the contract. |
| F — measured performance/polish | Admin review still loads all `$documentBlocks` in addition to paginated blocks. No current load/memory measurements were found. | **Measurement pending.** |
| G — release evidence | Earlier phase-07 matrix records live provider, storage, browser, real-file openability and human quality/layout checks as pending. | **Pending after code gates.** |

These are **source observations**, not estimates of frequency. Passing automated tests does not close the listed failure paths. The earlier `phase-00`–`phase-07` records belong to the previous correction plan; they are not records of post-audit Packages B–G.

## Execution order and gates

Work **B → C → D → E-A → F → G in one sequence**, collecting E-B evidence as real document fixtures become available. Run focused tests at each gate, fix regressions, continue without a new planning/permission round. Stop only for a material product decision, unsafe operation on existing data, or unavailable external dependency. Do not run migrations or repairs against an existing database before an inventory, backup, and reversible runbook. Use the test-environment guard before Laravel tests. Keep secrets and user document content out of records.

### B — publication, published text, and audit (highest release risk)

1. Trace all review writers and readers: `ReviewService::{verify,flag,editText,verifyDocument,applyBlockEdits,flagDocument,saveAndRegenerate}`, their controllers, `TranslationBlock`, `TranslationEditLog`, owner/admin block endpoints, and both preview panes. Reproduce audit-insert failure, mid-batch edit failure, and two-admin stale publication.
2. Commit each review state change and its required audit rows in one **short database transaction**. Include block cascades, draft revision updates, pointer update, published revision, and publish audit as appropriate. Keep Python, storage upload/read, and network work outside that transaction. Use row locking or conditional revision/pointer update so a stale publisher receives a clear `409` and cannot erase newer work.
3. Add the minimal durable per-block published-text representation. Populate it on initial successful translation and successful publication. Keep `current_text` as draft and `ai_translated_text` immutable. Final/Saved and owner fallback previews must read published text; editor and explicitly labeled draft preview may read current text. Inventory legacy rows: backfill only where file/content/edit evidence proves equivalence; mark ambiguous rows for reconciliation without altering their downloadable file. Document forward/rollback migration procedure.
4. If candidate upload/read or commit fails, old pointer and audit remain authoritative. If candidate cleanup fails, record a durable cleanup intent. A successful publish requires readable candidate, pointer, revision, published text, and audit to agree. Add failure-injection and competing-admin HTTP tests; compare fallback preview with actual downloaded bytes for representative formats.

**Gate B:** No required audit failure leaves an unaudited state. No partial block batch survives failure. Stale publication returns `409`. Published preview and downloaded file represent the same revision; draft edits stay visibly separate. Legacy ambiguity is reported, not guessed.

### C — truthful completed downloads and durable object cleanup

1. Distinguish signer failure with a readable object, missing object, and storage outage in `TranslationController` status payloads and owner download routes. Preserve authorized fallback only after the object's readability is proven by the chosen backend rule. Do not assert `completed` plus a link known to fail. Cover Supabase and local behavior separately.
2. Reuse the existing outbox for superseded and uncommitted regenerated objects. Record cleanup intent durably, make retry idempotent, and protect paths referenced by surviving histories or recoverable jobs. **Recheck references at deletion time:** the current `StorageCleanupService::processPending()` deletes pending paths without such a check. Handle a reused/referenced path by retaining or cancelling its cleanup intent, never deleting live data. Define the candidate's behavior across crash between upload and database commit; a log-only cleanup attempt is insufficient.
3. Decide and document cleanup ownership for failed jobs with `translated_storage_path` recovery handles. Do not remove files required for an admin Retry or reconciler.

**Gate C:** Every tested completed response has an accessible owner download. Missing output is not labeled complete; outage is distinguishable where possible. Superseded/orphan objects stay discoverable until safe deletion, and shared/recoverable objects survive retry.

### D — honest UI and text partial success

1. Correct review publication messages to describe actual file retention and revision state. Check rendered behavior.
2. Make polling reject/network failures show **status unavailable** while retaining the job ID. Ensure stale responses cannot overwrite a newer submission. Use bounded backoff from 2 seconds toward 15 seconds, resume reliably, and never infer job failure from elapsed time.
3. On text-history insertion failure, return valid translation with explicit `saved:false` and show that it will not appear in Saved Translations or admin review. Return `saved:true` only after a history row exists. Keep notification/metrics failures distinguishable from history failure so a successfully saved item is not mislabeled unsaved. Test both paths and user copy.

**Gate D:** Polling/network loss preserves a recoverable job reference. User/admin copy matches persistence and actual bytes. Unsaved text result cannot look like ordinary saved success.

### E-A and E-B — quality state and spacing contract

1. Trace all Python/PHP score consumers before changing `QualityReview`. Provider failure must produce a typed **unavailable** review state, never `100` or a green/pass appearance, while retaining the translation result. Guard calculations, comparisons, serialization, sorting, metrics, and templates. Give uncalibrated scores neutral triage wording and visual treatment. Test text/document and admin/user surfaces.
2. E-B is an **evidence task**, not permission to rewrite spacing. Compare both splitters and current normalized contract with the earlier approved per-chunk-preservation intent using `0  0`, multi-chunk text, and at least one rendered, layout-sensitive file. If evidence supports the current contract, document it. If it shows a meaningful conflict, present the concrete alternatives and seek a product decision before changing semantics.

**Gate E:** Review outage is visibly unavailable and does not crash consumers. Spacing decision is backed by document evidence or remains explicitly open.

### F — measure, then targeted polish

Profile a representative large document and concurrent uploads on a deployment-shaped runtime: HTML size, page time, PHP/worker memory, download memory, queue wait, file size and block count. Inspect the admin review's full `$documentBlocks` load first; remove it if unused or measured as a bottleneck. Make other changes only at measured bottlenecks. Fix observed focus, clipped action, misleading preview, or narrow-layout failures without redesign.

**Gate F:** Record environment, inputs and measurements; prove stated size/concurrency limits or record a release blocker. No speculative performance layer.

### G — integrated and live acceptance

1. Run safe-environment guard, full Laravel suite, deterministic Python suite excluding import-time benchmark/live modules, Vite build, `view:cache`, and focused failure tests. Report passes, failures, skips, deselections and exact commands separately. The existing CSS test skip needs an asset-backed recheck.
2. In an isolated deployment-shaped PostgreSQL/database-queue environment, exercise two workers, slow job, crash, retry, reconciliation and dispatch/read-back ambiguity. Compare job, queue, history, quota, notification, status and file outcome. Use isolated storage objects for actual Supabase/local upload, signer outage, read, regeneration, delete and outbox retry. Never write to a configured existing database or user objects for these tests.
3. Walk guest/user/admin ownership and review routes in a served browser; test keyboard/screen reader, mobile, network interruption, and long documents. Open representative DOCX/PDF/PPTX/XLSX/ODT output in target applications. Human reviewers judge meaning/layout against thresholds agreed before scoring.

**Final gate:** No High finding remains, and all required operational, browser, storage/provider and human gates have evidence. If a gate cannot run, state **release blocked/unverified** rather than claiming production readiness.

## Handoff output required from the implementing agent

Write `post-audit-package-B.md` through `post-audit-package-G.md` under `trilingua-code/docs/implementation-records/` as work completes. Each record: reproduced problem, affected callers, changed files and behavior, migration/data-repair steps, exact tests/results, rollback concerns, unresolved limits. End with one release report separating automated, live, human-reviewed and unverified evidence. Do not stop between packages merely to ask whether to continue.
