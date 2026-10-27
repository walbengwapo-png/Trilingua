# Hybrid OCR functional corrections - 26 October 2026

Status: engineering corrections implemented; production OCR replacement remains HOLD. Branch `codex/hybrid-ocr-functional`, base `6e1f131`; implementation commit `9d8d3af`. No production acceptance configuration was changed.

## Retained changes

| Boundary | Change |
|---|---|
| `Model/document/ocr_geometry.py` | Standard-library hOCR parser retains paragraph/line IDs, word boxes/confidence, baseline slope/intercept and ascender/descender metrics. Validates finite geometry. Baseline checks distinguish ordinary descenders from skew/curvature. Missing actual OCR baselines hold. |
| `Model/document/ocr_extractor.py` | Production and evaluator share hOCR extraction. One uncertain-paragraph retry: 32px crop margin, minimum200px padding, 4/3 Lanczos upscale, no binarization. Candidate text must agree after NFC/whitespace normalization, preserving case/punctuation/diacritics, with every word >=80. Failure keeps the original uncertain words. SETTINGS v3 invalidates earlier evidence. |
| `Model/document/pixel_budget.py`, `pdf_regions.py` | Retry intermediates consume the remaining shared120MP job allowance, retain40MP per-image cap, and cannot extend the60-second OCR allowance or the parent job deadline. A low individual word holds before provider translation even if paragraph mean exceeds80. |
| `Model/document/image_reconstructor.py` | Short image-strip letter stems no longer masquerade as long vertical rules. Long rules, unsafe background, neighbor overlap, no-fit and actual skew/curvature still hold. Font comparison trims background padding before comparing glyph shapes. Renderer algorithm v2. |
| `Model/document/extractor.py` | Uses individual line edges/centers before union-box position for native alignment. The supplied PDF's three falsely centered body paragraphs now extract as left aligned. Alignment and family/weight remain estimates, not recovery of original authoring metadata. |
| `Model/pipeline/document_pipeline.py`, `document/regenerator.py` | Shared status logic counts unchanged provider text as passthrough, without locking that content against administrator edits. Regeneration recounts translated/passthrough regions after an edit. Held content remains held. |
| `Model/tools/ocr_kit/README.md` | Corrected a malformed reference-check command and documented policy/version compatibility. |

The 95% word-accuracy acceptance gate, word-confidence80 minimum,10pt readability floor, flat-background scope, resource caps, signed report/plan validation and no-OCR/no-provider regeneration contract remain enforced. No new dependency, cloud OCR service, package install, environment-file edit or service restart was used. Pre-existing Phase A/provider/admin changes were preserved.

Algorithm v2 rejects earlier v3 signed render plans with algorithm v1. Downloaded PDFs remain readable. A fresh translation is required for those old plans; they are not silently re-signed. Legacy v1/v2 sidecar behavior was not replaced.

## Evidence and limits

- Baseline:254 Python tests;52 PHP tests/255 assertions;4 browser checks, all passed.
- Final code checks:280 Python tests (26 added),52 PHP tests/255 assertions and4 browser checks passed. Python checks denied outbound socket connections. Logs are under `output/reviews/ocr-functional-implementation/`.
- Actual input SHA256:`df09eaad8e681a4c5792081db117b38d238f06a9bdadf7c8241b7b0c0b76e34f`.
- Diagnostic-only, no-provider recognition/source-text reconstruction planning succeeded for both real dialogue panels. Page1 accepted its agreeing retry with minimum confidence85; page2 needed no retry, minimum83. Previously both source-text probes falsely held at the curved-baseline check; fixing that exposed and then corrected the letter-stem/rule false positive. These are confidence readings and planning probes, **not checked word accuracy, actual translated-image replacement or acceptance evidence**.
- Ordinary cached service rerun: HTTP200,5 translated/1 passthrough/4 held, no HTTP provider calls because6 blocks hit the existing cache. Image pixels/raw streams and page geometry unchanged. Source alignment corrected. Evidence:`output/pdf/lion-mouse-functional-rerun-2026-10-26/`.
- A fresh cache-disabled service rerun made one real configured GPTOSS POST `/api/chat` (HTTP200,29.718seconds), total63.906seconds. It also returned5 translated/1 passthrough/4 held. Both pages were rendered with Poppler and visually inspected. All image bytes/pixels and page geometry remained unchanged. Import-time unrelated warmup connections were blocked; no external server was started. Evidence:`output/pdf/lion-mouse-functional-live-2026-10-26/`.
- That fresh run temporarily tested generic prompt clarifications. It still returned incorrect content, including `Ang Leona ug ang Mice` and `Ang kalooy dili gayud mapuslan.` for `A kindness is never wasted.` The latter appears to reverse the intended meaning. This is an engineering observation, not an independent bilingual rating. The experiment was reverted: retained provider prompts match the initial bytes, and the live experimental PDF is **not publishable or a final-source linguistic acceptance result**. No story-specific substitution or default-provider change was made.
- Packaged font matching remains approximate. In the real source probe both panels chose a bundled serif bold face; this does not establish exact source-font/weight recovery. Short rules versus narrow letter stems need representative visual calibration. No claim of seamless replacement for arbitrary PDFs or textured backgrounds is made.

## Required owner/reviewer work, in order

1. Collect genuine English/Cebuano/Filipino scan/photo/screenshot material, actual rights/acquisition information, complete source transcripts and region geometry. Use the existing kit's3x3x4 starting grid. An independent person must check the originals and supply actual attestations. The Lion/Mouse sample has been used for tuning and must remain **calibration**, never held-out evidence.
2. Freeze settings after calibration. Measure genuinely unseen held-out material using the existing evaluator, keeping the95% gate. Review region recall, reading order and erasure/redraw quality separately from spelling accuracy. English-to-Cebuano requires English-source OCR evidence; changing the target language does not change the source recognition pack. Unknown capture type currently requires scan/photo/screenshot scopes.
3. Independently assess the configured translation route on supported language directions. Fast-mode success/HTTP200 is not semantic acceptance. Model/routing changes require an owner decision supported by bilingual comparison; no new provider default was selected here.
4. Only after legitimate evidence passes, sign/verify the evaluator report and configure durable acceptance-report/key/manifest and separate operational-plan-key paths. Then rerun the ordinary service on the sample: both dialogue regions must really translate in place, old glyphs disappear, artwork stays unchanged outside masks, text is searchable, and Cebuano meaning is checked. Complete Linux/font/licensing and visual review before release.

Exact intake/review/evaluator/key commands are in [the OCR kit README](../Model/tools/ocr_kit/README.md). They require real source folders and human review; running the commands against generated or unchecked references does not satisfy this task. The installed isolated environment is `trilingua-code/.venv-ocr-layout`; no additional install is needed for the retained approach.

## Reproduce local engineering checks

From repository root in PowerShell:

```powershell
$py = (Resolve-Path .\trilingua-code\.venv-ocr-layout\Scripts\python.exe).Path
& $py output/reviews/hybrid-pdf-implementation/offline_tests.py trilingua-code/Model/tests/test_ocr_functional.py trilingua-code/Model/tests/test_ocr_documents.py trilingua-code/Model/tests/test_pdf_image_layout.py trilingua-code/Model/tests/test_pdf_hybrid_regeneration.py trilingua-code/Model/tests/test_hybrid_fonts.py -q --tb=short
Set-Location trilingua-code
php vendor/phpunit/phpunit/phpunit tests/Feature/HybridPdfPartialOutputTest.php tests/Feature/TranslationControllerTest.php tests/Feature/TranslationStatusDownloadIntegrityTest.php tests/Feature/DocumentPreviewTest.php tests/Feature/Admin/TranslationManagerRegenerateTest.php tests/Feature/Admin/ReviewDraftPublishIntegrityTest.php tests/Feature/Admin/DocumentReviewWriteActionsTest.php --no-progress
$env:TRILINGUA_PLAYWRIGHT_MODULE = 'C:\Users\walbe\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright'
node --test tests/browser/hybrid-pdf-partial.test.mjs
```

The larger Python handoff run additionally covers classification, corpus contract, feasibility, general regeneration/regression, service-token policy, trust, resources, provider deadline budgets, kit and signed-fixture service smoke. Full invocations/logs and preservation hashes are in `output/reviews/ocr-functional-implementation/`. Automated fixtures establish engineering behavior; they never enable real-input acceptance.
