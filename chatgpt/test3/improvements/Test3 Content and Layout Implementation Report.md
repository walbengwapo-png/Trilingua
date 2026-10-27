# TriLingua Content and Layout Implementation Report

Date: 5 October 2026. Approved overflow policy: controlled reflow and extra pages.

Implementation completed locally. 176 focused tests passed. All eight saved-translation PDF replays passed complete-block placement, saved-text coverage and text geometry checks. This is a rendering and guard verification result; linguistic accuracy and full end-to-end operation remain unverified.

## Implemented behavior

| Change | Resulting behavior |
| --- | --- |
| Complete text and overflow | Measure complete blocks; use a minimum 8-point translated font and bounded shrinking. Move overflow to readable continuation pages immediately after the source page. No silent word truncation in the preserved PDF route. |
| Rotation and geometry | Normalize displayed coordinates for extraction and reconstruction. Transform legacy sidecars once; preserve normalized coordinates in new sidecars. Native tests cover 90, 180 and 270 degrees. |
| Roles, styles and artwork | Separate heading-size changes and bullet starts. Retain mixed bold/italic runs. Avoid text, images, vector illustrations, table rules and panel edges. Protect passthrough glyphs from redaction padding. Darken pale text on white continuation pages and contrast navigation against its background. |
| Shared content acceptance | Reject recognized conversational replies, empty translations and missing literal URLs/numbers/placeholders. Apply checks to primary, batch, fallback, repair, cache reuse, glossary processing and final document blocks. Keep valid initial text when a repair is invalid. Preserve language-name labels. |
| Saved-output gate | Reopen the actual PDF, verify complete block placement and each saved fragment, then check bounds, orientation and text overlap. Failed checks raise a structured HTTP 422 on translation or regeneration. Successful document responses and sidecars carry validation and rendered fragment metadata. |

The existing provider routes, default legacy pipeline selection and startup workflow were retained. No new dependency was installed. The PyMuPDF minimum was raised to 1.26.4 for the native PDF operations; verification used installed version 1.27.2.3. Obsolete truncation-era reconstruction helpers were removed.

## Verification and document results

The replay reused each original file's existing translation and language direction. It called no translation providers and did not change originals, historical translated PDFs or the original evaluation report. Extra pages apply to outputs; the original 2–10-page input restriction remains satisfied.

| Document | Direction | Pages: source / output | Saved-PDF gate |
| --- | --- | --- | --- |
| 01 CFPB Spending Tracker | EN to CEB | 4 / 8 | PASSED |
| 02 OSHA Working in the Heat | EN to CEB | 4 / 8 | PASSED |
| 03 CDC Inactive Tuberculosis | EN to FIL | 2 / 4 | PASSED |
| 04 FTC Avoiding Scams | FIL to CEB | 2 / 4 | PASSED |
| 05 FTC Immigration Scams | FIL to EN | 5 / 10 | PASSED |
| 06 FTC Tech Support Scams | FIL to CEB | 2 / 4 | PASSED |
| 07 CDC Hindi Aktibong Tuberculosis | FIL to EN | 2 / 5 | PASSED |
| 08 Ang Wikipedya | CEB to EN | 2 / 4 | PASSED |

Total: 23 source pages and 47 output pages. Output PDFs total 6.86 MB, compared with 39.52 MB for the historical outputs. This matched comparison isolates reconstruction; it does not measure fresh provider translation quality or latency.

Focused checks cover rotation, complete overflow text, numeric and URL literals, saved-PDF corruption detection, lost-block detection, redaction neighbors, vector obstacles, white panel text, bad batch responses, invalid quality/coherence repairs, glossary loss, regeneration isolation, response/sidecar metadata and structured endpoint failures. The endpoint tests use mocks; they do not exercise Laravel or live HTTP.

Broader run: 227 passed and 7 failed across 234 tests. The chunk-boundary failure was a Hypothesis input-generation speed check and passed in an isolated recheck. Six Gemini-analysis tests still fail against old mock response/model expectations. Their source files and the analysis/chunking implementation hashes match the saved pre-change manifest. These failures were recorded without changing the unrelated implementation or tests.

All current output pages were rendered and inspected in contact sheets, with full-page/crop checks of identified problems. The main CFPB icon loss was corrected. Of 24 icon regions, 20 were pixel-identical at 2x; two further regions were identical at 4x. Two regions differ at 4x, including clipped edge artwork and an adjacent rule. Exact artwork fidelity is not certified.

## Limits and remaining verification

An automated PASS means the supplied target text was placed and recovered with acceptable text geometry. It does not mean the translation is correct, all source material was extracted, tables retain every semantic relationship, or the design is visually identical.

Six historical blocks are flagged by the new content guard: one input-request reply in file 04, four in file 05, and a missing numeric literal in file 08. These bad historical targets were deliberately retained in reconstruction stress outputs. Fresh pipeline processing rejects or retries recognized invalid content; rendering an old sidecar does not retroactively translate it. The earlier file 08 lexical mistranslation remains in its replay and is outside the literal guard's capabilities.

The conservative reflow produces fragmented layouts and blank original slots, especially in the spending forms and old sidecars with sentence fragments. Overflow text appears on following pages, and navigation is added only where it fits. Old source extraction and block boundaries are retained for regeneration compatibility. The saved-text gate does not certify contrast on every arbitrary background, source clipping masks, reading-order semantics, table association, PDF accessibility tags or general wrong-language detection.

MuPDF emits a structure-tree diagnostic for file 02 during native operations. Its output opens, renders and passes the text/geometry gate, but PDF tag/accessibility integrity remains unverified. Pre-existing clipped source artifacts are explicitly listed in validation metadata rather than treated as newly omitted translated text.

Remaining: a fresh live provider and Laravel upload/queue/download run; bilingual review; confirmation that the conservative continuation layout is acceptable for the forms; the six unrelated Gemini mock failures; and PDF structure/accessibility verification for file 02. No service restart, deployment, commit or production promotion was performed.

### Evidence and reproduction

Evidence is under chatgpt/test3/improvements: replay-results.json, verification.json, focused-tests.log/XML, local-tests.log/XML, chunk-recheck.log/XML, replay.log, eight reconstructed PDFs, rendered page PNGs, contact sheets and icon-differences.png. Historical evidence remains under chatgpt/test3/evidence.

Offline replay: run chatgpt/test3/verify_improvements.py with the installed Python 3.11 runtime. It overwrites only the new improvements artifacts. Do not rerun run_test3.py over historical evidence. Focused test modules: test_pdf_content_layout, test_translation_fallback, test_cache_namespace, test_block_quality, test_unit_pipeline, test_regeneration and test_regression. Run with TRANSLATION_CACHE_ENABLED=false.

Native rotation behavior reference: https://pymupdf.readthedocs.io/en/latest/page.html#Page.remove_rotation. The source hashes, precise assertions and replay details are the authorities for the local results above.
