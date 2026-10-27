# Hybrid PDF translation — implementation plan only

25 October 2026. **No implementation approval is assumed. No application code, configuration, packages or acceptance settings were changed for this plan.**

Inputs: [investigation report](C:/dev/Trilingua/output/reviews/layout-preserving-ocr-investigation-2026-10-25/FINDINGS_AND_DESIGN.md), the follow-up options comparison in this chat, [primary-source options note](C:/dev/Trilingua/output/reviews/layout-preserving-ocr-investigation-2026-10-25/ocr-options-primary-sources.md), and the user's nine fixed decisions. All nine are retained. The subsequently selected minimum is **10 pt for body text in the new image-text renderer**.

## 1. Delivery sequence and gates

**First ship classification plus truthful partial-output behavior.** Build the corpus/evaluator concurrently. The complete pixel-replacement slice depends on both; expansion waits for review of that slice.

Effort below is an estimate of focused engineering days, not an accuracy promise or committed schedule. All new filenames are **proposed** and do not exist yet. Existing-file claims are linked in the source map below.

| Phase | Proposed work and files | Dependency | Measurable exit criterion | Estimate |
|---|---|---|---|---|
| P0 — isolated baseline | Reproduce existing tests; record dependency/font versions and fixture hashes. No application settings change. | Plan approval | Baseline failures distinguished from new failures; original files immutable; local test environment reproducible. | 0.5–1 day |
| **P1 — standalone classification fix** | Create `Model/document/pdf_regions.py`, `Model/document/pdf_worker.py`, `Model/tests/test_pdf_region_classification.py`. Modify `extractor.py`, `ocr_extractor.py`, `document_pipeline.py`, `reconstructor.py`, `regenerator.py`; add completeness handling through response/context, PHP persistence/downloads and the two review/completion views. Detailed package in §2. | P0 | Native content never suppresses candidate image/outline regions; no fresh job takes document-wide OCR reflow; real gate rejection produces held regions with originals intact and accurate partial warnings/counts. Native-only and historical-sidecar regressions pass. | 3–5 days |
| **P2 — corpus and evaluator, parallel track** | Extend `Model/benchmarks/ocr_feasibility.py`, `test_ocr_feasibility.py`; add `test_ocr_corpus_contract.py`. Collect private corpus, references and separate splits. No threshold change. | Starts alongside P1; evaluator/schema design coordinated with P1 | Screenshots/larger manifests supported without weakening eligibility; held-out reports include every expected region, missed text, word accuracy and order. A category is eligible only after genuine evidence meets 95%. | 1.5–3 engineering days **plus 3–7 corpus/review person-days**, potentially longer elapsed |
| P3 — one complete flat-background slice | Create `Model/document/image_reconstructor.py`, `Model/tests/test_pdf_image_layout.py`; extend `layout.py`, OCR block extraction, unit adapters/map, single PDF writer and validator. Add OpenCV headless only in the isolated environment. | P1 + a passing P2 category; layout helpers can be developed earlier with fixed geometry/translations | One fully scanned PDF and one same-page native+image PDF use genuine approved OCR, existing translation, cleaned image pixels and searchable PDF target text. Original page geometry retained; held regions untouched; no duplicate text, remnants or outside-mask damage. Owner reviews the rendered slice before expansion. | 4–7 days |
| P4 — regeneration and release hardening | Extend `regenerator.py`, existing validator, sidecar/resource checks and admin region review. Add `test_pdf_hybrid_regeneration.py`, PHP partial-output tests and a browser partial-output check. Provision approved fonts on Linux. | P3 reviewed | Edited regeneration makes zero OCR/provider calls, uses no temporary references and preserves cleaned backgrounds. Hash/version/font failures reject safely. Partial warning survives upload/status/review/download. Linux output and native-only regression pass. | 2–4 days |
| P5 — reviewed expansion | Extend region/renderer tests for tables, columns, rotations/cropboxes, additional capture/language categories and **isolatable flat-background outlined text**. Shared/clipped/transparent/overlapping occurrences stay held unless separately proven safe. | P3 review + P4; passing evidence for each added category | Each newly enabled class passes the same recognition, visual, completeness and regeneration checks. Unisolatable vector glyph paths remain held; no whole-page flattening of mixed PDFs. | 3–6+ days; vector-path isolation is the largest technical uncertainty |

**Planning range:** first raster/native release roughly **11–20 engineering days plus corpus/review work**; roughly **3–6 working weeks for one person** under the stated assumptions. P5 is additional. The **acceptance corpus and reviewer availability are the likely critical path**. If recognition fails 95%, there is no honest completion date until a newly evaluated configuration passes; implementation progress does not authorize release.

## 2. P1 standalone work package

P1 may ship without enabling a single image-text replacement category. It fixes classification/routing and makes incomplete output explicit, not falsely seamless.

| Step | Required behavior |
|---|---|
| Inventory | Per page, collect native spans, image occurrences/xrefs/transforms, drawing candidates, page boxes and rotations. Preserve original coordinates and an explicit transform chain. |
| Raster verification | Inspect image/drawing regions rather than treating “some native text exists” as coverage. Use pixel structure plus native visibility/occlusion signals. An image/drawing is only a text **candidate** until verified. |
| Calibrated signals | Native coverage of candidate text, invalid/replacement/private-use Unicode ratio, text-region area/height, baseline consistency, visibility through `get_texttrace`, paint order/occlusion, and OCR/native agreement. Freeze thresholds against calibration data and record their version. Missing/ambiguous evidence produces `held`, not an invented native/OCR classification. |
| Gate ordering | Call the unchanged acceptance check before application OCR for each candidate's evidence scope. If blocked, record `ocr_acceptance_hold`; do not invoke recognition, trust a hidden layer as a substitute, or bypass the gate. OCR/native agreement is explicitly unavailable in that case. |
| Hidden layers / outlines | A visible native span can use the native path. An invisible OCR layer is a recognition candidate, not native artwork: check agreement when eligible, and suppress duplicate translation. Suspected outlined words remain region candidates; unproved glyph-path isolation is held. |
| Local dedup | Match words/lines/paragraphs many-to-many within one region using containment/overlap, text agreement and visibility. Preserve repeated strings elsewhere. Retain match provenance; ambiguous ownership is held. |
| Safe first output | Translate eligible native blocks. Until P3 passes, pixel/outline candidates remain held with original pixels/paths untouched. New jobs do not use `ocr_reflow` to reconstruct the whole document. Fully held jobs report **zero translated regions** and an explicitly untranslated/source-preserving result. |
| Strict native fit | Reuse native fonts/links/quality. Preflight placement before redaction; if a native block cannot fit in strict mode, retain it and flag it. No automatic continuation pages for new strict jobs. Do not raise existing native font sizes merely because the new image renderer has a 10 pt floor. |
| Partial accounting | Separate execution status from content status: `complete`, `partial` or `untranslated`; include translated/held/passthrough region counts and held reason/page/box. Held regions are never provider work, translated output or completed translated-word volume. Unknown source coverage is not reported as complete. |

**All-held persistence is a P1 requirement:** the current empty-block branch returns before saving a supplied sidecar ([BlockService.php:35–43](C:/dev/Trilingua/trilingua-code/app/Services/BlockService.php:35)). Persist the versioned region plan/completeness independently of block count, in the same completion transaction. Do not create a dummy translated block to avoid this branch. Add a real all-held envelope → history → status → review → download regression test.

**P1 integration files:** `Model/dto/responses.py`, `pipeline/document_context.py`, `server.py`; PHP `TranslationManager.php`, `BlockService.php`, `Admin/ReviewService.php`, `CompletedDownloadResolver.php`, `MetricsService.php` as needed for accurate existing counters; `resources/views/admin/review-document.blade.php`, `resources/views/translation.blade.php`. Region summaries remain in the sidecar/response, not invented database columns. Extend `SourceWordCounter.php`/its caller only to retain partial/unknown extraction coverage; do not conflate source-document volume with translated volume or rewrite unrelated statistics. Backend review actions must retain completeness status, not merely hide a warning in the view.

Create `tests/Feature/HybridPdfPartialOutputTest.php` for status/warnings/counts and legacy behavior. P1 regression examples: one native caption over a screenshot; a page number on a scan; visible native plus hidden duplicate; native page plus scanned page; native-only PDF; and old reflow-sidecar regeneration. Gate-held tests must preserve the real HOLD outcome. Pure geometry/renderer fixtures are not acceptance reports and must never be installed as application evidence.

Capture provenance cannot be reliably inferred from a `.pdf` extension. Unknown scan/photo/screenshot origin must not be routed to whichever category happens to pass: require evidence for all plausible supported capture classes or hold pending verification. Outlined PDFs need their own accepted evidence before enabling that path.

## 3. Data, rendering and persistence contract

Reuse existing dict blocks, `TranslationUnit`/`unit_adapters.py` and the existing translator. Do not introduce another translation service or duplicate review database.

| Record | Proposed extension |
|---|---|
| Region | Stable `region_id`, page, occurrence ID, xref/resource identity where relevant, source kind (`native`, `raster`, `outlined`, `unknown`), capture/evidence scope, bbox+quad, transform chain, status and reason. Native candidates and uncertain regions both remain traceable. |
| OCR paragraph/block | Stable source ID, region/occurrence association, words with confidence and geometry, original line/paragraph membership, reading order, language/pack, raw text and any reviewed correction provenance. Preserve paragraph context through translation; never flatten a multi-line heading into unrelated requests. |
| Estimated style | Family/weight, size estimate, foreground/background color, alignment, baseline angle; each has method/confidence. Work from the original color raster, not grayscale OCR input. Uncertain estimates can hold a region. |
| Render plan | Version, original SHA-256, source/image hashes, page boxes/transforms, glyph masks, approved fills, font IDs/checksums/licenses, translated block references, fit decisions and allowed edit areas. A held region has no destructive edit action. |
| Content summary | Counts/IDs for translated, held and passthrough regions; source-coverage provenance; completeness status and warnings. Operational provider/cache counters remain separate from successful placement and content completeness. |

**Single assembly:** copy the original document once; plan all native and image operations before committing. For each unique non-overlapping raster occurrence, create a cleaned lossless image from its source pixels, change only approved glyph masks and draw visible PDF target text through the occurrence transform. Multiple accepted regions in one image share one cleaned bitmap; held regions in it retain their original pixels. Remove corresponding obsolete hidden OCR text only for successfully edited regions. Hold ambiguous overlaps rather than destroying native content or changing paint order.

“Unique” means one displayed occurrence across the entire document/resource inventory, including nested forms, not merely one image entry on the current page. If uniqueness, clipping, alpha or ownership cannot be established, hold the occurrence. Stable region IDs derive from original-file identity, page/occurrence and deterministic region identity; freeze them in the sidecar and preserve the existing integer `block_index` association used by database edits.

Restrict the existing image-unchanged check to unmodified assets. For edited images, check decoded pixels outside approved masks, alpha and dimensions; do not compare compressed bytes as if intentional edits were corruption. Ensure the output does not retain an obsolete original image/revision containing removed words for an edited unique asset. A colored overlay never satisfies this test.

**Historical compatibility:** introduce a new versioned plan for new jobs. Sidecar versions already using legacy reflow remain on their old regeneration path. Unknown plan versions reject instead of being guessed. P1 may save a native-plus-held plan; P3 adds approved pixel-edit actions under a defined newer plan version.

**Regeneration:** resolve the durable original, verify its hash plus plan/algorithm/font versions, rebuild from saved masks/fill parameters and the current edited target text, then rerun fit/validation. Do not OCR, call a provider, or reuse ephemeral files. Store bounded compressed masks and deterministic flat-fill parameters in the JSON sidecar. This flat-background scope does not require a new external cleaned-image storage system; if artifacts later exceed bounds, hold them rather than adding unbounded base64 payloads.

If a new edit no longer fits, retain the last published file and return a fit failure; never publish a partially erased regeneration. Preserve the draft/published distinction.

## 4. Typography and mask pipeline

1. Select an approved, redistributable font family/weight; estimate initial point size from source glyph geometry and font metrics. **Body text in the image renderer never goes below 10 pt.** Wrap, then bounded shrink; calibrate the shrink range. Hold if the size/style/rotation cannot be matched safely.
2. Provision the same approved font files on Windows and Linux through proposed `Model/assets/fonts/manifest.json`, accompanying font/license files, and `Model/tests/test_hybrid_fonts.py`. Require glyph coverage for English/Cebuano/Filipino, ñ, accents/combining marks and punctuation. Do not rely on host Arial paths, OS font-package availability or request-time downloads. Exact brand typography is excluded without supplied assets.
3. Create glyph masks inside recognized word/line geometry. Exclude table rules, borders, adjacent native content, icons and held regions; account for anti-aliased edges. Background verification uses multiple clean boundary/interior samples, color variation and edge/texture evidence, not four corner equality.
4. If verified flat, fill only the glyph mask from the approved local background color; retain the original-color image. Detect residual source edges/halos and unintended mask coverage. Gradient/photo/textured backgrounds, curved/stylized text, ambiguous masks and unproved overlaps are held.
5. Validate translation, mask, background and fit **before** removing source pixels or native glyphs. Stage the result, render it, and commit only successful region actions. No inpainting model, cloud image editor or second OCR engine is added in this plan.

## 5. Corpus/evaluator package

**Suggested pilot, not a statistical readiness guarantee:** 36 independent pages/documents across 3 source languages × 3 initial capture classes × 4 cases, with two calibration and two held-out documents per slice. Include controlled known-text captures plus real user materials; expand poorly covered/error-prone slices before release. The same source content must not cross splits. Real captures of the same page are correlated and do not count as independent content. Add a separate outlined-PDF slice before P5 enables outlines.

Use permission-cleared real scans, real photos of flat printed material, and real digital screenshots. Include unsupported textured/skewed/curved negatives for correct HOLD behavior, without removing difficult in-scope text from the scoring denominator. Store private originals/references outside tracked application fixtures; repository fixtures may be small permission-cleared/synthetic geometry cases only.

**Proposed evaluator schema v2:** case ID, document/content-group ID, split, source language/pack, capture class, source kind, image/PDF page and transforms, every expected text region and order, transcript, expected supported/held scope, rights/provenance, reference-check status/reviewer, source/reference hashes. Add `screenshot` and later `outlined_pdf` with truthful acquisition tags; remove the spike's 10-case ceiling. Validate nonempty unique cases, independent split groups and reviewed evidence instead of treating a case count as proof of quality.

Score separately per source-language/input category, and report per document:

- **Word accuracy:** same Unicode/whitespace policy; count expected words in missed regions as deletions. The **95% requirement is unchanged**. Recognition confidence does not substitute for this measurement.
- **Region recall:** matched expected regions / all expected in-scope text regions, with missing regions listed. Report false positives separately.
- **Reading order:** pair-order agreement and explicit column/cell inversions, not just a concatenated transcript score.
- **Visual/completeness checks:** target coverage, residual source glyphs, held-region integrity and outside-mask changes, independently of recognition and translation quality.

Freeze OCR/segmentation/style settings after calibration. Calibration reports must remain diagnostic/HOLD regardless of their score; only reviewed held-out evidence may generate acceptance-eligible results. Evaluate held-out material once for the selected version; after tuning from a held-out failure, replenish the held-out set rather than rebranding it as independent evidence. Versioned reports retain runtime/packs/settings fingerprints and reference evidence. Preserve the runtime report contract while replacing the evaluator's spike count restriction with genuine corpus validation. Screenshot/outline schema work changes neither the threshold nor the requirement for matching evidence; no synthetic report, force flag or hidden-layer shortcut may enable a category.

Recognition measurement is performed by the evaluator, as distinct from application OCR eligibility. Application processing always consults genuine matching acceptance evidence. Until that exists, the end-to-end outcome remains held; no gate bypass is needed to test pure layout helpers with predetermined geometry/translations.

## 6. Review, warnings and failure policy

- Admin review: page/region list plus source-page link/box coordinates, source kind, translated/held status, reason, OCR/style evidence and proposed target text. A held region may have no recognized text and still must be visible. It is not a fake translated block or a quality-score zero. Use the existing original-file access path first; no new PDF viewer dependency is needed for P1.
- Download/status: durable machine-readable completeness plus a visible message such as **“Partially translated: 3 regions retain original text.”** Include page/region reasons, counts and a partial/untranslated filename label. A completed queue job does not imply complete content. An all-held result has zero translated regions and is labelled untranslated.
- Keep warnings in history/review and regenerated downloads, not just the initial POST. Do not let “Verify Document” dismiss held/untranslated content as a complete translation; verification must preserve completeness status.
- Preserve original and held content. Malformed/encrypted inputs fail explicitly; unreadable/low-confidence, unsupported background, failed provider, unavailable font or no-fit regions are held when the page can otherwise be processed safely. A corrupt or unvalidated final PDF is not offered as a download. Failed regeneration retains the last published output.

**Initial benchmark bounds (proposed):** retain 40 MP/page and 60 s OCR-call limits; one isolated PDF worker process, one page/crop at a time, at most two raster buffers; 50 pages/job, 16 MB total compressed sidecar with decoded-pixel/decompression bounds, and a 900 s whole-job deadline including providers. Verify the deadline is below the configured service/job/worker budgets; a call must fit the remaining budget. Over-budget regions are held, or the job fails safely if parsing/assembly cannot complete. These are starting operational caps to validate, not throughput claims.

PyMuPDF document/page work must not run concurrently in request threads. `pdf_worker.py` will own bounded sequential analysis/assembly tasks using independently opened documents; exchange paths/serializable plans, never live Document/Page objects. Existing translation HTTP batching stays in its route. Only after latency/peak-RAM benchmarks may a small process pool be considered. No new distributed queue or service is proposed.

## 7. Post-approval commands — not executed

The new test filenames/CLI flags below are **planned interfaces**, not tools already available. No command overrides `require_ready`, fabricates a passing report, enables image uploads or weakens 95%. Run commands from the stated directory; do not use a live application environment for experiments.

### P0/P1 — isolated baseline and classification

```powershell
Set-Location C:\dev\Trilingua\trilingua-code
py -3.11 -m venv .venv-ocr-layout
$ocrPython = 'C:\dev\Trilingua\trilingua-code\.venv-ocr-layout\Scripts\python.exe'
& $ocrPython -m pip install -r .\Model\requirements.txt 'PyMuPDF==1.27.2.3' 'pillow==12.2.0' 'pytesseract==0.3.13'
& $ocrPython -m pip install -r .\requirements-dev.txt
& $ocrPython -m pip check
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --version
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --list-langs --tessdata-dir 'C:\Users\walbe\AppData\Local\TriLingua\ocr\tessdata'
& $ocrPython -m pytest Model/tests/test_regeneration.py Model/tests/test_regression.py -q
# After implementing P1:
& $ocrPython -m pytest Model/tests/test_pdf_region_classification.py Model/tests/test_ocr_documents.py -q
php vendor/phpunit/phpunit/phpunit tests/Feature/HybridPdfPartialOutputTest.php tests/Feature/TranslationControllerTest.php tests/Feature/TranslationStatusDownloadIntegrityTest.php --no-progress
```

Existing Tesseract and packs need no reinstall on this PC. The reference package versions reproduce the inspected stack; the prototype environment is not automatically used by the normal launcher.

### P2 — schema tests, calibration and held-out evaluation

```powershell
Set-Location C:\dev\Trilingua\trilingua-code\Model
& $ocrPython -m pytest tests/test_ocr_feasibility.py tests/test_ocr_corpus_contract.py -q
$corpus = 'C:\Users\walbe\AppData\Local\TriLingua\ocr-corpus\manifest.json'
# --split is proposed P2 functionality; the manifest and output folders must exist.
& $ocrPython -m benchmarks.ocr_feasibility --manifest $corpus --split calibration --minimum-accuracy 95 --output C:\dev\Trilingua\output\acceptance\hybrid-pdf\calibration.json
& $ocrPython -m benchmarks.ocr_feasibility --manifest $corpus --split held_out --minimum-accuracy 95 --output C:\dev\Trilingua\output\acceptance\hybrid-pdf\held-out.json
```

The evaluator must load the recorded binary/data configuration and include fingerprints. A HOLD/NO-GO is recorded as such. These commands do not activate their reports in the application; genuine passing evidence is reviewed before normal approved deployment/configuration.

### P3 — isolated mask/font/layout slice

```powershell
Set-Location C:\dev\Trilingua\trilingua-code
& $ocrPython -m pip install 'numpy==2.4.6' 'opencv-python-headless==4.13.0.92'
& $ocrPython -m pip check
& $ocrPython -m pytest Model/tests/test_pdf_image_layout.py Model/tests/test_pdf_region_classification.py Model/tests/test_hybrid_fonts.py -q
```

OpenCV is the only proposed new image-processing dependency. The candidate pin must pass this environment's checks before entering normal requirements; no GUI OpenCV variant is installed alongside it. Pure renderer tests use known geometry/approved translations. Any integrated OCR test must receive a genuine accepted report through the ordinary configuration; missing evidence must remain HOLD, not be patched away. A bounded live translation smoke is optional only after recording the existing provider's cost/allowance impact and user-approved test inputs; no paid OCR or cloud image editing is proposed.

### P4/P5 — regeneration, UI and full regression

```powershell
Set-Location C:\dev\Trilingua\trilingua-code
& $ocrPython -m pytest Model/tests/test_pdf_hybrid_regeneration.py Model/tests/test_pdf_image_layout.py Model/tests/test_pdf_region_classification.py Model/tests/test_regeneration.py Model/tests/test_regression.py -q
php vendor/phpunit/phpunit/phpunit tests/Feature/HybridPdfPartialOutputTest.php tests/Feature/DocumentPreviewTest.php tests/Feature/Admin/TranslationManagerRegenerateTest.php --no-progress
# Planned browser test; use the project's existing browser-test runtime.
$env:TRILINGUA_PLAYWRIGHT_MODULE = 'C:\Users\walbe\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright'
node --test tests/browser/hybrid-pdf-review.test.mjs
npm run build
```

The bundled Playwright directory and installed Chrome path were verified on this PC; the proposed browser test must follow the existing `TRILINGUA_PLAYWRIGHT_MODULE` convention. No browser framework install is required. P5 extends the same fixture suites and must rerun the relevant held-out evaluator categories. Final authenticated upload → queue → review → edited regeneration → download verification is separate from unit tests. Start the Python service explicitly with the approved environment only during that approved pilot, and do not interrupt an active job or launch a second service on the occupied port.

P4 Linux font/layout parity, in a Linux checkout **after the approved font assets and tests exist**:

```bash
cd /path/to/Trilingua/trilingua-code
python3.11 -m venv .venv-ocr-layout
.venv-ocr-layout/bin/python -m pip install -r Model/requirements.txt -r requirements-dev.txt 'PyMuPDF==1.27.2.3' 'pillow==12.2.0' 'pytesseract==0.3.13' 'numpy==2.4.6' 'opencv-python-headless==4.13.0.92'
.venv-ocr-layout/bin/python -m pip check
.venv-ocr-layout/bin/python -m pytest Model/tests/test_hybrid_fonts.py Model/tests/test_pdf_image_layout.py Model/tests/test_pdf_hybrid_regeneration.py -q
```

The Linux checkout path is environment-specific; no such checkout was inspected here. Pure font/layout tests need no cloud call or OCR-gate bypass. Linux end-to-end OCR additionally requires its approved Tesseract/data runtime and matching acceptance fingerprints; the current Windows report is not assumed portable evidence.

## 8. Acceptance test matrix

| Fixture | Must prove |
|---|---|
| Fully scanned PDF | Real gate HOLD until accepted; after acceptance, expected regions accounted for, original-sized searchable output, source glyphs removed only for translated regions. |
| Native page + scanned page | Native/vector/link quality retained; the scan cannot reflow the other page. |
| Caption + screenshot, same page | Caption never suppresses the image candidate; exactly one translation per accepted visual region. |
| Hidden correct/junk OCR layer | Hidden text does not qualify as native artwork; local reconciliation, no duplicate translated/old hidden text in successfully edited regions. Held originals remain explicitly untranslated. |
| Shared/clipped/transparent/overlapping image | Correct HOLD, unchanged pixels/other occurrences and explicit reason; no global replacement. |
| Tables, columns, headers/footers | Stable order, cell/label grouping, rules/borders preserved, no cross-cell masking. |
| Rotation/cropbox + simple straight outlines | Inverse transforms round-trip; no painting in wrong coordinates. Outlined glyph paths must be isolated and actually removed before claiming replacement; otherwise HOLD. |
| Uniform white/color vs texture/gradient/photo/curved lettering | Flat backgrounds pass only after calibration; deferred classes remain original and flagged, including in the download summary. |
| All six language directions | English↔Cebuano, English↔Filipino, Cebuano↔Filipino; independent translation checks, glyph/diacritic coverage, shorter/longer paragraphs. Recognition gate remains per source-language/input category. |
| Low confidence / wrong high-confidence OCR | No destructive edit based on confidence alone; genuine evidence and local safety checks required. Missed text appears in recognition scoring. |
| Overflow / provider failure / missing font | Hold region, original intact, translated count excludes it, no strict-mode continuation or truncation. Image body text never below 10 pt. |
| Regeneration/hash/version changes | Zero OCR/provider calls; no temp paths; deterministic background; mismatch rejects; no-fit edit preserves last published output. |
| Native-only + historical sidecars | Native regression remains intact; historical reflow records keep their old reconstruction behavior. |
| Resource/malformed/encrypted input | Bounded allocation/time/processes, explicit failure/hold, no corrupted or half-erased published output. |

Final validation reopens and renders each result, checks target-text extraction/search, clipping/collisions, source-glyph residuals, unchanged pixels outside masks, unmodified native/vector/link content and accurate completeness. Validate old hidden text/obsolete image resources for edited areas as well as visible appearance. Known fixture translations isolate geometry tests; live-provider results are assessed separately. A text-coverage pass never substitutes for linguistic or visual acceptance.

## 9. Main risks and mitigations

| Risk | Mitigation |
|---|---|
| Corpus is too small/easy, references wrong, or Tesseract fails a category | Independent image-checked references, split by source content, missed-region accounting and worst-case reporting; expand failing slices; never lower 95% or promise a release date from code completion. |
| Wrong masks/transforms damage original content | Preflight + isolated assembly; tight masks and exclusion zones; outside-mask/held-region pixel comparisons; hold ambiguous occurrence/path ownership. |
| Partial output is presented/counted as fully translated | Durable region statuses, separate execution/content state, translated-only counters, partial/untranslated filenames and warnings across status/history/review/regeneration. |
| Font/fit or regeneration drifts across OS/version | 10 pt image-body floor, glyph checks, versioned licensed font files and render plans, source hashes; strict fit failures retain originals/last published file. |
| Existing dirty checkout/regressions or unbounded PDF work | Preserve unrelated changes, baseline before edits, focused legacy/native tests, one isolated PDF worker, explicit limits and deadline checks. |

**Before deployment:** confirm the existing PyMuPDF/MuPDF AGPL/commercial arrangement and font embedding/redistribution rights. The [publisher license options](https://pymupdf.io/licensing) are a dependency constraint; this plan does not make a legal compliance determination or purchase a license.

**Remaining inputs, not reopened decisions:** who can provide permission-cleared representative documents and independently check/sign off the reference set; and confirmation of the existing deployment license arrangement. No further architecture choice is needed to begin P1 after plan approval. Operational threshold/shrink/budget numbers remain provisional until calibration/benchmark review, not excuses to bypass HOLD.

## 10. Verified existing-code source map

These are claims about current code, not assertions that the proposed features already exist:

| Existing fact | Source |
|---|---|
| Any native blocks suppress same-page image OCR; page-only rotation handling | [ocr_extractor.py:171–213](C:/dev/Trilingua/trilingua-code/Model/document/ocr_extractor.py:171) |
| Gate validates at least 95% and matching evidence/settings/packs | [ocr_extractor.py:71–97](C:/dev/Trilingua/trilingua-code/Model/document/ocr_extractor.py:71) |
| OCR line grouping, fixed style, uncertain words and `ocr_reflow` | [ocr_extractor.py:123–149](C:/dev/Trilingua/trilingua-code/Model/document/ocr_extractor.py:123) |
| Existing 40 MP cap / 60-second recognition timeout | [ocr_extractor.py:13](C:/dev/Trilingua/trilingua-code/Model/document/ocr_extractor.py:13), [ocr_extractor.py:119](C:/dev/Trilingua/trilingua-code/Model/document/ocr_extractor.py:119) |
| Existing translator routes and unit IDs/context/geometry | [document_pipeline.py:475–502](C:/dev/Trilingua/trilingua-code/Model/pipeline/document_pipeline.py:475), [unit_adapters.py:53–74](C:/dev/Trilingua/trilingua-code/Model/pipeline/unit_adapters.py:53) |
| Native fitting can create continuation pages; source images are protected | [reconstructor.py:1505–1554](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:1505), [reconstructor.py:1615–1622](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:1615) |
| Any OCR reflow block selects new A4 text output | [reconstructor.py:1955–2006](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:1955) |
| Windows-specific font fallback paths / simplistic background sampler | [reconstructor.py:975–987](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:975), [layout.py:182–226](C:/dev/Trilingua/trilingua-code/Model/document/layout.py:182) |
| Version-2 sidecars and selected structural fields; reconstruction-only regeneration | [regenerator.py:18–24](C:/dev/Trilingua/trilingua-code/Model/document/regenerator.py:18), [regenerator.py:89–104](C:/dev/Trilingua/trilingua-code/Model/document/regenerator.py:89), [regenerator.py:243–258](C:/dev/Trilingua/trilingua-code/Model/document/regenerator.py:243) |
| Existing evaluator accepts only scan/photo acquisition tags and limits cases to 5–10 | [ocr_feasibility.py:65–69](C:/dev/Trilingua/trilingua-code/Model/benchmarks/ocr_feasibility.py:65), [ocr_feasibility.py:101–118](C:/dev/Trilingua/trilingua-code/Model/benchmarks/ocr_feasibility.py:101) |
| Python returns file, blocks, sidecar and validation; request temp directory is removed | [server.py:726–746](C:/dev/Trilingua/trilingua-code/Model/server.py:726) |
| PHP bridge forwards sidecar/metrics; persisted review blocks default to pending | [TranslationManager.php:205–212](C:/dev/Trilingua/trilingua-code/app/Services/Translation/TranslationManager.php:205), [BlockService.php:60–93](C:/dev/Trilingua/trilingua-code/app/Services/BlockService.php:60) |
| Empty block lists currently return before sidecar persistence | [BlockService.php:35–43](C:/dev/Trilingua/trilingua-code/app/Services/BlockService.php:35) |
| Admin regeneration overlays current database edits onto sidecar blocks | [ReviewService.php:450–465](C:/dev/Trilingua/trilingua-code/app/Services/Admin/ReviewService.php:450), [ReviewService.php:670–689](C:/dev/Trilingua/trilingua-code/app/Services/Admin/ReviewService.php:670) |
| Download payload already carries extraction warnings | [CompletedDownloadResolver.php:51–56](C:/dev/Trilingua/trilingua-code/app/Services/Translation/CompletedDownloadResolver.php:51) |
| Review already shows warnings/confidence; completion text currently asserts translation succeeded | [review-document.blade.php:68](C:/dev/Trilingua/trilingua-code/resources/views/admin/review-document.blade.php:68), [review-document.blade.php:269](C:/dev/Trilingua/trilingua-code/resources/views/admin/review-document.blade.php:269), [translation.blade.php:504–520](C:/dev/Trilingua/trilingua-code/resources/views/translation.blade.php:504) |
| Existing block counters are operational; supplied-block source counting does not certify extraction | [document_context.py:61–85](C:/dev/Trilingua/trilingua-code/Model/pipeline/document_context.py:61), [MetricsService.php:15](C:/dev/Trilingua/trilingua-code/app/Services/MetricsService.php:15), [SourceWordCounter.php:42–62](C:/dev/Trilingua/trilingua-code/app/Support/SourceWordCounter.php:42) |
| Existing browser tests accept an explicit Playwright module path | [document-preview.test.mjs:1–12](C:/dev/Trilingua/trilingua-code/tests/browser/document-preview.test.mjs:1) |

Result: implementation packages, dependencies, commands and acceptance plan specified. Checked: prior reports/options and the linked current sources. Remaining: plan approval, corpus/reference-review ownership and deployment licensing confirmation; no implementation or gate change performed.
