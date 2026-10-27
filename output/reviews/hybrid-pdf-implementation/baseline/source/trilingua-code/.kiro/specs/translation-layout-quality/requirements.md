# Requirements Document

## Introduction

This feature improves the output quality of the Trilingua document translation system across two dimensions: translation quality and document layout fidelity. The system currently uses `facebook/nllb-200-distilled-600M` for English ↔ Cebuano ↔ Filipino translation and reconstructs translated documents as PDF or DOCX files. Known gaps include weak fluency from the distilled model, no cross-block context, no terminology consistency, mid-sentence chunk splits, hardcoded fonts in PDF output, white-rect bleed on non-white backgrounds, overflow pushing into adjacent blocks, and near-total loss of DOCX formatting (styles, color, alignment, tables).

## Glossary

- **Translator**: The Python translation pipeline in `document_translator_v3.py` that converts source text blocks into target-language text.
- **Block**: A discrete unit of text extracted from a document (paragraph, heading, table cell, etc.) with associated position and style metadata.
- **Chunk**: A sub-unit of a Block produced by sentence-boundary splitting when a Block exceeds the word limit.
- **Chunk_Splitter**: The component responsible for dividing long Blocks into Chunks before encoding.
- **PDF_Writer**: The component in `write_pdf_preserved()` that overlays translated text onto the original PDF page.
- **DOCX_Writer**: The component in `write_docx()` that reconstructs a translated DOCX file.
- **Glossary_Store**: A user-supplied or auto-generated key-value mapping of source terms to their canonical target-language equivalents.
- **Context_Buffer**: An in-memory sliding window of recently translated Blocks used to improve coherence across Block boundaries.
- **Font_Mapper**: A component that maps original PDF font names to available embedded or system fonts for use in the translated PDF.
- **Background_Sampler**: A component that samples the pixel color of the area behind a text Block to determine the correct erase fill color.
- **Column_Detector**: The existing component that splits page blocks into left and right columns.
- **Style_Mapper**: A component that maps DOCX paragraph style names (e.g., "Heading 1", "List Bullet") to their python-docx equivalents in the output document.
- **NLLB_Model**: The `facebook/nllb-200-distilled-600M` seq2seq model currently used for translation.
- **BLEU**: Bilingual Evaluation Understudy score — a standard metric for translation quality.

---

## Requirements

### Requirement 1: Sentence-Boundary Chunk Splitting

**User Story:** As a translator user, I want chunk boundaries to always fall at sentence ends, so that translated output does not contain incomplete or grammatically broken sentences caused by mid-word or mid-phrase splits.

#### Acceptance Criteria

1. WHEN a Block contains more than 80 whitespace-delimited tokens, THE Chunk_Splitter SHALL divide the Block only at sentence-ending punctuation (`.`, `!`, `?`) followed by whitespace or end-of-string.
2. WHEN no sentence boundary exists within an 80-token window, THE Chunk_Splitter SHALL extend the current Chunk to the next available sentence boundary, up to a maximum of 150 tokens per Chunk, rather than splitting mid-sentence.
3. WHEN a Block contains no sentence-ending punctuation anywhere, THE Chunk_Splitter SHALL treat the entire Block as a single Chunk regardless of its length.
4. THE Chunk_Splitter SHALL produce Chunks of no fewer than 5 whitespace-delimited tokens unless the entire Block is shorter than 5 tokens.
5. WHEN a Block is split into multiple Chunks, THE Translator SHALL join the translated Chunks with a single space to form the final translated Block text.
6. THE Chunk_Splitter SHALL preserve the complete character-for-character content of the original Block across all Chunks — including all words, punctuation, and whitespace — with no characters dropped or duplicated at boundaries.

---

### Requirement 2: Cross-Block Context Window

**User Story:** As a translator user, I want the translation of each block to be informed by the preceding blocks, so that pronouns, named entities, and topic continuity are consistent across block boundaries.

#### Acceptance Criteria

1. WHEN translating a Block, THE Translator SHALL maintain a Context_Buffer scoped to the current document and current translation session, containing the translated text of the preceding 2 Blocks from the same document.
2. WHEN the Context_Buffer is non-empty, THE Translator SHALL prepend the Context_Buffer content as a context hint to the source text before encoding, using the fixed delimiter string `" ||| "` (space, three pipe characters, space) to separate the context hint from the source Block text.
3. WHEN the combined length of the context hint and the source Block exceeds 400 tokens, THE Translator SHALL truncate the context hint from the front (oldest context first) to fit within the 400-token limit.
4. THE Translator SHALL NOT include the context hint text in the decoded output — the decoded output SHALL contain only text derived from the source Block, with no verbatim content from the Context_Buffer appearing in the result.
5. WHEN a document has fewer than 2 preceding Blocks, THE Translator SHALL use only the available preceding Blocks in the Context_Buffer.

---

### Requirement 3: Glossary-Based Terminology Consistency

**User Story:** As a translator user, I want to supply a glossary of key terms, so that domain-specific words and proper nouns are translated consistently throughout the entire document.

#### Acceptance Criteria

1. THE Glossary_Store SHALL accept a list of source-term to target-term pairs provided by the user before translation begins.
2. WHEN a Block's translated output contains a source term that exists in the Glossary_Store, THE Translator SHALL replace all occurrences of that source term — matched as a whole word using case-insensitive comparison — with the corresponding target term from the Glossary_Store.
3. WHEN applying glossary substitution, THE Translator SHALL preserve the original capitalisation pattern of each matched token: all-caps tokens SHALL produce all-caps target terms, title-case tokens SHALL produce title-case target terms, lowercase tokens SHALL produce lowercase target terms, and tokens with any other capitalisation pattern SHALL use the target term exactly as stored in the Glossary_Store.
4. IF a source term in the Glossary_Store does not appear in any Block of the document, THE Translator SHALL complete translation without error and SHALL NOT modify any Block text.
5. THE Glossary_Store SHALL support between 1 and 1,000 term pairs per translation job.
6. WHEN the Glossary_Store is empty or not provided, THE Translator SHALL translate the document without glossary substitution and SHALL NOT raise an error.
7. WHEN the Glossary_Store contains duplicate source terms (two or more entries with the same source term after case-insensitive normalization), THE Translator SHALL reject the glossary before translation begins and SHALL notify the user identifying the duplicate term, without starting the translation job.

---

### Requirement 4: PDF Font Matching

**User Story:** As a translator user, I want the translated PDF to use fonts that visually match the original document, so that the output looks consistent with the source layout.

#### Acceptance Criteria

1. WHEN writing a translated Block to a PDF page, THE Font_Mapper SHALL read the dominant font name from the Block's style metadata as extracted by `read_pdf()`.
2. WHEN the dominant font name from the Block matches a font embedded in the original PDF (using case-insensitive exact string comparison), THE PDF_Writer SHALL use that embedded font for the translated text insertion.
3. WHEN the dominant font name does not match any embedded font and belongs to a recognized font family, THE Font_Mapper SHALL map the font name to the closest available standard PDF base font (Helvetica, Times-Roman, Courier) based on font family classification (sans-serif → Helvetica, serif → Times-Roman, monospace → Courier).
4. IF font matching fails for any Block — either because the embedded font match fails and the font family is unrecognized, or because an exception occurs during font lookup — THE PDF_Writer SHALL fall back to "helv" (Helvetica) for that Block and SHALL log a warning identifying the Block's page number and bounding box.
5. THE Font_Mapper SHALL extract and store font metadata per Block during the `read_pdf()` phase so that font metadata is available at write time without requiring an additional PDF parsing pass.

---

### Requirement 5: PDF Background-Aware Erasure

**User Story:** As a translator user, I want the text erasure rectangles in the translated PDF to match the background color of the original page, so that erased areas do not appear as white patches on colored or image backgrounds.

#### Acceptance Criteria

1. WHEN erasing a text Block region on a PDF page, THE Background_Sampler SHALL sample the fill color of the page at the four corners of the Block's bounding box before drawing the erase rectangle. WHEN a corner coordinate falls outside the page bounds, THE Background_Sampler SHALL clamp that coordinate to the nearest point within the page boundary before sampling.
2. WHEN all four sampled corner pixels share the same RGB color value (exact equality of all three channels), THE PDF_Writer SHALL use that color as the fill for the erase rectangle.
3. WHEN the sampled corner pixels differ in any RGB channel (indicating a gradient, image, or pattern background), THE PDF_Writer SHALL use a transparent clip-and-redraw strategy: re-stamp the original page content clipped to the Block region, then overlay the translated text on top.
4. WHEN the transparent clip-and-redraw strategy is used, THE PDF_Writer SHALL render the translated text in a layer added after the re-stamped background clip, ensuring the text appears above the background with no z-order conflicts observable in the output PDF.
5. WHEN a Block's bounding box has zero width or zero height, THE Background_Sampler SHALL skip sampling for that Block and THE PDF_Writer SHALL proceed directly to text insertion without drawing an erase rectangle.
6. IF background sampling raises an exception for a Block, THE PDF_Writer SHALL fall back to a white fill erase rectangle for that Block and SHALL log a warning to stdout identifying the Block's page number and bounding box coordinates.

---

### Requirement 6: PDF Overflow Containment

**User Story:** As a translator user, I want overflow text in translated PDFs to expand downward without overlapping adjacent text blocks, so that no translated content is lost or visually collides with neighboring content.

#### Acceptance Criteria

1. WHEN translated text overflows the original Block bounding box, THE PDF_Writer SHALL calculate the required expansion height based on the overflow amount returned by `insert_textbox()`.
2. WHEN expanding a Block downward, THE PDF_Writer SHALL check whether the expanded bounding box intersects any other Block on the same page, where "intersects" means the vertical gap between the bottom of the expanded box and the top of any other Block on the same page would be less than 2 points.
3. IF the expanded bounding box would intersect an adjacent Block, THE PDF_Writer SHALL reduce the font size of the overflowing Block by 1 point and retry insertion into the original bounding box dimensions, repeating until either the text fits within the original bounding box or the font size reaches 6 points.
4. WHEN font size reduction reaches 6 points and overflow still exists, THE PDF_Writer SHALL insert the remaining overflow text in a new continuation box of the same width as the original Block, placed 4 points below the last Block on that page.
5. THE PDF_Writer SHALL NOT move or resize any Block other than the currently overflowing Block when resolving overflow.
6. WHEN the continuation box itself would extend beyond the bottom of the page, THE PDF_Writer SHALL clip the continuation box to the page boundary and log a warning to stdout identifying the Block's page number and bounding box.

---

### Requirement 7: DOCX Paragraph Style Preservation

**User Story:** As a translator user, I want the translated DOCX to preserve the paragraph styles of the original document (headings, lists, body text), so that the document structure is recognizable after translation.

#### Acceptance Criteria

1. WHEN reading a DOCX source file, THE DOCX_Writer's reader SHALL extract the paragraph style name for each paragraph in addition to text and run-level formatting.
2. WHEN writing a translated paragraph to the output DOCX, THE Style_Mapper SHALL apply the same paragraph style name to the output paragraph.
3. WHEN the source paragraph style name is null, empty, or does not exist in the output document's style table, THE Style_Mapper SHALL apply the "Normal" style to the output paragraph.
4. THE DOCX_Writer SHALL preserve text alignment (left, center, right, justify) for each paragraph by copying the `paragraph.alignment` value from source to output.
5. THE DOCX_Writer SHALL preserve paragraph spacing for each paragraph: WHEN `paragraph.paragraph_format.space_before` is not None in the source, THE DOCX_Writer SHALL copy that value to the output paragraph; WHEN `paragraph.paragraph_format.space_after` is not None in the source, THE DOCX_Writer SHALL copy that value to the output paragraph.
6. WHEN a run in the source paragraph has a font color assigned directly on the run (not inherited from the paragraph or style), THE DOCX_Writer SHALL copy that `run.font.color.rgb` value to the corresponding run in the output paragraph.

---

### Requirement 8: DOCX Table Translation

**User Story:** As a translator user, I want tables in DOCX source files to be translated and included in the output document, so that tabular data is not silently dropped during translation.

#### Acceptance Criteria

1. WHEN reading a DOCX source file, THE DOCX_Writer's reader SHALL extract all tables, preserving the row and column structure, the spanning attributes of merged cells, and the text content of each cell.
2. WHEN translating a DOCX document, THE Translator SHALL translate the text content of each table cell whose text content, after stripping leading and trailing whitespace, is non-empty, using the same source and target language settings as the rest of the document.
3. WHEN writing the output DOCX, THE DOCX_Writer SHALL reconstruct each table with the same number of rows and columns as the source table, preserving merged cell spanning attributes.
4. WHEN writing a translated table cell, IF the source cell's run has bold explicitly set, THE DOCX_Writer SHALL set bold on the corresponding output run; IF the source cell's run has a font size explicitly set, THE DOCX_Writer SHALL set the same font size on the corresponding output run; IF bold or font size is not explicitly set on the source run, THE DOCX_Writer SHALL leave the corresponding attribute unset on the output run.
5. WHEN a table cell's text content, after stripping leading and trailing whitespace, is empty in the source document, THE DOCX_Writer SHALL write an empty cell in the output document without attempting translation.
6. WHEN writing the output DOCX, THE DOCX_Writer SHALL insert each translated table at the same position index within the document body element sequence as in the source document.

---

### Requirement 9: Translation Quality Metric Reporting

**User Story:** As a developer, I want the translation pipeline to report a BLEU score for each document translation job, so that I can monitor translation quality over time and detect regressions.

#### Acceptance Criteria

1. WHEN a document translation job completes and a reference translation file is provided, THE Translator SHALL compute a corpus-level BLEU score by comparing the translated Blocks against the corresponding reference Blocks, where the reference file is a plain-text file with one block of reference text per non-empty line.
2. WHEN no reference translation file is provided, THE Translator SHALL skip BLEU computation and SHALL NOT raise an error.
3. WHEN a document translation job completes and a reference file was provided, THE Translator SHALL return a result dictionary containing the keys `bleu_score` (a float in the range 0.0–100.0), `output_file` (the path to the translated output file), and `translated_blocks` (the list of translated Block objects).
4. WHEN the reference file contains a different number of non-empty lines than the number of translated Blocks, THE Translator SHALL compute BLEU only over the Blocks that can be aligned by index (up to the minimum of the two counts) and SHALL print a warning to stdout stating the count mismatch.
5. THE Translator SHALL use the `sacrebleu` library for BLEU computation to ensure reproducible, standardised scores.
6. IF the reference file cannot be read or is malformed (e.g., encoding error, file not found), THE Translator SHALL skip BLEU computation, set `bleu_score` to `None` in the result dictionary, and print a warning to stdout identifying the file path and the error.

---

### Requirement 10: Multi-Column PDF Detection Improvement

**User Story:** As a translator user, I want the column detector to correctly identify documents with more than two columns or non-uniform column widths, so that text reading order is preserved in complex layouts.

#### Acceptance Criteria

1. WHEN analyzing a PDF page, THE Column_Detector SHALL use x-coordinate gap analysis to identify column boundaries, where a column boundary is defined as a horizontal gap of at least 10% of the page width between the rightmost edge of one group of Blocks and the leftmost edge of the next group of Blocks.
2. THE Column_Detector SHALL support detection of 1, 2, or 3 columns per page.
3. WHEN THE Column_Detector identifies column boundaries, THE Column_Detector SHALL sort Blocks within each column by their top y-coordinate before merging columns into the final reading order: left column first, then center column (if present), then right column.
4. WHEN a page contains Blocks whose width is at least 90% of the page width, THE Column_Detector SHALL classify those Blocks as full-width and place them in reading order before any columnar Blocks whose top y-coordinate is greater than the full-width Block's top y-coordinate.
5. IF THE Column_Detector cannot determine a clear column structure (fewer than 2 Blocks per candidate column after applying the gap threshold), THE Column_Detector SHALL treat the page as single-column and return all Blocks sorted by top y-coordinate.
