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
| S2 | major | `trilingua-code/Model/document/pdf_worker.py:73`, `:102`; `document/render_plan.py:28` | Actual 50-page/40MP checks cover extract/inspect only. A matching v3 plan with a short pages list can regenerate an oversized original. | Reuse existing actual-template checks for strict source-preserving operations, unchanged caps. | Planned |
| S3 | major | `trilingua-code/Model/document/pdf_worker.py:164` | Linux timeout before setsid can miss killpg; a live process.close exception can skip pipe/file/thread lock cleanup. | Terminate the owned process on a missing process group; finally-safe cleanup; startup-race test. | Planned; actual Linux still unrun |
| S4 | major | `trilingua-code/Model/document/image_reconstructor.py:321` | Font estimation scans the entire image up to64 times per paragraph for an invariant median. | Hoist the conversion/median outside both loops; conversion-count regression. | Planned |

### Spec
| ID | Severity | File:line | Concrete problem | Recommendation | State |
|---|---|---|---|---|---|
| P1 | blocker | `trilingua-code/Model/document/ocr_extractor.py:80`; `Model/tests/test_ocr_documents.py:86` | Matching engine/pack hashes and self-asserted report booleans do not prove genuine corpus/reviewer provenance; the unit fixture omits corpus fields and is accepted under its mocked engine. | Owner chooses trusted report issuance/approval and artifact verification. No report will be fabricated to demonstrate this, and gate behavior is not changed. | OPEN: gate/contract decision |
| P2 | blocker | `trilingua-code/Model/server.py:782`; `document/regenerator.py:248`; `document/render_plan.py:44` | An authenticated caller supplies a self-consistent pixel plan; hashes prove consistency, not that the plan originated from accepted OCR. Normal Laravel uses stored sidecars, so this is a service-boundary provenance gap, not an anonymous exploit. | Owner chooses trusted persisted-plan/approval provenance while keeping regeneration free of OCR/provider calls. | OPEN: schema/interface decision |
| P3 | major | `trilingua-code/Model/document/pdf_regions.py:108` | If a later paragraph's style fails, the parent image becomes held but earlier pending children/blocks survive. Editing them changes a held parent. | Roll back that image's candidate children on the image-wide hold; deterministic failing test. | FIXED theme A |
| P4 | major | `trilingua-code/app/Services/Admin/ReviewService.php:56`, `:165` | The text verification action still accepts a document ID and bypasses the document-only completeness guard. | Route document verification through the shared guarded document action; HTTP negative test. | Planned |
| P5 | major | `trilingua-code/Model/pipeline/document_pipeline.py:580`, `:610` | Sidecar held entries restore source text, but response.translated_blocks still returns attempted target text. | Synchronize held DTO text/flags without changing list/index shape; regression test. | FIXED theme A |

No taste-only code-smell findings. Unused imports and a duplicated checked-ID validation may be cleaned only after full caller/source reads. No gate/95%/10pt/resource-cap/schema/interface changes are authorized.

## Work still underway
Checklist verdicts, complete hold-test matrix, five mutation spot-checks, per-theme commits, after-commit suite results, leak/preservation audit, first-scan manual checklist and final owner decisions will be appended as work finishes. All real language/capture categories remain on HOLD.

## Cleanup theme A: held-region correctness
Four new cases failed against the original code (native survivor identity, late style hold, missing font hold, and held DTO text). All10 classification tests pass after local fixes. No gate, threshold, public field or sidecar shape changed; operational attempt counters remain separate from placed-region counts. Commit follows; full suites are rerun after it.
