# TriLingua document handling implementation report

- **Date:** 19 October 2026, Asia/Manila.
- **Result:** Preview sanitization and spreadsheet formula preservation are implemented and locally verified. OCR feasibility is on hold; page-level OCR, image uploads and optional region-level OCR have not been enabled.
- **Approved basis:** [Document handling implementation plan](C:/dev/Trilingua/output/reviews/TriLingua_Fix_First_Detailed_Plan_2026-10-19.md).
- **Owner decisions received:** Minimum OCR word accuracy is **95% for each tested language/input category**; PNG/JPEG translated output is **PDF**. Public internet sources may be collected and organized for the spike.
- **Preservation:** The manuscript, approved plan and prior findings report were not edited. Existing unrelated working changes were preserved. No commit, deployment, production migration or service restart was performed.
- **Evidence directory:** [Local checks and source snapshots](C:/dev/Trilingua/output/reviews/document-handling-2026-10-19).

## 1 Findings and current status

### A Unsafe converted document previews

- **Confirmed before the fix:** A real synthetic DOCX passed through the installed converter and shared browser renderer retained a `javascript:` link. The new browser regression failed with one unsafe link present; no unsafe script was executed.
- **Implemented:** DOMPurify 3.4.16 sanitizes converter HTML immediately before insertion into the shared preview. The sanitizer has explicit tag, attribute and URL policies.
- **Confirmed after the fix:** The original browser regression passes. Seven additional browser checks cover active elements, attribute placement, unsafe/encoded URLs, raster image restrictions, XLSX result display, plain-text/CSV escaping and block fallback.
- **Unverified:** Actual authenticated user/admin browser sessions against the running application were not exercised. Laravel route/view/authorization checks and the shared renderer were tested separately.
- **Scope limit:** The separate third-party PPTX viewer and the PDF viewer were not security-certified by this converter-HTML change.

### B Spreadsheet formula loss

- **Confirmed before the fix:** Five of six new workbook regressions failed. Formulas became empty cells after saving, including formulas reached through regeneration and shared/array formula cases.
- **Implemented:** Workbook extraction and editing retain formula expressions, exclude actual formula cells from translation and retain formula-like literal text as text.
- **Confirmed after the fix:** All six workbook checks pass, including initial translation, edited regeneration, array formulas, shared formulas, formula-only writer behavior and missing result caches.
- **Implemented preview behavior:** The application shows uncached formulas with a recalculation notice. A stored numeric result remains visible when one exists.
- **Unverified:** Excel recalculation itself was not run. Python does not calculate spreadsheet formulas; this change preserves the expressions rather than producing their results.

### C OCR feasibility and image support

- **Confirmed decisions:** The owner selected a 95% threshold and PDF image output.
- **Confirmed preparation:** Eight source candidates are organized with language/input labels, availability and limitations. Two official English scan/reference pairs were downloaded, along with an author photo overview and two low-resolution photo candidate crops.
- **Incomplete evidence set:** Four Filipino/Tagalog or Cebuano scan sources were located but their image downloads remain unresolved. The photo crops are not acceptance-ready full-resolution images. The upstream English references have not received complete local transcription verification.
- **Runtime limitation:** Tesseract was not found on PATH or in the conventional installation locations inspected; `pytesseract` was unavailable in the inspected Python runtime. The installed language-pack inventory could not be obtained and remains **unknown**, not confirmed empty.
- **Approval limitation:** Automatic approval review rejected the combined Tesseract download-and-install action with **blocked by policy**. No specific reason was provided. The rejected installer action was not executed or retried.
- **Measured result:** **0 OCR calls and 0 live translation-provider requests.** Per-language accuracy is **not measured**. The spike status is **HOLD**, not an accuracy failure and not a pass.
- **Dependency consequence:** OCR 3a, direct image uploads and OCR 3b remain gated. Existing OCR behavior has not been represented as fixed.

## 2 Implementation and verification by step

### Step 0 Preserve the baseline

- Recorded a manifest of **317 existing source/configuration/test files**, the manuscript hash and the approved-plan hash.
- Saved the initial working-tree listing and before-copies of the five existing files changed by this implementation.
- Created a deterministic two-page native-text PDF fixture and retained its extracted blocks, output text, geometry and rendered pixel hashes.
- Recorded the preview and spreadsheet regression failures before applying their fixes.
- Verified afterward that only the five intended existing files changed; all other recorded source hashes, the manuscript and approved plan remained unchanged.
- **Completion:** Baseline and preservation evidence are recorded. The two-page native-text fixture has identical text, geometry and rendered pixel hashes after the changes.
- **Limits:** This is a small native-text regression fixture, not proof of preservation across all real PDF layouts or educational documents.

### Step 1 Sanitize shared preview output

- **Priority followed:** Preview sanitization was implemented first because active content in the application origin is the highest-severity item and the smallest change.
- **Changed paths:** [Shared preview renderer](C:/dev/Trilingua/trilingua-code/resources/js/document-preview.js:1), [sanitizer policy](C:/dev/Trilingua/trilingua-code/resources/js/preview-sanitizer.js:1), package manifest and lockfile.
- **Dependency:** DOMPurify 3.4.16 was installed; the lockfile records its integrity. The baseline-relative dependency change contains DOMPurify and its optional trusted-types declarations, without unrelated dependency upgrades.
- **Allowed tags:** `p`, `br`, `div`, `span`, `h1`, `h2`, `h3`, `h4`, `h5`, `h6`, `strong`, `b`, `em`, `i`, `u`, `s`, `sup`, `sub`, `ul`, `ol`, `li`, `blockquote`, `pre`, `code`, `hr`, `a`, `table`, `caption`, `colgroup`, `col`, `thead`, `tbody`, `tfoot`, `tr`, `th`, `td`, `img`.
- **Allowed attributes:** Global `title`, `lang`, `dir`; `a`: `href`, `rel`; `img`: `src`, `alt`, `width`, `height`; `th`/`td`: `colspan`, `rowspan`, `scope`; `ol`: `start`, `reversed`, `type`; `li`: `value`; `col`/`colgroup`: `span`. Attribute placement, enumerated values and bounded integer values are checked.
- **Allowed link forms:** Explicit HTTP, HTTPS and mailto links; same-origin relative links and fragments. All retained links receive `noopener noreferrer`.
- **Allowed image forms:** Same-origin HTTP/HTTPS or relative URLs and base64 PNG/JPEG/GIF/WebP data with matching raster signatures. External images, SVG data and forged raster data are rejected.
- **Blob policy:** The current converter has no application-managed blob registry, so all supplied blob URLs are rejected. The implementation does not permit arbitrary blobs merely because they claim the same origin.
- **Removed:** Event handlers, inline styling, document-supplied identifiers/names, unlisted data/ARIA attributes, forms, frames, scripts, SVG, MathML and unlisted tags/attributes. Trusted outer preview styling is owned by the application.
- **Server-side review:** Searches found converter HTML creation in browser code; the reviewed Laravel routes stream original/translated binaries or return blocks. No server-side converter-HTML consumer was identified in those paths, so no unused server sanitizer was introduced. Any future HTML-rendering/export consumer must independently sanitize its HTML.
- **Verification:** Eight Chrome browser regression checks pass; user/admin route and view checks are included in the 33-test Laravel run. The original real-DOCX unsafe-link test failed before and passed after the change.
- **Completion:** The identified converted-HTML insertion path is sanitized and locally verified; legitimate tested links, tables, raster images and escaped fallbacks remain usable.
- **Limits:** Browser tests run the actual shared renderer in an isolated fixture page, not a signed-in deployed application. PPTX's separate renderer and general application security remain outside this result. Safe-use reference: [DOMPurify documentation](https://github.com/cure53/DOMPurify/blob/main/README.md).

### Step 2 Preserve spreadsheet calculations

- **Changed paths:** [XLSX reader](C:/dev/Trilingua/trilingua-code/Model/document/extractor.py:878), [shared XLSX writer](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:359), [workbook preview](C:/dev/Trilingua/trilingua-code/resources/js/workbook-preview.js:1) and its shared-renderer integration.
- Opened workbooks with formula expressions retained instead of cached values.
- Excluded formula cells from extraction, translation and the existing regeneration writer. Array formula objects are also excluded from text translation.
- Retained literal text beginning with `=` and explicitly wrote translated strings as text, preventing translation output from becoming a new formula.
- Tested standard formulas, cross-sheet references, array formula ranges, shared formula semantics, numeric values, merged cells, text styling and formula-only writer behavior.
- Confirmed that regeneration preserves formulas while applying edited text through the existing sidecar mapping.
- Added a preview fallback for formulas without cached values: display the expression and explain that recalculation is needed. Browser checks also confirm that saved calculated results remain visible.
- Replaced the writer's unqualified perfect-layout log message with a factual formulas-retained message.
- **Completion:** All six new workbook regression checks pass. Actual XLSX browser preview tests cover both absent and present calculated results. Existing selected regeneration/Office checks also pass.
- **Limits:** Shared formulas may be serialized as equivalent individual expressions; original XML encoding is not guaranteed. Formula-only document acceptance was not changed at the full queued-pipeline level. No macro support or calculation engine was added. Formula caches can remain blank until Excel recalculates; [openpyxl does not evaluate formulas](https://openpyxl.readthedocs.io/en/stable/simple_formulae.html).

### Step 3 OCR feasibility spike

- **Owner settings recorded:** 95% minimum word accuracy per language/input category; PDF output; internet sample collection authorized.
- Added an [offline spike runner](C:/dev/Trilingua/trilingua-code/Model/benchmarks/ocr_feasibility.py:1). It inventories an available Tesseract binary/packs, reads checked references, records word/character errors and produces category-level go/no-go/hold outcomes without calling an LLM or enabling application OCR.
- Scoring normalizes Unicode NFC and whitespace only; punctuation, case and diacritics remain meaningful. WER is recorded as a ratio and word accuracy is `100 * max(0, 1 - WER)`.
- Missing engines, packs, images or checked references produce **hold** and no fabricated accuracy. Three regression checks verify scoring, diacritic sensitivity and missing-evidence handling.
- Organized the [eight-candidate manifest](C:/dev/Trilingua/output/reviews/document-handling-2026-10-19/ocr-samples/manifest.json): two English scans from the Tesseract test repository; two Cebuano book-page sources; two historical Tagalog page sources; two English photo candidates derived from the authors' DocUNet overview.
- Recorded language limitations: historical Tagalog is only a possible Filipino proxy; older Cebuano orthography is not representative of all modern classroom materials. Magazine pages and photo previews cannot establish worksheet accuracy.
- Recorded download limits: Wikimedia requests returned HTTP 403; the full-resolution DocUNet archive failed TLS certificate validation. TLS verification was not disabled. The downloaded photo overview is not misrepresented as a full-resolution test corpus.
- Ran the spike's prerequisite/scoring command with `--minimum-accuracy 95`; it reported **hold**, with **0 OCR calls**. Actual installed pack names/checksums and per-language recognition accuracy remain unavailable.
- **Completion:** Runner, missing-evidence tests, source manifest and explicit hold record are delivered. The measured 5-to-10-file feasibility experiment is **not complete**.
- **Limits:** An available/approved OCR runtime and a complete set of downloaded, sufficiently resolved samples with checked transcriptions are still required. If measured accuracy later falls below 95%, the owner must select a different engine and repeat the spike, restrict language/input scope, or defer that category before OCR 3a begins.

### OCR 3a: page-level OCR for accepted PDFs

- **Status:** Not started; the approved feasibility gate has not passed.
- No runtime OCR dependency, language capability, page-classification or extraction behavior was silently enabled.
- The planned implementation still requires per-page detection, coordinates/order, confidence handling, explicit extracted/blank/uncertain/failed outcomes and stable review/sidecar/regeneration mapping.
- The native-text baseline fixture remains unchanged, but this alone does not satisfy OCR 3a acceptance because no new page-level OCR was implemented.
- **Completion:** Pending a spike go decision for the intended language/input scope.
- **Limits:** The pre-existing whole-document OCR fallback and mixed-document omissions must still be treated as unresolved.

### Step 4 Add direct image uploads

- **Decision resolved:** Translated PNG/JPEG output will be PDF.
- **Status:** Not started; image support remains dependent on OCR 3a quality and measured photo-category results.
- Deskew, perspective correction, contrast/lighting normalization, resolution limits and skewed/shadowed/angled worksheet fixtures remain planned rather than implemented or verified.
- Existing upload formats were not changed to advertise unsupported image processing.
- **Completion:** Pending OCR feasibility, OCR 3a and a representative photo acceptance set.
- **Limits:** The retained low-resolution photo candidates are insufficient to certify phone-photo support; no handwriting or photo-layout fidelity claim is made.

### OCR 3b: region-level OCR and scanned-text replacement

- **Status:** Optional and decision-gated; not started.
- No region-level OCR, source-word masking or scanned-text replacement was enabled.
- The proceed/defer decision remains after OCR 3a ships, as specified in the plan.
- **Completion:** Pending that decision and, if approved, dedicated mixed-page/replacement tests.
- **Limits:** Do not claim mixed-page OCR or damage-free replacement of scanned words from this implementation.

### Step 5 Verify and deliver the combined change

- **Python:** 21 selected workbook, regeneration, DOCX and PPTX checks passed; three additional spike-runner checks passed. Total **24 passing Python checks** across these targeted runs.
- **Browser:** **8 passing checks** in installed Chrome, using the real shared renderer, real DOCX conversion and real XLSX preview fixtures.
- **Laravel:** **33 tests and 154 assertions passed** for preview routes/views, authorization, published text and draft/publication integrity. PHPUnit reported **10 deprecations**, which were not investigated in this scope.
- **Build:** Production frontend build passed. The existing large-chunk warning remains, principally involving the separate PPTX viewer; no unrelated bundle restructuring was performed.
- **Preservation:** Native baseline text/geometry/render hashes match; approved plan/manuscript hashes match; unrelated recorded source hashes match.
- **Fresh translation smoke check:** Not run. The approved maximum remains three documents. No selected live-run cost estimate was established, so no provider run was initiated. Local deterministic tests do not count as those fresh provider documents.
- **Real queue/storage pilot:** Not run; Laravel tests use their guarded isolated test configuration and mocked external operations. No live storage/provider/browser-session outcome is inferred.
- **Completion:** The two independent fixes have passing local regression/build evidence. Final acceptance of the entire document-handling plan remains incomplete while the OCR and live-pilot gates are open.
- **Limits:** These results do not establish general translation accuracy, full-format visual fidelity, completed UAT or production readiness.

## 3 Concise summary

- **Fixed locally:** Converted preview HTML is sanitized; spreadsheet formulas survive translation and regeneration.
- **Preview improvement:** Missing formula results display an expression and recalculation notice instead of an unexplained blank.
- **Verified:** 24 Python checks, 8 browser checks, 33 Laravel tests, production build and unchanged native-PDF baseline.
- **OCR decisions resolved:** 95% minimum accuracy and PDF output.
- **OCR preparation delivered:** An offline evaluation runner and eight clearly labeled source candidates.
- **OCR result:** **HOLD.** No OCR accuracy was measured; the engine is unavailable and the acceptance-ready sample set is incomplete.
- **Remaining order:** Complete the spike, obtain category-level go decisions, implement OCR 3a, implement image support, decide whether to proceed with optional OCR 3b, then finish bounded live verification.
- **Remaining decision:** The spike's eventual go/no-go outcome and any alternative if it fails; OCR 3b proceed/defer after OCR 3a ships. Threshold and image-output choices no longer need to be asked again.
- **Remaining action:** Make an approved Tesseract runtime available, complete the real scan/photo set and checked references, then run the recorded 95% gate. Any future fresh provider smoke test requires cost recorded before execution and stays capped at three documents.
- **Unchanged:** Manuscript, approved plan, provider/model selection and unrelated working changes.

## Changelog

- Added DOMPurify and an explicit shared converted-HTML policy.
- Preserved workbook formulas and formula-like literal text in extraction, translation and regeneration.
- Added honest handling of missing formula caches in the application's XLSX preview.
- Added six workbook, eight browser and three spike-runner regression checks.
- Captured the source/native-PDF baseline and verified preservation.
- Added the offline OCR spike runner, source manifest and truthful hold report.
- Recorded the approved 95% threshold/PDF decision and the unexecuted OCR/image/optional work.
- Kept the approved findings/plan intact and reported actual checks separately from pending verification.

Automatic approval review rejected the Tesseract download-and-install action with **blocked by policy** and supplied no more specific reason. That action was not executed or retried; it remains a runtime prerequisite for the planned Tesseract spike.
