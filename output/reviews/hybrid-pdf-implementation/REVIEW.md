# Hybrid PDF review and cleanup

Historical review of `7e953bf`. The subsequent engineering finish is documented in `FINISH.md`; its protocol and tests supersede the open engineering items below. Real-document acceptance remains HOLD.

**Verdict: real-document image replacement remains HOLD.** Local cleanup is complete on `codex/hybrid-pdf-review-fixes`. Passing fixtures establish implementation behavior, not OCR accuracy or production readiness.

Reviewed phase commits: `4599e6f`, `ac36462`, `3c2ce0b`, `ef4479a`, `7e953bf`; base: `ed50c6b1e3bc9f1e1463a8066e6ca76337f1c763`. All 59 paths in `CHANGED_FILES.txt` were read, including binary font validation; standards/safety and spec reviews were performed separately. Findings were reported before fixes. Source anchors below refer to **7e953bf**, so later cleanup and unrelated dirty hunks can shift working-file lines. Paths are repository-relative; `Model/`, `app/`, `resources/` and `tests/` below are under `trilingua-code/`.

## Checklist verdicts

| # | Area | Verdict and evidence/limits |
|---|---|---|
| 1 | Gate integrity | **BLOCKED.** Normal inventory checks readiness before recognition; negative tests and the ordering mutation enforce this. Calibration/legacy evaluator output is excluded. Runtime still trusts report assertions; genuine issuance/provenance cannot be proved (P1). Supplied reconstruction plans have a separate trust gap (P2). |
| 2 | Destructive safety | **PASS on fixed fixtures after cleanup.** Mask/background/fit checks precede edits; initial writing now stages and validates before replacing output. Tests compare decoded pixels outside masks, retain originals on holds/failures, and inspect fixed saved output for obsolete source images and incremental revisions. Shared resources are held; no global `replace_image` call is used. This is not a guarantee for arbitrary PDFs. |
| 3 | Hold completeness | **PASS for deterministic coverage; calibration pending.** Tests now cover every named hold: sharing/resource aliases, optional layers/backups, forms, clipping, alpha, image/native/vector overlaps, cropbox, stretch/rotation, outlines, uncertain fonts/curved baselines, non-flat backgrounds, low confidence and no-fit. Native/hidden ownership tests remain. No listed condition lacks a unit test; representative real-input evidence is absent. |
| 4 | Accounting | **PASS for scoped content accounting after cleanup.** Held response text matches source; region totals, persisted summary, unknown source-word coverage, filenames, warnings, history/status/review/download remain explicit. Both verification routes reject incomplete documents. Existing `metrics.blocks_translated` records provider work, not successful placement; it must not be interpreted as coverage (`Model/pipeline/document_context.py:70`, `:322`, unchanged by these phases). Unrelated dirty MetricsService/SourceWordCounter work was not altered or approved. |
| 5 | Regeneration | **PASS consistency/reconstruction tests; BLOCKED approval provenance.** Poisoned OCR/provider calls prove zero calls; original/runtime/version/font mismatch and bad-fit tests retain last output. Saved plans contain durable geometry, not request temp paths. PHP tests cover file/plan publication and failed publish retention; historical v1/v2 tests pass. P2 remains. |
| 6 | Resources/processes | **PARTIAL.** Existing 50-page/40 MP limits now check actual sources for render/preserve/regenerate before decode; 60 s OCR, bounded mask decompression, 8 MB accumulated masks, 16 MB plan and 24 MB sidecar/result checks remain. Thread/process serialization and real Windows descendant termination pass. POSIX startup/close races are simulated, not Linux execution. Aggregate RAM and hard-kill scratch cleanup remain (S8/S9). Provider networking is not hard-cancelled. |
| 7 | Security | **PARTIAL.** Service-token policy, approved font IDs/path rejection, JSON/base64/mask bounds and rendered reason escaping are tested. Source/plan hashes establish consistency, not authorization. P1/P2 remain; no adversarial PDF fuzzing or claim of parser safety. |
| 8 | Correctness | **PASS fixed geometry/font cases; real calibration pending.** Conservative transform/crop/rotation holds, original native obstacle identity, word-mask boundaries, line overlap and bounded fit are exercised. Packaged font tests round-trip English/Cebuano/Filipino Latin text, quotes, accents and combining forms. Background/typography thresholds are unchanged and uncalibrated on real material. |
| 9 | Tests | **PASS strengthened offline checks.** 217 Python, 52 PHP/254 assertions, 4 browser; all five final mutations killed. Initial outside-mask mutation exposed a missing negative test, now added alongside real pixel comparisons. Fixtures never establish acceptance. |
| 10 | Maintainability | **PASS local cleanup.** Reused actual-source checks, removed dead imports/duplicate validation/stale comments, and hoisted invariant image work. No broad rewrite, public signature or schema change. |
| 11 | Assets/licensing | **HASH PASS; owner rights review OPEN.** All 8 manifest font hashes and bundled OFL hash match; all sfnt table bounds parse and fsType values are 0. Runtime uses packaged assets with no download path. No legal determination: PyMuPDF AGPL obligations and font embedding/redistribution require owner approval. |

## Findings

Severity is blocker / major / minor. Standards/safety findings use S; spec findings use P. No taste-only findings.

| ID | Severity | Source at reviewed commit | Issue and correction/decision | State |
|---|---|---|---|---|
| P1 | blocker | `Model/document/ocr_extractor.py:80`; `Model/tests/test_ocr_documents.py:86` | Runtime accepts matching hashes plus self-asserted eligibility/contract booleans; the mocked positive fixture lacks genuine corpus/reviewer provenance. Choose trusted report issuance/approval and verification. Do not fabricate a report as a demonstration. | **OPEN** gate/contract decision |
| P2 | blocker | `Model/server.py:782`; `Model/document/regenerator.py:248`; `Model/document/render_plan.py:44` | Authenticated caller-supplied self-consistent plans are not bound to an accepted original extraction. Normal Laravel uses stored sidecars; this is a service-boundary trust gap, not an anonymous exploit. Choose trusted persisted-plan provenance without adding OCR/provider calls to regeneration. | **OPEN** interface/approval decision |
| S1 | major | `Model/document/reconstructor.py:1585`, `:1658`, `:1754` | Filtering held native blocks renumbered survivors against original occupied-box tags; later text could collide with itself after redaction. Preserve original ownership tags. | FIXED A |
| P3 | major | `Model/document/pdf_regions.py:108` | Later paragraph style failure held the image while earlier pending children survived. Roll back all candidates belonging to that image-wide hold. | FIXED A |
| P5 | major | `Model/pipeline/document_pipeline.py:580`, `:610` | Held sidecar text reverted to source but returned translated blocks retained attempted target text. Synchronize DTO source text/passthrough flags. | FIXED A |
| P4 | major | `app/Services/Admin/ReviewService.php:56`, `:165` | Alternate verification action accepted document IDs without the completeness guard. Dispatch documents through guarded verification. Existing error-status mapping remains 500; incomplete verification cannot succeed. | FIXED B |
| S2 | major | `Model/document/pdf_worker.py:73`, `:102`; `Model/document/render_plan.py:28` | Render/preserve/regeneration could bypass actual-template page/pixel checks using a small supplied plan. Apply unchanged limits to actual sources and declared image dimensions before decode. | FIXED C |
| S3 | major | `Model/document/pdf_worker.py:164` | Timeout before POSIX process-group setup could miss termination; process-close errors could retain locks/pipes. Fall back to terminating the owned process and guarantee cleanup in finally blocks. | FIXED C; Linux unrun |
| S5 | major | `Model/document/reconstructor.py:1871`, `:1879` | Saved-output validation ran after overwriting the destination. Stage privately, validate, then replace; reject source/destination aliases. | FIXED D |
| P6 | minor | `resources/views/history.blade.php:120`, `:146` | Incomplete documents displayed an unconditional 100% badge. Show content status when available. | FIXED E |
| P7 | minor | `resources/views/translation.blade.php:528` | Completed/download-unavailable polling omitted incomplete summary/warnings. Preserve them in both download branches. | FIXED E |
| S7 | major | `Model/document/image_reconstructor.py:218` | Zero-area path rectangles missed painted horizontal/vertical vector strokes. Test actual stroke extent and hairlines. | FIXED F |
| S6 | minor | `Model/tests/test_pdf_image_layout.py:35` | Original happy-path assertions survived deletion of outside-mask guards. Add explicit invariant-failure injection while retaining decoded-pixel assertions. | FIXED F |
| S4 | major | `Model/document/image_reconstructor.py:321` | Invariant full-image conversion/median repeated up to 64 times per paragraph. Compute once; conversion-count test failed 8 versus 1 before correction. | FIXED G |
| S8 | major | `Model/document/image_reconstructor.py:135`, `:241`, `:271` | Assembly retains all cleaned RGB arrays; planning also creates full-image float arrays. Fifty 40 MP RGB images alone imply about 6 GB retained, excluding PDF/intermediate storage (estimate, not a measured stress run). Choose bounded assembly/aggregate capacity policy; per-image caps do not bound job RAM. | **OPEN** design/capacity follow-up |
| S9 | minor | `Model/document/pdf_source.py:21`; `Model/document/pdf_worker.py:113`, `:164` | Hard-killing a worker bypasses its TemporaryDirectory cleanup for converted image templates. Parent-owned scratch cleanup is needed for reliable crash recovery. Code-path finding; no live kill/leak reproduction. | **OPEN** scratch ownership follow-up |

## Cleanup commits and verification

Exact handoff Python/PHP/browser suites were run before cleanup and **after each fix commit**. Python outbound socket connections were blocked; browser requests intercepted; providers mocked. No services were started, no acceptance report installed, and no live environment modified. No baseline suite failed. Suites ran in the preserved local working tree; they are not clean-deployment evidence.

| Theme / commit | Change | Python passed | PHP tests / assertions | Browser passed |
|---|---|---:|---:|---:|
| Baseline `7e953bf` | Before review fixes |179|49 /239|2|
| A `1fc3bf6` | Held-region ownership, rollback and returned text |183|49 /239|2|
| B `d8a135d` | All document verification paths guarded |183|50 /247|2|
| C `3205baa` | Actual source limits and timeout cleanup |192|50 /247|2|
| D `ec06a41` | Atomic initial PDF output |195|50 /247|2|
| E `fb4dd61` | Truthful history/download status |195|51 /251|4|
| F `c7efbba` | Hold/security tests and vector stroke correction |216|52 /254|4|
| G `c52d017` | Font-statistic reuse, dead imports, duplicate validation/docs |217|52 /254|4|

Clear bug fixes had failing-then-passing regressions. The corrected POSIX mock tests were rerun against original committed code in a private export; actual Linux behavior is still unverified. Additional hold tests test intended guards, not corpus quality. Raw logs are local `review-A-*` through `review-G-*`; baseline snapshots/exports/logs remain uncommitted.

Mutation checks used isolated source exports, restoring original bytes after each mutation. Gate order, shared-image hold, source hash and partial status were killed initially; outside-mask removal initially survived. After strengthening tests, **all 5 were killed**, including outside-mask removal. See `review-mutations-initial.json` and `review-mutations-final.json`. Application/live gate code was never the mutation surface.

## Scope and preservation

`review-verification.json` records 59 phase-changed paths matching all 59 inventory paths, 8 valid font hashes/license hash, and 557 starting hash entries with **zero unrelated hash mismatches**. All 35 initially dirty tracked files were compared byte-for-byte: 34 are unchanged; the mixed pipeline file contains only the reviewed fixes plus its original `_engine_metrics` dirty function, preserved verbatim. No unrelated Phase A/provider/admin hunks were observed in the five phase diffs or cleanup commits. Existing unrelated source work was not reviewed for correctness or staged.

Live `.env`, acceptance settings/gate state, corpus contract/schema, 95% threshold, 10 pt floor and resource-cap values remain unchanged. Git emitted the pre-existing `.git/worktrees/tril-baseline` metadata cleanup permission warning; commits succeeded and no checkout was removed.

## Pilot blockers and owner decisions

1. **Trust boundaries:** choose approved report issuance and durable plan provenance (P1/P2). These changes were excluded from cleanup because they affect gate/interface decisions.
2. **Actual evidence:** provide rights-cleared representative scans/photos/screenshots, disjoint content splits and independent checked references for English/Cebuano/Filipino. All 9 language/capture scopes remain HOLD; no real corpus/report was created.
3. **Resource policy:** address aggregate memory and crash scratch ownership before a real-input pilot; pick the intended machine capacity and stress workload. Provider transport timeouts currently finish in-flight requests while the job deadline prevents late publication. Acceptable for held offline checks, **not proof of a hard whole-job cancellation guarantee**; decide the required guarantee before pilot use.
4. **Release checks:** actual Linux execution/font parity, owner visual sign-off, PyMuPDF licensing and font embedding/redistribution review. None is established by local fixtures.

## First real-scan manual inspection (only after blockers are resolved)

- Compare aligned original/output at 100% and print size: source glyph removal, anti-alias halos, seams and unchanged held pixels.
- Check columns/tables/headers, image positions, native links/vectors, reading order, missed/duplicate text and protected rules.
- Inspect English/Cebuano/Filipino accents, ñ, combining forms/quotes, 10 pt floor and longer translations for overlap/clipping.
- Follow partial/untranslated status through history, review, downloads and unavailable-download states; verification must stay blocked.
- Edit and regenerate: no OCR/provider work, durable plan/file agreement, rejection retains the last published artifact.

Result: scoped review and seven cleanup themes complete; real-document replacement remains HOLD.
Checked: full handoff suites, five mutations, scope/preservation and packaged asset hashes.
Remaining: P1/P2 trust decisions, real evidence, capacity/crash cleanup, Linux/visual/rights approval.
