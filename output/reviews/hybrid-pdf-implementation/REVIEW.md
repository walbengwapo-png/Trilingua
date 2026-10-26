# Hybrid PDF review and cleanup

What this change does: inventories native and raster regions, preserves held content, translates eligible content in place, and saves a reusable reconstruction plan. This review covers only the five phase commits ending at `7e953bf`, from base `ed50c6b`, scoped by `CHANGED_FILES.txt`.

Branch: `codex/hybrid-pdf-review-fixes`. No application fixes yet. **Verdict: HOLD for a real-document pilot.**

## Baseline
179 Python tests passed; 49 PHP tests / 239 assertions passed; 2 browser tests passed. The same handoff commands were used, with outbound Python connections blocked and browser requests intercepted. Private initial dirty snapshots include byte copies and hashes; .env is hash-only. No service, acceptance setting or live environment change is permitted.

## Findings reported before cleanup

Line anchors below refer to committed `7e953bf`, not unrelated dirty offsets. Standards/safety and spec findings are kept separate.

### Standards / safety
| ID | Severity | File:line | Concrete problem | Smallest correction | State |
|---|---|---|---|---|---|
| S1 | major | `trilingua-code/Model/document/reconstructor.py:1585`, `:1658`, `:1754` | Holding the first native block renumbers later survivors while occupied boxes keep old tags; a later fitting block collides with itself after redaction. | Preserve each surviving block's original page-local obstacle tag; hold-first/fit-second regression. | FIXED theme A |
| S2 | major | `trilingua-code/Model/document/pdf_worker.py:73`, `:102`; `document/render_plan.py:28` | Actual 50-page/40MP checks cover extract/inspect only. A matching v3 plan with a short pages list can regenerate an oversized original. | Reuse existing actual-template checks for strict source-preserving operations, unchanged caps. | FIXED theme C |
| S3 | major | `trilingua-code/Model/document/pdf_worker.py:164` | Linux timeout before setsid can miss killpg; a live process.close exception can skip pipe/file/thread lock cleanup. | Terminate the owned process on a missing process group; finally-safe cleanup; startup-race test. | FIXED theme C; real Linux unrun |
| S4 | major | `trilingua-code/Model/document/image_reconstructor.py:321` | Font estimation scans the entire image up to64 times per paragraph for an invariant median. | Hoist the conversion/median outside both loops; conversion-count regression. | Planned |

### Spec
| ID | Severity | File:line | Concrete problem | Recommendation | State |
|---|---|---|---|---|---|
| P1 | blocker | `trilingua-code/Model/document/ocr_extractor.py:80`; `Model/tests/test_ocr_documents.py:86` | Matching engine/pack hashes and self-asserted report booleans do not prove genuine corpus/reviewer provenance; the unit fixture omits corpus fields and is accepted under its mocked engine. | Owner chooses trusted report issuance/approval and artifact verification. No report will be fabricated to demonstrate this, and gate behavior is not changed. | OPEN: gate/contract decision |
| P2 | blocker | `trilingua-code/Model/server.py:782`; `document/regenerator.py:248`; `document/render_plan.py:44` | An authenticated caller supplies a self-consistent pixel plan; hashes prove consistency, not that the plan originated from accepted OCR. Normal Laravel uses stored sidecars, so this is a service-boundary provenance gap, not an anonymous exploit. | Owner chooses trusted persisted-plan/approval provenance while keeping regeneration free of OCR/provider calls. | OPEN: schema/interface decision |
| P3 | major | `trilingua-code/Model/document/pdf_regions.py:108` | If a later paragraph's style fails, the parent image becomes held but earlier pending children/blocks survive. Editing them changes a held parent. | Roll back that image's candidate children on the image-wide hold; deterministic failing test. | FIXED theme A |
| P4 | major | `trilingua-code/app/Services/Admin/ReviewService.php:56`, `:165` | The text verification action still accepts a document ID and bypasses the document-only completeness guard. | Route document verification through the shared guarded document action; HTTP negative test. | FIXED theme B |
| P5 | major | `trilingua-code/Model/pipeline/document_pipeline.py:580`, `:610` | Sidecar held entries restore source text, but response.translated_blocks still returns attempted target text. | Synchronize held DTO text/flags without changing list/index shape; regression test. | FIXED theme A |

No taste-only code-smell findings. Unused imports and a duplicated checked-ID validation may be cleaned only after full caller/source reads. No gate/95%/10pt/resource-cap/schema/interface changes are authorized.

## Work still underway
Checklist verdicts, complete hold-test matrix, five mutation spot-checks, per-theme commits, after-commit suite results, leak/preservation audit, first-scan manual checklist and final owner decisions will be appended as work finishes. All real language/capture categories remain on HOLD.

## Cleanup theme A: held-region correctness
Four new cases failed against the original code (native survivor identity, late style hold, missing font hold, and held DTO text). All10 classification tests pass after local fixes. No gate, threshold, public field or sidecar shape changed; operational attempt counters remain separate from placed-region counts. Commit follows; full suites are rerun after it.

## Post-commit suite results
| Stage / commit | Python | PHP | Browser |
|---|---:|---:|---:|
| Baseline 7e953bf | 179 passed |49 /239 assertions|2 passed|
| A: 1fc3bf6 |183 passed (+4)|49 /239 assertions|2 passed|
| B: d8a135d |183 passed|50 /247 assertions (+1)|2 passed|
| C: 3205baa |192 passed (+9)|50 /247 assertions|2 passed|
| D: ec06a41 |195 passed (+3)|50 /247 assertions|2 passed|
| E: fb4dd61 |195 passed|51 /251 assertions (+1)|4 passed (+2)|

## Cleanup theme B: alternate verification action
The new HTTP regression returned200 before the fix. Generic verification now dispatches document rows to verifyDocument, preserving its completeness/draft checks and transaction/audit behavior. Focused PHP suite:4 tests/28 assertions passed. Existing text-controller exception status mapping remains unchanged (500); the route can no longer return successful verification or clear partial/untranslated state. Full suites follow this theme commit.

## Cleanup theme C: actual source limits and worker cleanup
Six render/preserve/regeneration cases exceeded the existing page/pixel cap and failed before the fix; two corrected POSIX startup/close-failure cases also failed on the original committed worker in an isolated export. A ninth metadata test reached rendering with a declared50MP image; the new guard now rejects it before any image-info decode. All22 regeneration/resource tests pass. The initial POSIX test harness needed a mocked SIGKILL constant on Windows; the corrected tests were rerun against original code and failed for the intended missing termination.

Actual-template limits now live in the shared template wrapper and apply before strict copying/rendering, including source-image metadata checks. Historical valid reflow layouts remain unchanged; over-limit legacy PDF sources are rejected in the worker using the same existing caps. Process group startup races fall back to terminating the owned Process; cleanup releases pipes/file/thread locks even when process closure raises. No real Linux signals were sent by the simulated race tests.

## Mutation spot-check, first pass
Mutations run only in a disposable source export, restored byte-for-byte after each. Gate order, shared image hold, source hash and partial-status mutations were killed. Removing the outside-mask checks survived the original happy-path pixel tests. Add invariant-failure injection while retaining the actual unchanged-pixel assertions, then rerun all five. No application gate or live file was mutated.

## Additional reported findings (before cleanup)
- S5 (major), `trilingua-code/Model/document/reconstructor.py:1872`: the new image validation runs after saving directly to the caller's destination. A saved-output validation failure can overwrite an earlier output or leave an erased invalid artifact for non-API callers. The API's private temp-directory cleanup prevents publication through Laravel, but does not make this writer atomic. Proposed small fix: a private validated staging file, then replace; preserve the public signature and reject aliases of the original source.
- P6 (minor), `trilingua-code/resources/views/history.blade.php:120`, `:146`: an untranslated/partial document still gets the unconditional100% document badge. Proposed conditional content-status badge and rendered-view assertion.
- P7 (minor), `trilingua-code/resources/views/translation.blade.php:528`: completed/download-unavailable polling ignores summary/warnings and says Translation complete. Proposed preservation of incomplete status in this branch and browser regression.
- S6 (minor, test gap), `trilingua-code/Model/tests/test_pdf_image_layout.py:35`: the initial outside-mask guard mutation survived. Add a negative invariant-failure test in addition to real output pixel comparisons; rerun all five mutations in the disposable export.

## Cleanup theme D: atomic first-render output
Both injected saved-image validation failures failed on the original writer: a new invalid output remained and an existing destination was overwritten. The public writer now stages privately, validates fully, then replaces the destination. Its call signature and render-plan shape are unchanged; same-file source destinations are rejected. All17 image-layout tests pass, including preservation of old/no output on failure and immutable original-source protection. Full suites follow this commit.

## Cleanup theme E: complete status presentation
The History regression found an unconditional100% badge; two browser cases found missing partial/untranslated status while a download is unavailable. New content-aware badges and completed-state warnings now remain explicit in both download branches. Focused PHP and four browser cases pass; full suites follow this theme commit. Stored/API state and legacy rows without the new summary are unchanged.

## Additional hold/test audit
- S7 (major), `trilingua-code/Model/document/image_reconstructor.py:219` (original drawing-overlap check): horizontal/vertical vector strokes have zero-area path rectangles, so the existing area-only overlap check misses a line painted across an image. The intended drawing-overlap hold needs actual stroke extent (including hairlines), without changing acceptance thresholds. Add a failing geometry test before correcting it.
- Missing explicit hold tests at baseline: optional layers, embedded backups, forms, resource-only sharing, cropbox, nonuniform scaling, image rotation, native/vector overlap, outlines, uncertain font shape, curved baselines, and failure of the outside-mask invariant. Windows job assignment was exercised but descendant termination had no dedicated assertion. Fixed fixtures will cover these; they are not OCR/corpus evidence.

## Cleanup theme F: hold, security and mutation coverage
New deterministic tests cover resource-only aliases, optional layers, embedded backups, forms, cropbox/nonuniform scaling/image rotation, native/vector/clipped-bbox overlap, outlines, uncertain font shape, curved baselines, unapproved font IDs, overlapping masks/targets, and failed outside-mask invariants. The new vector-line case failed before its local geometry correction: actual stroke bounds and zero-area hairlines now trigger the already-intended drawing-overlap hold. No confidence/fit/acceptance threshold changed.

Actual Windows containment now has an owned worker/descendant termination test; it opens the exact child handle before terminating its own worker, avoiding PID reuse and touching no application jobs. Added plan/sidecar cap and review-HTML escaping checks; saved PDF inspection checks the absence of obsolete source image objects and a prior incremental revision chain in fixed fixtures. These are geometry/security tests, not representative scan/photo evidence.

All five final isolated mutations were killed: gate ordering, shared images, outside-mask guards, original hash, partial status. Every mutated export file was restored byte-for-byte; application code/config was never used as the mutation surface. The outside-mask negative tests use explicit invariant-failure injection in addition to actual decoded-pixel comparisons. Full suites follow this commit.

## Cleanup theme G: invariant font sampling and dead imports
The new conversion-count regression failed before the fix (8 full-image conversions versus 1). The image median is now computed once per paragraph instead of once per font/word pair; source glyph scoring and thresholds are unchanged. Removed unused imports, a duplicated case-ID validation already performed by the corpus validator, and stale runner documentation. All45 focused tests pass. Theme F full results:216 Python,52 PHP/254 assertions,4 browser. Full suites follow the theme G commit.
