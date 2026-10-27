# Local OCR implementation — 25 October 2026

## Current state

The local implementation now has page-level PDF OCR, an image-to-PDF path, explicit extraction failures, review warnings and reconstruction from saved OCR blocks. **Normal OCR use remains on HOLD.** No language/input category has acceptance-ready evidence at the approved 95% word-accuracy minimum. Image uploads remain hidden (`TRANSLATION_IMAGE_UPLOADS=false`), and scanned PDF pages fail explicitly rather than disappearing from otherwise successful documents.

This is local work only. Nothing was deployed or published, and no database migration was needed. Existing unrelated working-tree edits were retained.

## Implemented

- Native PDF text still uses the existing extractor. Each page is classified as native, filtered native, blank or OCR-required. Scan-only pages join native pages in source order; a missing OCR prerequisite fails the document.
- OCR uses Tesseract at 300 DPI with source-language packs `eng`, `ceb` and `fil`. Installed packs and checksums are recorded. Missing runtime, packs, evidence, unreadable pages and timeouts have explicit outcomes.
- Decimal confidence is parsed safely. Uncertain words remain in extracted text and carry separate confidence/geometry metadata; they are not silently discarded or represented as translation-quality scores.
- Raster input is bounded to 40 megapixels and a minimum 200 pixels per side. Image extension/format, single-frame content, EXIF orientation, transparent backgrounds and decoding are checked. Preprocessing is grayscale plus autocontrast; it does not correct perspective.
- PNG/JPG/JPEG mappings reach Laravel capabilities/validation, the durable upload job, the Python endpoint and PDF download/regeneration names. The image capability is disabled by default, and Python independently enforces photo-category acceptance.
- OCR documents use a **separate translated-text PDF**, grouped by source page. This reflows the whole translated document, including native pages in a mixed PDF; it does not reproduce artwork, tables or source layout. Native-only PDFs retain the existing preserved-layout writer. Saved reflow output is reopened and checked for complete rendered text.
- OCR metadata, page classifications and extraction warnings survive sidecar storage. Reviewers see warnings and per-block OCR confidence. Completed download responses carry extraction warnings to the translation page. Regeneration uses saved text and edits without OCR or translation calls.
- `GET /ocr/readiness` reports runtime and per-category state behind the existing service-token check, without calling a translation provider. Health distinguishes ordinary formats from quality-gated image formats.

## Runtime installed locally

- Tesseract `5.4.0.20240606`, installed using the Windows package manager with installer-hash verification. The [official Tesseract installation guidance](https://tesseract-ocr.github.io/tessdoc/Installation) points Windows users to UB Mannheim builds.
- `pytesseract 0.3.13`; the dependency is declared in `Model/requirements.txt`.
- English/OSD data copied from the installed runtime; Cebuano and Filipino data downloaded from the official `tesseract-ocr/tessdata_fast` repository at revision `87416418657359cb625c412a48b6e1d6d41c29bd`.
- Local `.env` now specifies `OCR_TESSERACT_CMD` and standard `TESSDATA_PREFIX`. No unrelated environment values were intentionally changed. Pack-source URLs and hashes are in `%LOCALAPPDATA%/TriLingua/ocr/pack-sources.json`.

## Recognition evidence and its limits

Evidence is saved under `output/reviews/ocr-2026-10-25/` at the repository root:

- `manifest.json`: six rasterized publication crops, one upstream English OCR benchmark, and one explicit missing-photo placeholder.
- `feasibility-report.json`: seven measured OCR cases, no translation-provider calls from the evaluator.
- References were visually compared by Codex with the rendered images and corrected for visible glyph artifacts. This is **not independent human transcription review**.
- The six publication crops are generated from born-digital files, not physical classroom scans. The upstream scan is an engine benchmark, not a representative classroom sample. Rights/representativeness remain explicitly unapproved in this manifest, so these scores cannot enable any category.

| Preliminary sample group | Word accuracy | Release decision |
|---|---:|---|
| English / scan-like fixtures | 100.00% | HOLD: insufficient representative evidence |
| Filipino / scan-like fixtures | 94.44% | HOLD: insufficient evidence; preliminary score also below 95% |
| Cebuano / scan-like fixtures | 94.82% | HOLD: insufficient evidence; preliminary score also below 95% |
| Phone photos | Not measured | HOLD: no acceptance-ready photo set |

These are sample-specific, word-weighted scores. They are not general language accuracy, classroom readiness or translation accuracy. Punctuation, case and diacritics are retained in scoring. The source material itself contains some unusual spellings/typos and image-region reading-order ambiguity.

`run-functional-smoke.py` and `functional-smoke.json` record a separate functional check: real local OCR on a mixed PDF, **mock translation**, saved sidecar, an edited block and regenerated PDF. The gate was stubbed only within that isolated test process; no application category was enabled. The generated mock PDFs are software evidence, not usable translations. A rendered regenerated page was visually inspected for layout and accented-character display.

## Verification

- **113 focused Python tests passed**: OCR, evaluator and regeneration checks plus existing document regression and service-token tests. The **30 analysis resilience tests passed separately**.
- Image tests exercise both the legacy and unit translation routes. Mixed-PDF tests check page mapping, no duplicated native text, blank pages, failed scan extraction and edited regeneration.
- **24 PHP tests / 97 assertions passed**, covering capability gating, valid uploads and extension spoofing, download warnings, review rendering/escaping and regeneration naming.
- Frontend production build passed. It retains the existing large-bundle warning for document preview dependencies.
- The analysis resilience tests pass separately. A broader combined run exposed existing test-order contamination: importing `server` loads local provider settings, after which six analysis fixtures expecting different defaults fail. This OCR work does not change provider behavior or claim a clean full-suite run.
- No live translation-quality evaluation, authenticated browser upload/queue pilot or deployment acceptance was performed.

Commands from the repository root (PowerShell):

```powershell
py -3.11 -m pytest trilingua-code/Model/tests/test_ocr_documents.py trilingua-code/Model/tests/test_ocr_feasibility.py trilingua-code/Model/tests/test_regeneration.py trilingua-code/Model/tests/test_regression.py trilingua-code/Model/tests/test_service_token_policy.py -q
py -3.11 -m pytest trilingua-code/Model/tests/test_analysis_resilience.py -q
```

From `trilingua-code/`:

```powershell
php vendor/phpunit/phpunit/phpunit tests/Feature/TranslationControllerTest.php tests/Feature/TranslationStatusDownloadIntegrityTest.php tests/Feature/DocumentPreviewTest.php tests/Feature/Admin/TranslationManagerRegenerateTest.php --no-progress
npm run build
```

## Remaining acceptance sequence

1. Assemble 5–10 representative input documents for the categories to be supported. Include real classroom scans and actual phone photos across the three languages; record provenance, usage rights and input quality. The current diagnostic crops do not satisfy this step.
2. Complete independent, image-checked references. Each manifest case needs `language`, `pack`, `input_category` (`scan`/`photo`), `image`, `reference`, `source_url`, `reference_checked`, `reference_reviewer`, `rights_verified`, `representative`, and `acquisition` (`real_scan`/`real_photo`). Mark these truthfully; do not relabel the diagnostic crops to obtain a pass.
3. From `trilingua-code/Model`, run `py -3.11 -m benchmarks.ocr_feasibility --manifest PATH --minimum-accuracy 95 --output PATH`. The evaluator uses the production recognizer and preprocessing. Missing data remains HOLD; measured category failures remain NO-GO.
4. If a representative category falls below 95%, present its errors and results to the owner before changing engines, reducing supported input/language scope or deferring that category. No threshold reduction or engine change was made here.
5. For a passing category, set `OCR_ACCEPTANCE_REPORT` to the generated report. Runtime version, pack hash, settings, category and minimum must match. A scan-category pass does not enable photos. The report must be regenerated after relevant runtime/processing changes.
6. After photo acceptance, enable `TRANSLATION_IMAGE_UPLOADS=true`, refresh Laravel configuration if cached, restart Python/queue workers and run an authenticated local upload → queue → review/edit → regenerate → download pilot. Keep unvalidated categories rejected.

Region-level OCR, handwriting, and replacement of words inside scanned artwork remain outside this implementation. Perspective correction is not implemented: photo acceptance and any preprocessing needed to meet the 95% gate remain unfinished. Image regions on native-text pages are explicitly warned about, not OCR-translated. A PDF extension alone cannot establish that a raster page came from a clean scanner rather than a camera; the accepted input-quality scope must remain explicit.
