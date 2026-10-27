# Test3 Current Pipeline Evaluation

Run date: 5 October 2026. Eight public source PDFs; one target language per original; 23 source pages.

Execution passed: all eight requests returned HTTP 200, created valid PDF files, and retained all 23 pages. Saved-output acceptance failed: none of the eight met the combined content-preservation and layout checks. The dominant failures are truncation/collisions and rotated-page reconstruction; separate block-level conversational replies and one confirmed mistranslation also occur. Total document request time was 37.86 minutes. This is not a production-readiness or linguistic-accuracy pass.

Acceptance checks: valid output and unchanged page count; readable upright text; no visible clipping or content loss; no disruptive overlap; no conversational reply substituted for document content. FAIL below refers to these saved-output checks, not the HTTP request. Linguistic accuracy is unverified except for stated spot checks.

| ID / document | Direction | Time | Output / QA |
| --- | --- | --- | --- |
| 01 CFPB Spending Tracker | English → Cebuano | 12.12 min | FAIL: layout |
| 02 OSHA Working in the Heat | English → Cebuano | 5.99 min | FAIL: layout / loss |
| 03 CDC Inactive Tuberculosis | English → Filipino | 2.98 min | FAIL: rendered loss |
| 04 FTC Avoiding Scams | Filipino → Cebuano | 3.95 min | FAIL: loss / label |
| 05 FTC Immigration Scams | Filipino → English | 4.53 min | FAIL: content / layout |
| 06 FTC Tech Support Scams | Filipino → Cebuano | 3.81 min | FAIL: rendered loss |
| 07 CDC Hindi Aktibong Tuberculosis | Filipino → English | 1.94 min | FAIL: local overlap |
| 08 Ang Wikipedya | Cebuano → English | 2.54 min | FAIL: rotation / content |

Coverage: five of six directed language pairs. Cebuano → Filipino was not run because the collection contains only one Cebuano original. Repeating it would violate the one-translation-per-file instruction.

## Scope and configuration

Direct POST /translate/document on an isolated loopback FastAPI process. Balanced mode; automatic PDF column handling; current working tree; legacy block pipeline (unit flag default false). Translation: gpt-oss:20b-cloud with gemini-3.5-flash-lite fallback. Analysis/review: Gemini with Ollama fallback. Saved cache disabled for fresh processing; reload disabled; no production configuration or application source was edited.

This run does not verify Laravel upload, authentication, database persistence, queue recovery, download UI, or other file formats. One startup warmup call was separate from the eight document requests. Internal batch retries and repairs were allowed as part of the current pipeline.

## Observed findings

### Critical: translated text is truncated or overlaps during PDF reconstruction

CFPB has severe paragraph/table collisions and logged truncation. OSHA loses a website during rendering although its translation block contains the correct literal URL. Page count and nonempty extracted text therefore cannot establish layout or content preservation. The reused benchmark helper's field called layout_validation is only that structural proxy, not a visual pass. CFPB had 37 blocks scored 95 by the automated text reviewer despite the rendered damage: those scores precede reconstruction and do not validate layout.

Evidence: 01_response.json; 02_response.json block 1; server.log [Layout] Overflow lines; visual-qa/01_pages_1-2.png, 01_pages_3-4.png, 02_pages_1-2.png; qa.json ID 1

### Critical: rotated PDF page handling fails

OSHA source page 2 renders upright with 180-degree page rotation metadata. Its translated text is upside down, unlike the retained illustrations. Both Cebuano brochure pages use 90-degree rotation metadata: English text runs vertically and original Cebuano prose remains visible. These are reconstruction orientation/overlay defects visible in direct source/output comparisons.

Evidence: 02 source/output page 2; 08 source/output pages 1-2; visual-qa/02_pages_1-2.png and 08_pages_1-2.png

### Content error: a conversational response was accepted for a short label

FTC Avoiding Scams source block 3 contains only Tagalog. Its final translation instead asks the user to supply a whole paragraph in Filipino, beginning Paumanhin. The English immigration output repeats this on blocks 0, 7, 24 and 35, replacing Tagalog headers with conversational requests. This proves recurring content contamination at the block stage; whether initial translation or a later quality repair introduced it is unverified. Short labels and proper language names need a content guard that rejects conversational replies.

Evidence: 04_response.json block 3; 05_response.json blocks 0, 7, 24, 35; visual-qa/04_pages_1-2.png and 05_pages_*.png

### Confirmed lexical spot-check: Spanish became Chinese

The Cebuano brochure's multilingual list includes Kinatsila. Final translated block 10 lists Chinese in that position. The Cebuano dictionary entry defines Kinatsila as Spanish, confirming a specific meaning error that already exists before rendering. This single verified error does not measure overall translation accuracy. Dictionary: https://en.wiktionary.org/wiki/Kinatsila (checked 5 October 2026).

Evidence: 08_response.json block 10; source PDF page 2; Wiktionary Kinatsila entry

### Recurring: malformed Gemini review responses trigger slow fallback

Both of the first two batched quality reviews received non-JSON Gemini responses after three attempts and fell back to Ollama. The first review then timed out twice before eventually producing scores. The full first file took 727.22 seconds and the second 359.40 seconds. The observed fallback behavior is included, not bypassed.

Evidence: server.log GeminiAnalysis / OllamaAnalysis / Analysis lines; results.json IDs 1 and 2

## Per-file content and layout checks

### 01. CFPB Spending Tracker (English → Cebuano)

All four pages saved, but page 1 bullet paragraphs and page 2 lower rows overlap severely. Page 3 labels are shortened, displaced, and some text falls outside the page. Reconstruction logs explicitly report truncated words. This is a successful request with an unusable layout, not a formatting pass. No blank or unchanged long non-passthrough blocks in the saved sidecar.

Output: 4 pages; 5,915 extracted characters; 89 blocks. Created: translated\01_EN_CFPB_Spending_Tracker_to_Cebuano.pdf. Evidence: evidence/01_response.json and visual-qa/01_pages_*.png.

### 02. OSHA Working in the Heat (English → Cebuano)

All four landscape pages saved. Source page 2 has rotation metadata 180 degrees but renders upright; the translated page's text renders upside down while illustrations remain upright. Other pages show collisions and truncated lines. www.osha.gov/workers exists in block 1 of the saved response but is missing from the output PDF; page 1's publication footer is also partly hidden. No blank or unchanged long non-passthrough blocks in the sidecar.

Output: 4 pages; 2,936 extracted characters; 39 blocks. Created: translated\02_EN_OSHA_Working_in_the_Heat_to_Cebuano.pdf. Evidence: evidence/02_response.json and visual-qa/02_pages_*.png.

### 03. CDC Inactive Tuberculosis (English → Filipino)

Two pages saved, but the page 1 title stops at Inaktibong, paragraphs and callout boxes lose trailing text, and page 2's footer loses www.cdc.gov/thinktesttreattb. The illustration layout remains recognizable. Whole-PDF reference similarity is BLEU 43.17 / chrF 68.93; these do not override the visible truncation. No blank or unchanged long non-passthrough sidecar blocks were found.

Output: 2 pages; 2,887 extracted characters; 22 blocks. Created: translated\03_EN_CDC_Inactive_Tuberculosis_to_Filipino.pdf. Evidence: evidence/03_response.json and visual-qa/03_pages_*.png.

### 04. FTC Avoiding Scams (Filipino → Cebuano)

Two pages saved and the overall design remains readable, but several page 1 headings/body paragraphs stop before the complete translated text. For the short label Tagalog, saved block 3 contains a long Filipino apology and request to provide a full paragraph; the PDF clips it to Paumanhin,. This is a conversational provider response accepted as document content, independent of reconstruction. Phone-number digit groups survive the heuristic check. No blank or unchanged long non-passthrough sidecar blocks were found.

Output: 2 pages; 3,832 extracted characters; 38 blocks. Created: translated\04_FIL_FTC_Kung_Paano_Makakaiwas_sa_Scam_to_Cebuano.pdf. Evidence: evidence/04_response.json and visual-qa/04_pages_*.png.

### 05. FTC Immigration Scams (Filipino → English)

Five pages saved; much English body text is readable and the checked domain strings and numeric groups survive. Repeated Tagalog headers turn into requests to provide a paragraph, printed down the right margin on pages 1, 2, 4 and 5. Headings/bullets are collapsed into nearby paragraphs, with small displaced text and some truncated endings. This is a content/formatting failure despite readable sections. No blank or unchanged long non-passthrough sidecar blocks were found.

Output: 5 pages; 7,981 extracted characters; 41 blocks. Created: translated\05_FIL_FTC_Mga_Scam_sa_Imigrasyon_to_English.pdf. Evidence: evidence/05_response.json and visual-qa/05_pages_*.png.

### 06. FTC Tech Support Scams (Filipino → Cebuano)

Two pages saved and most paragraphs are readable without major collisions. The subscription URL FTA.gov/subscribe, the additional-information callout, and the report-action row disappear from the rendered output. FTA.gov is already the spelling in the original; that source typo is not a translation-created defect. Checked phone-number groups survive. No blank or unchanged long non-passthrough sidecar blocks were found.

Output: 2 pages; 2,138 extracted characters; 23 blocks. Created: translated\06_FIL_FTC_Mga_Scam_ng_Tech_Support_to_Cebuano.pdf. Evidence: evidence/06_response.json and visual-qa/06_pages_*.png.

### 07. CDC Hindi Aktibong Tuberculosis (Filipino → English)

This is the most readable of the eight inspected outputs: two pages, recognizable design, and preserved visible footer URL. However, page 2's How are you tested for TB infection? heading overlaps its own second line; the treatment heading also absorbs If from the following paragraph. This prevents a clean layout pass despite readable body text. Whole-PDF reference similarity is BLEU 59.40 / chrF 79.34. No blank or unchanged long non-passthrough sidecar blocks were found.

Output: 2 pages; 2,652 extracted characters; 42 blocks. Created: translated\07_FIL_CDC_Hindi_Aktibong_Tuberculosis_to_English.pdf. Evidence: evidence/07_response.json and visual-qa/07_pages_*.png.

### 08. Ang Wikipedya (Cebuano → English)

Both source pages have 90-degree rotation metadata and render as landscape brochures. Output English text is vertical, columns are damaged, and original Cebuano prose remains visible. Numeric 250 is complete in translated block 10 but missing from the output PDF. Block 10 also changes Kinatsila (Spanish) to Chinese: a lexical spot-check confirms this mistranslation (Wiktionary: https://en.wiktionary.org/wiki/Kinatsila, checked 5 October 2026). No blank or unchanged long non-passthrough sidecar blocks were found; that does not detect untranslated source text left visible beneath a failed overlay.

Output: 2 pages; 3,319 extracted characters; 16 blocks. Created: translated\08_CEB_Ang_Wikipedya_to_English.pdf. Evidence: evidence/08_response.json and visual-qa/08_pages_*.png.

## Execution metrics and verification limits

| ID | LLM calls* | GPT-OSS / Gemini* | Batch fallback | Echo retry | Repair |
| --- | --- | --- | --- | --- | --- |
| 1 | 25 | 22 / 2 | 2 | 0 | 14 |
| 2 | 13 | 11 / 1 | 1 | 0 | 6 |
| 3 | 6 | 5 / 0 | 0 | 0 | 2 |
| 4 | 9 | 8 / 0 | 0 | 0 | 4 |
| 5 | 13 | 11 / 1 | 1 | 0 | 4 |
| 6 | 11 | 10 / 0 | 0 | 0 | 8 |
| 7 | 17 | 13 / 3 | 1 | 2 | 5 |
| 8 | 7 | 6 / 0 | 0 | 0 | 3 |

* Engine telemetry, not billing records. Provider counts describe recorded translation responses; analysis/review calls may be counted differently. See full response metrics and server.log for provenance.

File 03: BLEU 43.17; chrF 68.93 against the publisher's counterpart (file 07). Whole-PDF text, whitespace collapsed, no content removed. These measure textual similarity; neither score is an accuracy percentage or a human evaluation.

File 07: BLEU 59.4; chrF 79.34 against the publisher's counterpart (file 03). Whole-PDF text, whitespace collapsed, no content removed. These measure textual similarity; neither score is an accuracy percentage or a human evaluation.

No human bilingual reviewer or medically qualified reviewer participated. Spot checks, structural checks, protected-span checks, and BLEU/chrF cannot certify translation accuracy. All inputs are PDFs; DOCX/XLSX/XML capabilities remain untested. Protected-span matching is a heuristic: the numeric helper checks digit groups of at least two digits, whole-document matches can hide local omissions, and legitimate formatting changes can cause false alarms. Publisher counterparts are not aligned sentence-level gold references; wording, ordering and document IDs can differ. One run per file does not establish stability or latency percentiles. This cohort and default legacy block path are different from the older storybook/unit-pipeline benchmark and cannot establish an iteration improvement or regression without a matched comparison.

### Reproducibility and next action

Evidence folder contains the manifest (source/engine hashes, Git revision, safe configuration), per-request response JSON, extracted source/output text, results.json, qa.json, comparison PNGs, and server.log. Originals unchanged: True. The test process was stopped after the run; the existing Ollama service was retained.

All saved engine Python source hashes were unchanged at the end of the run. Output PDFs total 39,519,216 bytes (39.52 MB), versus 3.82 MB for the originals. Source selection, download links and legal basis are documented in output/research/translation-test-resources.md.

Prioritize PDF reconstruction: orientation transforms, safe fitting without silent truncation, and a post-render content-preservation gate. Reject conversational replies for short labels and preserve language names. Separately investigate structured Gemini review responses and retry latency. Obtain bilingual human review before claiming linguistic accuracy. Cebuano-to-Filipino needs another Cebuano original or separate authorization to reuse the existing one. No application fixes were made in this testing task.

Do not rerun run_test3.py over this evidence: it refuses an existing results.json to prevent duplicate translation requests. inspect_outputs.py and build_report.py only inspect/rebuild saved evidence.
