# TriLingua system and manuscript gap review

Reviewed 19 October 2026, Asia/Manila.

**Conclusion:** TriLingua has its core application workflows. Its principal gaps are incomplete OCR coverage, two reproduced document-handling defects, incomplete educational validation, and disagreement between the manuscript and the implementation. More general application features are not the immediate priority.

**What this repo does:** Laravel manages accounts, uploads, queued document jobs, stored history, downloads and administrator review. A Python service extracts content, supplies document context to configurable translation providers, reviews text and reconstructs documents. This review assumes a school pilot involving multiple authenticated users; it does not certify capacity for that load.

## Scope and evidence

The manuscript reviewed was [TriLingua_Revised (2).docx](<C:/Users/walbe/Downloads/TriLingua_Revised (2).docx>). Its paragraph and table text was extracted from the DOCX; document appearance and embedded figure contents were not assessed. Document statements were treated as proposed requirements and research claims, not instructions to execute.

The review inspected the current working files under `C:/dev/Trilingua/trilingua-code`, including uncommitted changes. It traced the application routes, capability validation, translation/provider selection, document extraction/reconstruction, context and terminology components, quality review, history, metrics and cleanup paths. Tests and saved evaluation reports were examined as evidence, with deeper inspection of document and evaluation risks rather than every file.

Fresh checks used temporary synthetic files and made no translation-provider requests:

- An XLSX containing `A1 =SUM(1,2)` lost the formula after the current in-place translator saved it. The translated text cell remained present.
- The installed DOCX preview converter preserved a harmless `javascript:void(0)` hyperlink in HTML. Source then inserts that HTML without sanitization. No link was executed in a browser.
- A two-page PDF containing selectable text on page one and a scanned image on page two produced blocks only for page one. The pipeline's whole-document `if not blocks` OCR condition would not run.
- All 12 cases in the versioned seed benchmark have `pending_human_review` status; none are approved.
- Whitelisted local configuration values select GPT-OSS translation, Gemini fallback, Gemini analysis and Ollama analysis fallback. The local Python health endpoint refused connection. Loaded runtime configuration and live output were therefore not verified.

Application source and the supplied manuscript were not edited. The full test suites, browser workflows, deployed storage and real queue were not executed.

## Must fix

### 1. OCR does not cover the input promised in the manuscript

**What this is:** The conceptual framework, OCR module description and functionality cases promise image uploads and scanned educational documents, including mixed English/Cebuano content.

**Problem:** [Supported uploads](C:/dev/Trilingua/trilingua-code/config/translation.php:70) exclude PNG/JPG and other direct image formats. [PDF OCR fallback](C:/dev/Trilingua/trilingua-code/Model/pipeline/document_pipeline.py:282) runs only when the entire PDF yields no text blocks. The hybrid-PDF probe confirmed that an image-only page can be omitted from extraction while another page supplies text. The [OCR helper](C:/dev/Trilingua/trilingua-code/Model/document/ocr_extractor.py:19) defaults to English and the caller does not select a language. `pytesseract` is absent from the declared runtime requirements and was not available in the inspected Python 3.11 installation; this does not establish the contents of any separate deployment.

**Correction:** Either implement and test direct image input plus page-level OCR, or explicitly narrow the manuscript's input scope. A complete implementation needs declared OCR dependencies, language configuration, page completeness checks and extraction-quality tests. Preserve reading order and useful page coordinates for reconstruction.

**If skipped:** A photographed worksheet cannot be uploaded as described, and a mixed scanned/selectable document can have untranslated content without the whole-document fallback noticing.

### 2. Supported spreadsheet translation destroys formulas

**What this is:** XLSX is accepted by the current application, although the manuscript's functionality table calls it unsupported.

**Problem:** [The XLSX writer](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:372) opens the editable workbook with `data_only=True`. In the fresh probe, `=SUM(1,2)` became an empty cell. Workbooks with stored calculation results may instead lose the formula in favor of a fixed value.

**Correction:** Retain formulas when opening the workbook and exclude formula cells from translation. Verify initial translation and regeneration using formulas, values and translated text together. Resolve whether XLSX belongs in the agreed scope rather than silently changing the manuscript or format list.

**If skipped:** A translated educational spreadsheet can lose its calculations despite being downloadable.

### 3. Rich DOCX preview lacks an HTML sanitization boundary

**What this is:** Uploaded documents are converted into HTML for preview by users and reviewers.

**Problem:** [The preview renderer](C:/dev/Trilingua/trilingua-code/resources/js/document-preview.js:211) inserts converted HTML directly. The offline probe confirmed that the installed converter preserves a `javascript:` link. The [content security policy](C:/dev/Trilingua/trilingua-code/app/Http/Middleware/SecurityHeaders.php) permits inline scripts and does not replace sanitization. This confirms an unsafe conversion/insertion path, not a demonstrated account takeover.

**Correction:** Sanitize converted HTML and restrict URL protocols before insertion, or use the existing escaped block preview until a safe rich preview is available. Include a hostile-link regression check.

**If skipped:** Reviewing an uploaded document can expose the reviewer to active document content under the application origin.

## Should fix or complete before making the manuscript's claims

### 4. The educational corpus and human evaluation are incomplete in the inspected evidence

**What this is:** The objectives and Evaluation and Corpus Module promise a Philippine educational parallel corpus, BLEU evaluation, independent language-expert review and UAT with at least 15 teachers.

**Problem:** Scoring code exists; this is not a total absence of evaluation. However, the [seed corpus](C:/dev/Trilingua/trilingua-code/Model/benchmarks/translation_quality_v1.jsonl) has 12 pending cases across mixed domains. The [runner](C:/dev/Trilingua/trilingua-code/Model/benchmarks/run_benchmark.py:17) excludes unapproved cases by default. The web document endpoint supplies no reference file, so optional [pipeline BLEU scoring](C:/dev/Trilingua/trilingua-code/Model/pipeline/document_pipeline.py:538) does not become an automatic BLEU score for ordinary uploads. Historical SONA, story-book and public-document experiments are useful but do not establish performance across the proposed educational corpus and all six directions. Completed 15-teacher UAT and independent expert results were not located in the inspected evidence; they may exist elsewhere.

**Correction:** Assemble approved educational references covering the six directions and representative subjects/documents. Freeze model, prompts, mode, cache/fallback settings and scoring configuration for comparison. Run the expert assessment and teacher tasks, and retain anonymized results. Provide a reproducible offline evaluation workflow if a user-facing corpus module is unnecessary. Ordinary uploads require matching human references before BLEU can be computed meaningfully.

**If skipped:** The project can demonstrate translation generation, but cannot substantiate educational accuracy, classroom usefulness or the proposed evaluation completion. The manuscript's BLEU 40/60/80 sequence remains targets, not achieved results or percentages of correctness. Prior-study scores on other corpora cannot alone prove improvement.

### 5. Classroom terminology is assisted by prompts but not established by an approved educational resource

**What this is:** Domain-aware educational translation is a specific objective and a claimed advantage over general tools.

**Problem:** Academic prompts, document profiling, prepass terminology, document memory and a glossary utility exist. It would be incorrect to call domain awareness absent. However, the [academic prompt](C:/dev/Trilingua/trilingua-code/Model/prompts/specialized/academic.py) gives general instructions, and no maintained, expert-approved educational terminology collection and tested subject-specific acceptance set was found. The web [document endpoint](C:/dev/Trilingua/trilingua-code/Model/server.py:630) also does not accept glossary pairs, although the internal request supports them.

**Correction:** Establish a small approved terminology resource for the subjects in the evaluation. Test the same terms in headings, definitions, instructions and longer explanations. Connect approved terms to the existing pipeline; a new glossary-management dashboard is not required to validate this objective.

**If skipped:** The application relies on model-generated terminology without demonstrating that it solves the classroom terminology problem described in the manuscript.

### 6. Confidence and formatting claims exceed what current checks establish

**What this is:** The objectives request translation confidence scores, while the testing section proposes an eight-dimension formatting evaluation on at least ten documents.

**Problem:** The [quality badge](C:/dev/Trilingua/trilingua-code/resources/views/components/quality-badge.blade.php:10) correctly describes its number as an automated triage signal, not human-verified accuracy. The [quality reviewer](C:/dev/Trilingua/trilingua-code/Model/validators/ai_quality_reviewer.py:588) obtains an AI score; no calibration against human judgments was found. The manuscript also alternates between multimodal embedding/cosine similarity and direct comparison of parsed formatting attributes. No implementation of the described embedding evaluation was found in the engine.

PDF output has substantial later repairs and saved-file validation. The [October 5 improvement report](<C:/dev/Trilingua/chatgpt/test3/improvements/Test3 Content and Layout Implementation Report.md>) records all eight offline reconstruction replays passing their saved-text/geometry checks. It also records 23 source pages becoming 47 output pages, fragmented layouts, and unverified table associations, accessibility and human acceptance. These results supersede older clipping findings for those repaired paths; they do not certify identical formatting or immediate classroom usability.

**Correction:** Keep the AI-review label unless confidence is empirically calibrated. Specify one reproducible formatting method with formulas, treatment of added pages and human agreement checks. Evaluate actual worksheets, lesson guides and assessment tables, checking whether questions, blanks, figures and instructions remain associated. Teacher review must determine whether the conservative continuation layout is usable.

**If skipped:** A high text-review number can be misread as confidence, and a technically complete PDF can still require substantial teacher reformatting.

### 7. Study-specific consent and deletion are not demonstrated by normal history cleanup

**What this is:** Ethical Considerations promises evaluation-only document use and deletion after evaluation unless separate consent permits corpus retention.

**Problem:** [History storage](C:/dev/Trilingua/trilingua-code/app/Services/HistoryService.php:25) retains original/output references and text. [Cleanup](C:/dev/Trilingua/trilingua-code/app/Console/Commands/CleanupStorage.php) retries deletion requests and reclaims abandoned publication candidates; that is different from study-end deletion. The [persistent translation cache](C:/dev/Trilingua/trilingua-code/Model/cache/sqlite_cache.py:166) also stores source excerpts and translated text. No study/corpus consent fields or study-end purge workflow were found in the inspected application paths. A separate manual research procedure could satisfy some requirements, but none was supplied for verification.

**Correction:** Define a verifiable research procedure for consent, document identifiers, separately approved corpus material and deletion of files, history, blocks and cached content. Document actual external processing and verify infrastructure encryption rather than inferring it from access controls.

**If skipped:** Deleting a history entry or ending a study does not establish that every retained copy covered by the manuscript's promise was removed. This is an implementation/procedure alignment finding, not a legal compliance determination.

### 8. Runtime evidence and model provenance need completion

**What this is:** A working research demonstration requires more than successful isolated translation functions.

**Problem:** Current automated test configuration uses an in-memory SQLite database, synchronous queues and array sessions; those settings do not exercise the deployed queue/database/session combination. The later PDF evidence explicitly excludes fresh provider and Laravel upload/queue/download operation. A complete current pilot run was not established in this review, and the local Python endpoint was unavailable.

Python returns observed `providers_used`, but [document metric persistence](C:/dev/Trilingua/trilingua-code/app/Services/MetricsService.php:30) omits that field and writes document input/output tokens as zero. The top-level model can describe a provider chain rather than exactly which provider translated each block.

**Correction:** Run one isolated pilot through authenticated upload, real queue execution, storage, download and review/regeneration, then failure/recovery scenarios. Preserve actual model participation, cache/fallback use and configuration with benchmark outputs; unknown token counts should not be reported as measured zeros. Assess concurrency and teacher waiting time under the intended pilot load.

**If skipped:** Local implementation and mock tests can be mistaken for verified deployment, and later research results may be difficult to attribute or reproduce.

## Manuscript corrections distinct from missing system features

1. **Model identity:** The Translation Pipeline Module specifies GPT-5.3. Local configuration selects `gpt-oss:20b-cloud` with `gemini-3.5-flash-lite` fallback. [Provider registration](C:/dev/Trilingua/trilingua-code/Model/server.py:89) includes GPT-OSS, Gemini and NLLB; the [OpenAI provider](C:/dev/Trilingua/trilingua-code/Model/providers/future_openai.py) is a stub. Update the manuscript to describe the evaluated implementation, or explicitly decide to change the implementation and re-evaluate it. This review does not verify which model any deployed service currently uses.
2. **Format contract:** The manuscript promises direct images and rejects XLSX; the application accepts nine document formats and rejects direct images. It also converts RTF/ODT to DOCX, contrary to an unconditional same-format download claim. Publish one accurate scope and derive the functionality cases from it.
3. **Context mechanism:** Document-level assistance exists, but the manuscript's uniform overlapping-segment description is incomplete. The current implementation combines blocks, batches, document memory, sampled analysis and mode-dependent context; Office formats use an in-place route. Describe actual context handling and test its benefit against a matched no-context baseline.
4. **Model comparison:** Labels such as best overall and extremely high accuracy need a documented comparison protocol and results. A model name or qualitative table does not establish TriLingua performance.
5. **Coordinator role:** The manuscript explicitly makes the Language Coordinator an institutional recommendation rather than a built-in role. Do not count the absence of a separate coordinator account as a missing requirement. Existing administrator edit/verify/flag and draft/publication mechanisms should be evaluated before adding roles.

## What is already present

Source implements the three languages, text translation, queued document translation, user accounts, stored text/document history, bookmarks, downloads/retranslation, administrator review/edit/flag/verification, draft regeneration, notifications, quotas, ownership checks and recovery/cleanup mechanisms. Their existence does not establish that every live workflow passes, but it means these are not the main missing features.

## Recommended order

1. Correct formula loss and unsafe rich preview.
2. Agree on the manuscript/input-format contract and complete OCR coverage within that scope.
3. Complete the approved educational corpus, terminology checks and explicit formatting method.
4. Verify fresh end-to-end operation, then conduct expert review and teacher UAT using representative classroom materials.
5. Align the manuscript's model, architecture, results and retention statements with the evidence actually obtained.

**Verdict:** The core application is implemented. Reliable document coverage, safe handling and a defensible educational evaluation remain the immediate priorities.

**Not checked:** Every source file; manuscript figure contents and visual layout; fresh translation quality; deployed services/infrastructure; full regression suites; live queue races; browser exploitation; completed UAT or expert records outside the inspected workspace. Historical test results are not presented as newly executed results.
