# Hybrid PDF implementation handoff

Branch: `codex/hybrid-pdf-p0-p4`. Implementation started 25 October 2026; handoff 26 October 2026 (Asia/Manila).

## Delivered and held

| Phase | Implemented | Verification / limit |
|---|---|---|
| P0 | Isolated `.venv-ocr-layout`, baseline versions/hashes and offline test runner | Baseline: 113 Python tests; 24 PHP tests / 97 assertions |
| P1 | Region inventory on mixed pages; visible/hidden native checks; local many-to-many ownership; acceptance before recognition; strict native preflight; explicit complete/partial/untranslated status; empty-block sidecar persistence | All-held output retains original content; no dummy translated blocks; no new PDF job reflows; historical sidecars regenerate through their legacy path |
| P2 | Corpus schema/evaluator v2; screenshots; split/content isolation; independent references/provenance/hashes; word accuracy, region recall and reading order | No corpus was created. Legacy/calibration material cannot enable a category; 95% minimum retained |
| P3 | Flat-background glyph masks, rules/neighbors protected, spatial background checks, fill/residual checks, licensed-source packaged font assets, bounded fit, unique-image pixel updates and searchable target text in one assembly | Fixed geometry and fixed translations tested. Real scanned/mixed OCR acceptance and owner visual review remain blocked |
| P4 | Sidecar v3/render plan v2; hash/version/font rejection; saved masks; reconstruction-only regeneration; atomic file and updated-plan publication; review/history/download labels; one isolated PDF worker and resource limits | Windows tests pass. Actual Linux execution and release sign-off remain outstanding |

An index-only Python source export, excluding unrelated dirty hunks, also passed 178 tests with 1 skip (the export contains Model files, not every external fixture).

Final working-tree checks: **179 Python tests passed**, followed by **48 affected renderer/service tests passed** after the final mask-boundary checks; **49 PHP tests / 239 assertions passed**; **2 browser tests passed**; `pip check` passed. Browser routes were intercepted; no application server was started. Translation tests used mocks and the Python runner denied actual outbound socket connections before server imports. Readiness checks made no translation requests.

**Real-document image replacement remains HOLD for English, Cebuano and Filipino across scan, photo and screenshot categories.** The live `.env`, OCR acceptance settings and unrelated tracked source hashes match their starting snapshots. No real acceptance report was created or installed. Unit contract fixtures are diagnostic tests, not acceptance evidence.

## Behavior and boundaries

- Held image pixels remain original. Held native text remains original. Provider attempts/cache work are separate from translated/held/passthrough content counts.
- Source text is removed from the edited unique image stream, not hidden by a PDF patch. Only approved glyph-mask pixels change; saved decoded pixels and searchable target text are checked. Unmodified assets retain their byte invariant.
- Shared resources, optional layers, embedded backups, forms, clipping, alpha/transparency, overlaps, nonuniform stretch, rotations, outlined text, uncertain typography, non-flat backgrounds, low word confidence or unfittable target text are held.
- Image body text wraps and may shrink only within its bounded range, never below 10 pt. Native strict fitting retains its existing size policy. Family/weight selection is a shape estimate against packaged Noto Sans/Serif assets, not a promise of exact brand-font recovery.
- New image uploads use the same source-preserving PDF route. v1/v2 reflow sidecars keep their historical regeneration behavior.
- Regeneration verifies the durable original, runtime/algorithm/font hashes and bounded masks, uses no recognition or translation, then publishes the PDF and updated fit plan together. Failed edits retain the last published file.
- Limits: 50 pages, 40 MP, 60 s per Tesseract call, 8 MB accumulated encoded masks, 16 MB render plan, 24 MB sidecar/result. PDF work is serialized across threads/processes; its isolated process and OCR descendants are contained on expiry.
- Default job deadline is 900 s and is reduced against effective service/job/worker budgets. Expiry prevents further PDF work and publication. An already in-flight provider request still uses its existing transport timeout; hard cancellation of provider networking was not added.

## Exact isolated setup and checks (PowerShell)

Run from `C:\dev\Trilingua`. The environment already exists; creation/install commands below are for reproduction and do not update the live application environment.

```powershell
Set-Location C:\dev\Trilingua
py -3.11 -m venv trilingua-code\.venv-ocr-layout
& .\trilingua-code\.venv-ocr-layout\Scripts\python.exe -m pip install -r output/reviews/hybrid-pdf-implementation/requirements-isolated.lock.txt
& .\trilingua-code\.venv-ocr-layout\Scripts\python.exe -m pip check
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --version
```

No runtime font download is needed: eight font files, license text, pinned upstream revision and hashes are in `trilingua-code/Model/assets/fonts/manifest.json`. The source license was retrieved from the [Noto repository](https://github.com/notofonts/noto-fonts/blob/ffebf8c1ee449e544955a7e813c54f9b73848eac/LICENSE); embedding/redistribution and PyMuPDF AGPL obligations still require owner review. This report is not a legal determination.

```powershell
& .\trilingua-code\.venv-ocr-layout\Scripts\python.exe output/reviews/hybrid-pdf-implementation/offline_tests.py trilingua-code/Model/tests/test_pdf_region_classification.py trilingua-code/Model/tests/test_pdf_image_layout.py trilingua-code/Model/tests/test_pdf_hybrid_regeneration.py trilingua-code/Model/tests/test_hybrid_fonts.py trilingua-code/Model/tests/test_ocr_corpus_contract.py trilingua-code/Model/tests/test_ocr_feasibility.py trilingua-code/Model/tests/test_ocr_documents.py trilingua-code/Model/tests/test_regeneration.py trilingua-code/Model/tests/test_regression.py trilingua-code/Model/tests/test_service_token_policy.py -q --tb=short

Push-Location trilingua-code
php vendor/phpunit/phpunit/phpunit tests/Feature/HybridPdfPartialOutputTest.php tests/Feature/TranslationControllerTest.php tests/Feature/TranslationStatusDownloadIntegrityTest.php tests/Feature/DocumentPreviewTest.php tests/Feature/Admin/TranslationManagerRegenerateTest.php tests/Feature/Admin/ReviewDraftPublishIntegrityTest.php tests/Feature/Admin/DocumentReviewWriteActionsTest.php --no-progress
$env:TRILINGUA_PLAYWRIGHT_MODULE='C:\Users\walbe\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright'
node --test tests/browser/hybrid-pdf-partial.test.mjs
Pop-Location
```

## Linux font check (provided, NOT executed here)

On an existing Linux checkout with Python 3.11, from repository root:

```sh
python3.11 -m venv trilingua-code/.venv-ocr-layout
trilingua-code/.venv-ocr-layout/bin/python -m pip install -r output/reviews/hybrid-pdf-implementation/requirements-isolated.lock.txt
trilingua-code/.venv-ocr-layout/bin/python output/reviews/hybrid-pdf-implementation/offline_tests.py trilingua-code/Model/tests/test_hybrid_fonts.py trilingua-code/Model/tests/test_pdf_image_layout.py trilingua-code/Model/tests/test_pdf_hybrid_regeneration.py -q --tb=short
```

## Remaining release work

1. Owner supplies rights-cleared, representative real scans/photos/screenshots and independent checked region references, split by document/content. No material was fabricated for this implementation.
2. Run evaluator schema v2 against that corpus with the actual engine/packs/settings. Every enabled language/capture scope needs genuine matching heldout evidence at or above 95%; calibration stays diagnostic. Unknown capture origin requires all plausible supported scopes, not the easiest passing one.
3. Calibrate region/visibility/font/background thresholds and perform visual review on real documents, including missed-region/order evidence, tables and columns. Conservative holds can over-report artwork as potential text.
4. Run the provided tests on actual Linux and approve visual/font parity. Review font embedding rights and PyMuPDF licensing before release.
5. P5 expansion, outlined replacement, textured/photographic backgrounds, new OCR engines and cloud editing are excluded.

## Change inventory and preservation

See `CHANGED_FILES.txt` for the exact task paths; `PROGRESS.md` and `TASKS.md` retain phase detail. P0-P3 commits: `4599e6f`, `ac36462`, `3c2ce0b`, `ef4479a`; P4 is the final hardening commit.

Unrelated initial Phase A/provider/admin changes remain uncommitted. Mixed files were staged with task-specific contents so those pre-existing hunks were not swept into the phase commits. Private baseline byte snapshots, exports and raw test logs are not committed. `PRESERVATION.json` records the unchanged live environment and unrelated source-hash check. Git reported a pre-existing stale-worktree metadata cleanup permission warning; phase commits succeeded and no checkout was removed.
