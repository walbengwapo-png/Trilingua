# TriLingua document handling findings and implementation plan

- **Date:** 19 October 2026, Asia/Manila.
- **Scope:** Spreadsheet formula loss, unsafe document previews and incomplete OCR.
- **Status:** Planning only. Application code and manuscript remain unchanged.
- **Basis:** Current source reinspection plus the offline probes documented in the [system review](C:/dev/Trilingua/output/reviews/TriLingua_System_and_Manuscript_Gaps_2026-10-19.md). Those probes were not rerun for this plan.
- **Deferred:** Educational evaluation, terminology approval, score calibration, broader formatting assessment, study-data controls and operational provenance/pilot work. Their specifics were saved in a memory update note at the user's request. Model naming remains set aside.

## 1 Detailed findings

### A Spreadsheet formula loss

- **Expected behavior:** Translate text cells while preserving formulas, numbers, references, sheets and supported formatting.
- **Confirmed cause:** [translate_xlsx_inplace](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:359) opens the editable workbook with `data_only=True`, which reads stored calculation results instead of formula expressions.
- **Confirmed example:** The earlier synthetic workbook had `A1 =SUM(1,2)`; the output contained an empty A1. Its translated text cell remained present.
- **Affected paths:** Initial XLSX translation and regeneration after administrator edits call the shared writer. The [XLSX extractor](C:/dev/Trilingua/trilingua-code/Model/document/extractor.py:878) also reads cached values and needs a matching formula-exclusion rule.
- **Consequence:** A file can appear successfully translated while its calculations are removed or replaced by fixed values.
- **Required result:** Preserve formula expressions and translate genuine text cells only. Formula preservation does not mean Python has recalculated Excel's results.

### B Unsafe document previews

- **Expected behavior:** Display uploaded content without permitting document-supplied active HTML or unsafe links.
- **Confirmed cause:** [document-preview.js](C:/dev/Trilingua/trilingua-code/resources/js/document-preview.js:211) inserts converter output through `innerHTML` without sanitizing it.
- **Confirmed example:** The installed DOCX converter retained a harmless `javascript:void(0)` hyperlink. No script was executed in a browser.
- **Affected paths:** The shared preview renderer and every user/admin page that mounts it. Other converter outputs using that insertion boundary need the same protection.
- **Consequence:** An uploaded document can expose a reviewer to active content in the application's origin. Account compromise was not demonstrated.
- **Required result:** Preserve permitted document markup while rejecting active elements, event handlers and unsafe URL schemes.

### C Incomplete OCR coverage

- **Expected behavior:** Extract the text needed for translation from supported scans and photographed worksheets without silently skipping text-bearing pages or regions.
- **Confirmed gaps:** PNG/JPEG are excluded from upload support; PDF OCR runs only when the entire document produces no native text blocks.
- **Confirmed example:** The earlier two-page PDF produced native blocks from page one and none from scanned page two. Because some blocks existed, OCR would not run.
- **Additional source limitations:** The OCR helper defaults to English; its returned blocks omit useful placement geometry; runtime requirements omit `pytesseract`; failures return an empty list. Available OCR languages and deployment binaries need verification.
- **Affected paths:** Laravel validation/content checks, capability responses and file selection, HTTP bridge, Python supported formats, extraction, OCR, reconstruction, job metadata, history/downloads, previews and regeneration.
- **Consequence:** A document can be only partially translated, and photographed worksheets cannot enter the documented workflow directly.
- **Important distinction:** Blank pages and diagrams without text are valid. Coverage checks must distinguish them from failed extraction.
- **Reconstruction constraint:** Scanned source words are embedded in image pixels. Placing translated words over the page without handling the original text can leave both visible. Text-region replacement must be checked for damage to diagrams and tables.

## 2 Detailed implementation plan

### Step 0 Preserve the baseline

- Complete this baseline before Step 1 or any other implementation work.
- Record the current changed/untracked working files; isolate implementation without discarding unrelated work.
- Keep the existing evidence report and original source documents unchanged.
- Prepare synthetic fixtures for formulas, unsafe preview links, ordinary PDFs, scanned PDFs and mixed pages. Identify the real supplied scans/photos for the later feasibility spike.
- Capture translation, regeneration and preview behavior, including native-text PDF content, reading order, geometry and rendered output under fixed settings and deterministic translation responses.
- **Completion:** Fixtures, settings and expected outputs are recorded before implementation; subsequent steps have a reproducible comparison baseline.
- **Limits:** Baseline recording is not a new defect reproduction or an accuracy claim. No baseline checks or probes have been rerun for this document revision.

### Step 1 Sanitize shared preview output

- **Priority:** Preview sanitization comes first because active content in the application origin is the highest-severity item and the smallest change.
- Map every caller of the shared preview renderer and its fallback paths.
- Use **DOMPurify** at the converter-to-DOM boundary with an explicit HTML-only allowlist; do not build a regular-expression sanitizer or modify document-supplied markup after sanitization. Follow the [DOMPurify configuration and safe-use guidance](https://github.com/cure53/DOMPurify/blob/main/README.md).
- **Allowed tags:** `p`, `br`, `div`, `span`, `h1`, `h2`, `h3`, `h4`, `h5`, `h6`, `strong`, `b`, `em`, `i`, `u`, `s`, `sup`, `sub`, `ul`, `ol`, `li`, `blockquote`, `pre`, `code`, `hr`, `a`, `table`, `caption`, `colgroup`, `col`, `thead`, `tbody`, `tfoot`, `tr`, `th`, `td`, `img`.
- **Allowed attributes:** Global `title`, `lang`, `dir`; `a`: `href`, `rel`; `img`: `src`, `alt`, `width`, `height`; `th`/`td`: `colspan`, `rowspan`, `scope`; `ol`: `start`, `reversed`, `type`; `li`: `value`; `col`/`colgroup`: `span`. Enforce element-specific attribute placement and valid bounded numeric values. Application code sets link `rel` to `noopener noreferrer`.
- **Allowed URL schemes and forms:** Link `href`: `https:`, `http:`, `mailto:` and same-origin relative/fragment references. Image `src`: same-origin `https:`/`http:` URLs, same-origin relative references, validated base64 `data:image/png`, `data:image/jpeg`, `data:image/gif` or `data:image/webp`, and application-created/tracked `blob:` URLs only. Reject all other schemes and untracked blob URLs; external image URLs are excluded.
- Remove event handlers, inline `style`, document-supplied `id`/`name`, extra `data-*`/ARIA attributes, scripts, forms, frames, embedded objects, SVG, MathML and all unlisted tags/attributes. Use application-owned styling for permitted content.
- Keep plain text and block fallback paths escaped; verify ordinary links, headings, tables, permitted images and navigation continue working.
- **Server-side consumers:** The reviewed converter path runs in the browser; other HTML consumers remain unverified until mapped. No server-side sanitizer is needed for a path that only stores or streams the original binary. Any server-rendered HTML, HTML export or other consumer of converter output must independently sanitize server-side using the same policy; browser DOMPurify and client claims of prior sanitization are insufficient for those consumers.
- Test encoded/mixed-case unsafe URLs, malicious attributes, SVG/data-URL payloads, untracked blobs, safe links, normal DOCX tables, permitted raster images and conversion failures.
- Run the frontend build and inspect user/admin previews in the browser using harmless attack fixtures.
- **Completion:** The explicit policy is enforced; unsafe content cannot become active in tested previews; legitimate previews and fallbacks remain usable; other converter-output consumers are identified and protected where required.
- **Limits:** This fixes the identified preview boundary, not every possible application security issue. Library integration, consumer mapping and browser tests are planned, not completed.

### Step 2 Preserve spreadsheet calculations

- Open editable workbooks with formulas retained.
- Use an explicit formula-cell exclusion rule consistently in text collection, translation and regeneration, including array/shared formula representations.
- Keep numeric/date cells, merged ranges, sheet names and supported formatting intact.
- Ensure translated strings beginning with a formula marker remain text rather than becoming new formulas.
- Check standard formulas, cross-sheet references, **array formulas**, **shared formulas**, formula-only sheets, ordinary text and literal text beginning with `=`. Verify the affected ranges and formula behavior even if shared formulas are serialized differently.
- Reopen both initially translated and regenerated files; compare formula expressions, array ranges and nontranslated values with the originals.
- **Formula-cache behavior:** Workbooks saved by this formula-preserving path have no newly calculated cached results until Excel recalculates and saves them. Non-recalculating viewers and `data_only=True` readers may therefore show blanks. Formula preservation does not calculate results; [openpyxl does not evaluate formulas](https://openpyxl.readthedocs.io/en/stable/simple_formulae.html).
- Check the application's own XLSX preview before and after recalculation. If cached results are absent, show the formula or an explicit recalculation-needed state; do not present a blank result as lost data or invent a calculated value.
- **Completion:** Formula expressions and array/shared formula semantics survive initial translation and regeneration; ordinary text translates; the application's preview handles missing cached values explicitly.
- **Limits:** Do not promise new support for macros, unsupported workbook features or calculation-engine behavior. Cached result display remains dependent on recalculation by Excel or another verified compatible calculation engine.

### Step 3 OCR feasibility spike

- **Status:** Planned investigation only; no OCR spike has been run for this revision.
- Select **5 to 10 real supplied scans and photos**, covering English, Filipino and Cebuano where represented, clean scans and difficult phone photos. Record file IDs, language segments and input conditions without altering originals.
- Record the actual Tesseract binary/version, installed language-pack identifiers and versions/checksums where available, using the installed language-data inventory. Test English, Filipino and Cebuano language data **if present**; record unavailable packs/languages explicitly instead of assuming support from a translation-language name.
- Prepare manually checked reference transcriptions for each tested language segment. Run OCR using the installed language packs; record settings and preprocessing separately for reproducibility.
- Record per-file and per-language character error rate, word error rate and word accuracy, separated by scan versus photo. Define word accuracy as `100 * max(0, 1 - WER)`, retaining the underlying WER as well. Do not hide a weak language or photo cohort behind an overall mean.
- **Owner-set minimum:** `[OWNER_SET_MINIMUM_OCR_WORD_ACCURACY_PERCENT]`. Set it before judging the results; apply it to each proposed supported language/input category.
- **Go/no-go:** Record a decision for each language/input category. Proceed to OCR 3a only for categories meeting the threshold. Missing packs, missing representative inputs/reference transcriptions or inconclusive results remain on hold.
- **If the threshold is not met:** Document the alternatives before OCR 3a begins: evaluate a different OCR engine, restrict the supported language/input scope, or defer OCR for that language. Record the owner's selected alternative; do not silently change engines or scope. A new engine requires another measured spike.
- **Completion:** The 5-to-10-file evidence set, real installed-pack inventory, per-language accuracy results, owner-set threshold and explicit go/no-go decisions are recorded.
- **Limits:** Results apply only to tested languages, packs and input conditions. They do not establish translation accuracy or general handwriting support. Real input selection, transcriptions, threshold and outcome remain unverified/pending.

### OCR 3a: page-level OCR for accepted PDFs

- **Dependency:** Begin only after the feasibility spike records a go decision for the intended language/input scope.
- Declare `pytesseract`, document the required Tesseract binaries and language data, and add a readiness check that reports missing dependencies or packs clearly.
- Detect native-text versus scan-only pages individually. Retain the existing native-text extraction path and OCR scan-only pages with the approved language configuration.
- Normalize OCR coordinates, page orientation, grouping and reading order into the existing block format.
- Parse confidence robustly; retain information about rejected/uncertain text instead of silently discarding it. Keep OCR confidence separate from translation AI-review scores.
- Classify every page explicitly as **extracted**, **blank/nontext**, **uncertain** or **failed**, with reasons. Identify mixed pages requiring region-level work as uncertain rather than reporting their native-text subset as complete.
- Carry normalized OCR blocks and page classifications through review, sidecar storage and regeneration, preserving stable content mapping after edits.
- For scan-only output before OCR 3b, use clearly separated translated text through the existing readable reflow/continuation path, or hold unsupported layouts. Do not superimpose translations over visible original scanned words or claim in-place replacement is complete.
- Test scan-only PDFs, documents combining native-text pages and scanned pages, rotated scans, low-quality scans, missing dependencies and genuinely blank/nontext pages.
- **Acceptance criterion:** Native-text PDF output is **unchanged against the Step 0 baseline fixtures**, using the same settings and deterministic translation responses; compare content, block order, layout geometry and rendered appearance rather than incidental timestamps/file metadata.
- **Completion:** Approved scan-only pages retain required text and reading order; page outcomes and uncertainty are explicit; review/regeneration preserve block mapping; the native-text baseline acceptance criterion passes.
- **Limits:** This step does not OCR image regions on mixed pages or replace source words inside scan pixels. Those capabilities belong to optional OCR 3b; unsupported mixed regions must remain visible as incomplete/uncertain.

### Step 4 Add direct image uploads after the output-format decision

- **Decision required:** Choose translated PDF or editable DOCX for PNG/JPEG inputs. PDF can reuse more of the existing page-oriented output path; DOCX emphasizes editability and requires different layout reconstruction.
- **Dependencies:** Image support depends on OCR 3a quality and the spike's language/photo outcomes. Photographed worksheets are the hardest OCR case in this scope; a clean-scan pass is insufficient to enable phone-photo support.
- Add PNG/JPG/JPEG consistently to Laravel and Python capability/validation contracts and the upload interface.
- Verify decoded image type, dimensions and orientation; set bounded pixel/page/resource limits and reject corrupt or disguised files.
- **Image preprocessing:** Cover deskew, perspective correction, contrast/lighting normalization and minimum/maximum resolution limits. Record the transforms and map OCR coordinates back to the output geometry; do not assume preprocessing can recover unreadable source detail.
- Normalize images into the selected existing document path while preserving the user's original upload for history/reprocessing.
- Reuse OCR 3a and avoid introducing a second independent translation pipeline. Before OCR 3b, use a clearly separated translated layout rather than overlaying original scanned words.
- Update output extension/MIME, stored filenames, previews, download handling, retranslation and edited regeneration for image sources.
- Add real supplied fixtures for **skewed**, **shadowed** and **angled phone photos**, alongside clean scans, corrupt images and oversized inputs. Evaluate the preprocessed photo categories against the spike threshold.
- Confirm current DOCX/PDF/XLSX and other accepted formats continue to behave as before.
- **Completion:** Photos in the approved language/quality scope meet the OCR threshold and complete upload, queue, translation, review/regeneration and download in the chosen format; failed or unreadable photos have explicit outcomes.
- **Limits:** Handwriting and additional image formats are not assumed included. Image upload support does not promise original-photo layout preservation or scanned-word replacement before OCR 3b.

### OCR 3b: region-level OCR on mixed pages and scanned-text replacement

- **Status:** Optional/deferrable; schedule after OCR 3a and image support, with its own decision gate.
- **Decision point after OCR 3a ships:** Review measured extraction quality and representative mixed-page demand. Record whether to proceed with OCR 3b or defer it. If deferred, retain explicit mixed-region limitations and use separated translated layouts; do not claim mixed-page OCR or scanned-text replacement is supported.
- Detect and OCR text-bearing image regions on pages that also contain native text. Deduplicate overlapping native/OCR detections and merge them into a coherent reading order.
- Remove or cover original scanned words before placing translated text, using masks derived from recognized text regions and mapped coordinates.
- Preserve table rules, figures, diagram labels/relationships and surrounding artwork; identify cases where removal cannot be performed safely.
- Carry region mappings, replacement metadata and uncertainty through review, sidecar and regeneration.
- **Acceptance test:** On real mixed-page and scanned worksheet fixtures, required text is accounted for exactly once, original scanned words do not remain visibly underneath translated replacements, reading order is correct, and before/after render comparisons show no new damage to tables or diagrams. Repeat after administrator edits/regeneration; native-text baseline checks must still pass.
- **Completion:** The proceed decision is recorded and the dedicated mixed-region/replacement tests pass, or the owner explicitly records deferral and the supported-scope limitations remain enforced.
- **Limits:** Geometrically successful masking does not establish semantic correctness or preservation of every arbitrary layout. Uncertain replacement cases must be held or use the clearly separated output path rather than destructive masking.

### Step 5 Verify and deliver the combined change

- Run focused workbook, preview and OCR regression checks; then the existing relevant backend/frontend suites and build.
- Exercise real queue processing and authenticated history/download/review flows in an isolated environment.
- Compare original/output files visually, confirm formula preservation by reopening workbooks, and check the application's formula-cache preview behavior.
- Run a fresh translation smoke check only after deterministic checks, capped at **3 documents total**: one XLSX, one DOCX and one approved scanned-PDF or photo fixture. Do not automatically expand or repeat this run.
- **Before running:** Record the selected files, provider/configuration, estimated request/token usage and monetary cost, including analysis, review, fallback and bounded retries. If cost cannot be estimated, leave the smoke check unrun until a cost estimate is recorded. Record actual usage/cost afterward where reported; unknown values remain unknown.
- Report each format/path as passed, failed or unverified. Preserve historical evidence rather than overwriting it.
- Document required OCR installation/configuration, approved language/input scope, the chosen image-output behavior and the OCR 3b proceed/defer decision.
- **Completion:** Sanitization, spreadsheet preservation, spike-approved OCR 3a and enabled image paths meet their acceptance conditions; OCR 3b is either verified or explicitly deferred; affected end-to-end paths and pre-run smoke cost have recorded evidence.
- **Limits:** Three smoke documents are a bounded integration check, not evidence of general translation accuracy, completed UAT or full production readiness. No application tests, OCR spike or translation probes were run for this planning-document revision.

## 3 Concise summary

- **Baseline first:** Preserve originals and record deterministic outputs before any implementation.
- **Protect previews:** Use DOMPurify with explicit tags, attributes and URL rules; independently protect any server-side HTML consumers.
- **Protect calculations:** Preserve standard, array and shared formulas; handle missing cached results explicitly in previews.
- **Measure OCR feasibility:** Test 5 to 10 real supplied scans/photos, inventory installed language packs and record per-language accuracy against the owner-set minimum.
- **Ship OCR 3a:** OCR scan-only pages, preserve coordinates/order, report page outcomes and keep native-text PDF output unchanged against the baseline.
- **Add photo support:** Choose PDF or DOCX output, apply the specified preprocessing and enable only spike-approved photo/language categories.
- **Gate OCR 3b:** Mixed-page region OCR and scanned-text replacement are optional; proceed only after an explicit decision following OCR 3a shipment.
- **Verify within bounds:** Run regression/visual/end-to-end checks, then at most 3 fresh smoke documents with cost recorded before execution.
- **Recommended order:** Step 0 baseline, sanitization, spreadsheet formulas, OCR feasibility spike, OCR 3a, image support, OCR 3b (optional, decision-gated), final verification.
- **Remaining decision:** Image output format; `[OWNER_SET_MINIMUM_OCR_WORD_ACCURACY_PERCENT]`; per-language/input spike go/no-go outcome and alternatives if it fails; OCR 3b proceed/defer decision after OCR 3a ships.
- **Status:** Planning document revised; Section 1 is unchanged; application code and manuscript are unchanged. No probes were rerun.

## Changelog

- Moved sanitization before spreadsheet repair and explained its severity/scope priority; kept Step 0 first.
- Specified DOMPurify, its intended allowlist and the server-side consumer requirement.
- Added array/shared formula coverage and cached-result/application-preview checks.
- Added a 5-to-10-file OCR feasibility spike with installed-pack inventory, per-language accuracy, an owner-set threshold and explicit go/no-go alternatives.
- Split page-level OCR 3a from optional, decision-gated mixed-region/replacement OCR 3b; added native-text baseline acceptance.
- Strengthened image support dependencies, preprocessing and difficult phone-photo fixtures.
- Capped the fresh smoke check at 3 documents and required cost recording before execution.
- Updated the summary, recommended order and remaining decisions; preserved all Section 1 findings and made no probe-rerun claims.
