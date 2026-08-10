# Requirements Document

## Introduction

Trilingua is a Laravel + Python (FastAPI) trilingual translation application supporting English, Cebuano, and Filipino. The Python microservice in `Model/document_translator_v3.py` handles all document translation for DOCX, PDF, TXT, CSV, PPTX, and XLSX formats using the Mistral AI API.

This feature addresses a set of critical, high-severity, and medium-severity defects in the translation pipeline. The primary goals are:

1. Introduce a `Chunk_Splitter` class so long blocks are split before Mistral API calls, eliminating mid-sentence truncation caused by the hard `max_tokens=2048` ceiling.
2. Implement a `Font_Mapper` class that detects embedded fonts and maps unknown fonts to safe built-in fallbacks with warnings.
3. Implement a `Style_Mapper` class that safely resolves DOCX paragraph styles to available styles in the target document.
4. Implement a `_resolve_overflow()` function with a downward-expansion strategy and continuation blocks for PDF text overflow.
5. Re-enable PDF column detection so the `column_mode` parameter (left / right / auto / single) is correctly honoured.
6. Preserve per-run bold/italic/color formatting when translating DOCX paragraphs with multiple runs.
7. Translate DOCX headers and footers in addition to body paragraphs.
8. Remove the dead `Context_Buffer` construction in `batch_translate_blocks` when context hints are intentionally unused.
9. Fix the fragile language-code round-trip in the CSV translation branch.
10. Extract PPTX notes slides and table shapes during reading.

All new classes and the `_resolve_overflow` function must be importable from `document_translator_v3` so the existing test suite in `Model/tests/test_units.py` passes without `ImportError`.

---

## Glossary

- **Pipeline**: The end-to-end translation workflow in `document_translator_v3.py` — read → translate → write.
- **Chunk_Splitter**: A new class responsible for splitting a long text block into translation-safe chunks at sentence boundaries.
- **Font_Mapper**: A new class responsible for resolving a PDF font name to a PyMuPDF built-in font name, using embedded-font detection and keyword classification.
- **Style_Mapper**: A new class responsible for resolving a DOCX paragraph style name to a style that exists in the target document.
- **Glossary_Store**: The existing class that applies post-translation term substitutions.
- **Context_Buffer**: The existing class that holds a sliding window of recently translated blocks; currently built but never used in `batch_translate_blocks`.
- **Block**: A dict produced by a reader function containing at minimum `"type"` and `"text"` keys, plus optional metadata (`"position"`, `"page"`, `"style"`, etc.).
- **Mistral API**: The external Mistral AI REST endpoint used for all translation calls.
- **max_tokens**: The `max_tokens` parameter sent to the Mistral API; currently hard-coded to 2048.
- **Token Budget**: The number of output tokens remaining after the prompt and source text consume their share of the model context window.
- **hard_cap**: The absolute maximum number of tokens Chunk_Splitter will put in one chunk before forcing a split.
- **Embedded Font**: A font whose glyph data is physically included in the PDF file, detectable via `fitz.Document.get_page_fonts()`.
- **Run**: A contiguous sequence of characters in a DOCX paragraph that share the same character-level formatting (bold, italic, color, font).
- **column_mode**: The user-selected PDF reading mode — `"auto"`, `"single"`, `"left"`, or `"right"`.
- **Language Code**: A language identifier of the form `eng_Latn`, `ceb_Latn`, or `tgl_Latn` used internally; mapped to human-readable names via `CODE_TO_LANG`.
- **Notes Slide**: A PowerPoint slide's notes panel containing speaker notes text.

---

## Requirements

### Requirement 1: Text Chunking Before API Calls (Refined)

**User Story:** As a developer maintaining the translation pipeline, I want long text blocks split into sentence-aligned chunks before they are sent to the Mistral API, so that the `max_tokens=2048` ceiling never truncates a translation mid-sentence.

#### Acceptance Criteria

1. THE `Chunk_Splitter` SHALL be importable from `document_translator_v3` without raising `ImportError`.
2. FOR the purposes of this requirement, a **token** SHALL be defined as a single whitespace-delimited word, and the token count of a text string SHALL be `len(text.split())`.
3. WHEN `Chunk_Splitter.split(text, max_tokens=80)` is called with a text whose token count does not exceed `max_tokens`, THE `Chunk_Splitter` SHALL return a single-element list `[text]` with the original text unchanged.
4. WHEN `Chunk_Splitter.split(text, max_tokens=80)` is called and a sentence boundary (a token ending with `.`, `!`, or `?`) exists at or before position `max_tokens`, THE `Chunk_Splitter` SHALL split at the last such boundary within `max_tokens` tokens, placing the tokens up to and including that boundary in the first chunk.
5. WHEN `Chunk_Splitter.split(text, max_tokens=80, hard_cap=150)` is called and no sentence boundary exists within the first `max_tokens` tokens but one exists within the first `hard_cap` tokens, THE `Chunk_Splitter` SHALL extend the first chunk to that boundary.
6. WHEN `Chunk_Splitter.split(text, max_tokens=80, hard_cap=150)` is called and no sentence boundary exists anywhere within the first `hard_cap` tokens, THE `Chunk_Splitter` SHALL return `[text]` as a single chunk without splitting mid-word.
7. WHEN `Chunk_Splitter.split(text, max_tokens=80, min_tokens=5)` is called and a valid split point exists but the resulting trailing chunk would contain fewer than `min_tokens` tokens, THE `Chunk_Splitter` SHALL merge that trailing chunk into the preceding chunk rather than emitting it separately.
8. FOR ALL text inputs where `text` is a non-empty string of ASCII or Unicode characters, `" ".join(c.split() for c in chunks)` joined as `" ".join(word for c in chunks for word in c.split())` SHALL equal `" ".join(text.split())` (round-trip property: no words are dropped or duplicated).
9. WHEN `Chunk_Splitter.split(text)` is called with an empty string or a string containing only whitespace, THE `Chunk_Splitter` SHALL return `[""]` (a single-element list containing an empty string).
10. WHEN `batch_translate_blocks()` processes a block, THE `Pipeline` SHALL apply `Chunk_Splitter.split()` to the block's text before calling `_translate_with_mistral()`, invoke `_translate_with_mistral()` once per chunk, and rejoin the translated chunks with a single space before storing the result in the translated block.

---

### Requirement 2: Token Budget Enforcement (Refined)

**User Story:** As a developer, I want the pipeline to enforce a token budget before each API call, so that the combined prompt, system instructions, and source text never exhaust the model's output capacity.

#### Acceptance Criteria

1. WHEN `_translate_with_mistral()` is called, THE `Pipeline` SHALL calculate `estimated_input_tokens = floor(len(prompt_string + source_text) / 4)`, where `prompt_string` includes the system instructions and the block-type prefix.
2. IF `estimated_input_tokens` exceeds 1 500, THEN THE `Pipeline` SHALL set `max_tokens = max(1, 4096 − estimated_input_tokens)` for that API call rather than using the default value.
3. IF `estimated_input_tokens` exceeds 3 500, THEN THE `Pipeline` SHALL log a warning to stdout containing the label `[TOKEN BUDGET]`, the estimated input token count, and the first 60 characters of the source text, and SHALL still attempt the translation.
4. THE `Pipeline` SHALL compute all token estimates using `floor(character_count / 4)`, where `character_count` is the length of the string in Unicode code points.

---

### Requirement 3: Context Buffer Integration (Refined)

**User Story:** As a developer, I want dead code that wastes CPU cycles removed from the hot path, so that large documents translate faster and the code is easier to reason about.

#### Acceptance Criteria

1. WHEN `batch_translate_blocks()` is called without a `context_buffer` argument (i.e., `context_buffer=None`), THE `Pipeline` SHALL NOT construct or reference any `Context_Buffer` object during that call.
2. WHEN `batch_translate_blocks()` is called with a non-None `context_buffer` argument, THE `Pipeline` SHALL call `context_buffer.get_hint()` once before translating each block (not each chunk) and SHALL call `context_buffer.push(translated_text)` once after all chunks for that block have been translated and rejoined.
3. WHEN a block translation fails (raises an exception), THE `Pipeline` SHALL NOT call `context_buffer.push()` for that block.
4. THE `Context_Buffer` class SHALL remain importable from `document_translator_v3` so that existing unit tests in `test_units.py` continue to pass.

---

### Requirement 4: PDF Column Detection Re-Enabled (Refined)

**User Story:** As a user translating a two-column PDF document, I want the reading order to follow the column layout, so that the translated output reads left-column-first rather than mixing lines from both columns.

#### Acceptance Criteria

1. WHEN `read_pdf()` is called with `column_mode="auto"`, THE `PDF_Reader` SHALL pass the merged block list through `detect_columns()` and use the sequence returned by `detect_columns()` as the final block order.
2. WHEN `read_pdf()` is called with `column_mode="single"`, THE `PDF_Reader` SHALL skip `detect_columns()` and return all blocks sorted in ascending order by their `position[1]` (top y-coordinate).
3. WHEN `read_pdf()` is called with `column_mode="left"`, THE `PDF_Reader` SHALL include only blocks where `(position[0] + position[2]) / 2 < page_width / 2`, sorted in ascending order by `position[1]`.
4. WHEN `read_pdf()` is called with `column_mode="right"`, THE `PDF_Reader` SHALL include only blocks where `(position[0] + position[2]) / 2 >= page_width / 2`, sorted in ascending order by `position[1]`.
5. IF `detect_columns()` returns a list whose length is less than 50% of the input block count, THEN THE `PDF_Reader` SHALL discard the `detect_columns()` result, fall back to single-column order (criterion 2), and log a warning to stdout containing `[COLUMN FALLBACK]` and the page number.
6. WHEN `read_pdf()` is called with a `column_mode` value that is not one of `"auto"`, `"single"`, `"left"`, or `"right"`, THE `PDF_Reader` SHALL raise a `ValueError` with a message identifying the invalid value and listing the accepted values.

---

### Requirement 5: Font_Mapper Class (Refined)

**User Story:** As a developer, I want a `Font_Mapper` class that centralises all font-name resolution logic for PDF output, so that embedded fonts are used when available, standard keywords map to safe fallbacks, and unknown fonts trigger an auditable warning.

#### Acceptance Criteria

1. THE `Font_Mapper` SHALL be importable from `document_translator_v3` without raising `ImportError`.
2. WHEN `Font_Mapper.resolve(font_name, embedded_fonts)` is called and the lowercase of `font_name` matches the lowercase of any entry in `embedded_fonts`, THE `Font_Mapper` SHALL return the original `font_name` (as passed by the caller) unchanged.
3. WHEN `Font_Mapper.resolve(font_name, embedded_fonts)` is called, `font_name` is not matched in `embedded_fonts`, and `font_name.lower()` contains any of the monospace keywords (`courier`, `consolas`, `mono`), THE `Font_Mapper` SHALL return `"cour"`. Monospace keywords take precedence over serif and sans-serif keywords.
4. WHEN `Font_Mapper.resolve(font_name, embedded_fonts)` is called, `font_name` is not matched in `embedded_fonts`, does not match a monospace keyword, and `font_name.lower()` contains any of the serif keywords (`times`, `georgia`, `roman`), THE `Font_Mapper` SHALL return `"tiro"`.
5. WHEN `Font_Mapper.resolve(font_name, embedded_fonts)` is called, `font_name` is not matched in `embedded_fonts`, does not match monospace or serif keywords, and `font_name.lower()` contains any of the sans-serif keywords (`arial`, `helvetica`, `sans`), THE `Font_Mapper` SHALL return `"helv"`.
6. WHEN `Font_Mapper.resolve(font_name, embedded_fonts)` is called and `font_name` is not matched in `embedded_fonts` and matches no keyword, THE `Font_Mapper` SHALL return `"helv"` and SHALL print a warning to stdout containing the `font_name` value and the `⚠️` character.
7. WHEN `Font_Mapper.resolve(font_name, embedded_fonts)` is called with an empty string or `None` as `font_name`, THE `Font_Mapper` SHALL return `"helv"` and SHALL print a warning to stdout containing `⚠️`.
8. WHEN `write_pdf_preserved()` resolves a font name for a PDF block, THE observable output font name written to the PDF SHALL equal what `Font_Mapper.resolve(font_name, embedded_fonts)` returns for the same `font_name` and `embedded_fonts` inputs.

---

### Requirement 6: PDF Text Overflow Resolution (Refined)

**User Story:** As a user receiving a translated PDF, I want overflowing translated text to expand its bounding box downward before the font is shrunk, so that translated text remains readable and is not silently clipped.

#### Acceptance Criteria

1. THE `_resolve_overflow` function SHALL be importable from `document_translator_v3` without raising `ImportError`.
2. IF `_resolve_overflow()` is called with `initial_remaining >= 0`, THEN THE `_resolve_overflow` function SHALL return `{"resolved": True, "continuation": False, "expanded": False, "final_font": font_size}` without invoking `page.insert_textbox()`.
3. WHEN `_resolve_overflow()` is called with `initial_remaining < 0` and no other block's top y-coordinate (`other_bboxes[i][1]`) is within 2 pt of the candidate expanded bottom edge (`y1 + abs(initial_remaining / font_size) * font_size`), and the expanded bottom edge does not exceed `page_height`, THE `_resolve_overflow` function SHALL expand the bounding box downward, call `page.insert_textbox()` once with the expanded rect and the original `font_size`, and return `{"resolved": True, "expanded": True, "continuation": False, "final_font": font_size}`.
4. WHEN `_resolve_overflow()` is called with `initial_remaining < 0`, downward expansion is blocked by a collision or would exceed `page_height`, and font reduction to some size `f` in the range `[7, font_size)` makes `page.insert_textbox()` return `>= 0`, THEN THE `_resolve_overflow` function SHALL return `{"resolved": True, "expanded": False, "continuation": False, "final_font": f}`.
5. IF `_resolve_overflow()` exhausts all font sizes down to 7 pt and `page.insert_textbox()` still returns `< 0`, THEN THE `_resolve_overflow` function SHALL return `{"resolved": False, "continuation": True, "expanded": False, "final_font": 7}`.
6. WHEN `write_pdf_preserved()` calls `page.insert_textbox()` and the return value is negative, THE `PDF_Writer` SHALL call `_resolve_overflow()` to handle the overflow rather than inline font-shrink logic.

---

### Requirement 7: DOCX Multi-Run Formatting Preservation (Refined)

**User Story:** As a user translating a DOCX document with mixed bold, italic, or coloured text within a single paragraph, I want each run's formatting to be preserved in the translated output, so that styled passages are not reduced to uniform plain text.

#### Acceptance Criteria

1. WHEN `translate_docx_inplace()` translates a paragraph that contains exactly one run, THE `DOCX_Writer` SHALL replace that run's `.text` attribute with the translated text and SHALL NOT modify the run's bold, italic, font size, or colour attributes.
2. WHEN `translate_docx_inplace()` translates a paragraph that contains N runs (N > 1), THE `DOCX_Writer` SHALL (a) concatenate all run texts to form the source string, (b) translate the concatenated source string as a single unit, (c) compute each run's character budget as `floor(len(translated) * len(run.text) / len(source))` with the last run receiving any remaining characters, and (d) assign each run its character budget as a contiguous slice of the translated string, preserving that run's formatting attributes.
3. WHEN `translate_docx_inplace()` translates a paragraph, THE `DOCX_Writer` SHALL update each run's `.text` in place and SHALL NOT call `run.text = ""` on any run before distributing the translated text.
4. WHEN a run's formatting attribute (bold, italic, font size, or colour) is `None` in the original document, THE `DOCX_Writer` SHALL leave that attribute as `None` in the translated output.
5. WHEN a run receives zero characters in the proportional distribution (e.g., because a source run had zero-length text), THE `DOCX_Writer` SHALL set that run's `.text` to an empty string and SHALL NOT modify its formatting attributes.

---

### Requirement 8: DOCX Headers and Footers Translation (Refined)

**User Story:** As a user translating a DOCX document with headers or footers, I want those regions translated along with the body, so that the final document does not contain untranslated header or footer text.

#### Acceptance Criteria

1. WHEN `translate_docx_inplace()` processes a document, THE `DOCX_Writer` SHALL translate non-empty paragraphs in every non-linked section header and footer in addition to body paragraphs, using block type `"header"` for header paragraphs and `"footer"` for footer paragraphs when calling `_translate_single()`.
2. IF a section's header or footer has `is_linked_to_previous == True`, THEN THE `DOCX_Writer` SHALL skip that header or footer entirely to prevent duplicate translation.
3. WHEN the `total` count for progress tracking is computed before translation begins, THE `DOCX_Writer` SHALL include the count of non-empty paragraphs from all non-linked section headers and footers in that total.

---

### Requirement 9: Style_Mapper Class (Refined)

**User Story:** As a developer, I want a `Style_Mapper` class that safely resolves paragraph style names in DOCX output, so that missing styles do not raise `KeyError` and the document always uses a valid available style.

#### Acceptance Criteria

1. THE `Style_Mapper` SHALL be importable from `document_translator_v3` without raising `ImportError`.
2. WHEN `Style_Mapper.resolve(style_name, available_styles)` is called and `style_name` is a non-empty string that is present in `available_styles`, THE `Style_Mapper` SHALL return `style_name` unchanged.
3. WHEN `Style_Mapper.resolve(style_name, available_styles)` is called and `style_name` is `None`, an empty string, or a non-empty string that is not present in `available_styles`, THE `Style_Mapper` SHALL return `"Normal"` unconditionally, regardless of whether `"Normal"` is itself present in `available_styles`.
4. WHEN `write_docx()` is called without a valid original file path (triggering the new-document code path), THE `DOCX_Writer` SHALL call `Style_Mapper.resolve(style_info.get("style_name"), available_styles)` — where `available_styles` is the set of style names in the new document — to determine the paragraph style, rather than using `style_info.get("style_name", "Normal")` directly.

---

### Requirement 10: CSV Language-Code Round-Trip Fix (Refined)

**User Story:** As a developer, I want the CSV translation branch to pass language names directly to `_translate_single`, so that the fragile language-code-to-name round-trip is eliminated and the code path matches the non-CSV branches.

#### Acceptance Criteria

1. WHEN `run_pipeline()` processes a CSV file, THE `Pipeline` SHALL pass `source_lang` and `target_lang` (the human-readable names, e.g. `"English"`, `"Cebuano"`, `"Filipino"`) directly as the `src_code` and `tgt_code` arguments to `_translate_single()`, without first converting them via `LANGUAGES[source_lang]`.
2. WHEN `_translate_single()` receives a value for `src_code` or `tgt_code` that is not present as a key in `CODE_TO_LANG`, THE `Pipeline` SHALL use that value as-is as the `source_lang` or `target_lang` argument passed to `_translate_with_mistral()`.
3. THE `LANGUAGES` dict and `CODE_TO_LANG` reverse-mapping SHALL remain present and unchanged in `document_translator_v3` so that all non-CSV callers that pass language codes (e.g. `eng_Latn`) continue to resolve to the correct language names.

---

### Requirement 11: PPTX Notes and Table Shape Extraction (Refined)

**User Story:** As a user translating a PowerPoint presentation that contains speaker notes or table shapes, I want that text included in the translation, so that the output document is fully translated.

#### Acceptance Criteria

1. WHEN `read_pptx()` processes a slide that has a notes slide with non-empty text frames, THE `PPTX_Reader` SHALL extract each non-empty paragraph text and append a block with keys `"type": "notes"`, `"text"`, `"slide"` (slide index), `"shape_id"` (notes placeholder shape ID), and `"para_idx"` (paragraph index within the notes frame).
2. WHEN `read_pptx()` processes a slide that contains a shape whose `shape_type` indicates a table, THE `PPTX_Reader` SHALL iterate every cell and append a block with keys `"type": "table_cell"`, `"text"`, `"slide"` (slide index), `"shape_id"`, `"row"`, and `"col"` for each cell whose text, after stripping whitespace, is non-empty (length > 0).
3. WHEN `translate_pptx_inplace()` encounters a block with `"type": "notes"`, THE `PPTX_Writer` SHALL locate the notes-slide paragraph identified by (`slide`, `shape_id`, `para_idx`) and replace its text in the same proportional-distribution manner as body paragraphs.
4. WHEN `translate_pptx_inplace()` encounters a block with `"type": "table_cell"`, THE `PPTX_Writer` SHALL locate the table cell identified by (`slide`, `shape_id`, `row`, `col`) and replace its text in place.

---

### Requirement 12: Test Suite Importability (Refined)

**User Story:** As a developer running `pytest`, I want all classes and functions referenced in `test_units.py` to be importable from `document_translator_v3`, so that the test suite runs without `ImportError` and all unit tests execute.

#### Acceptance Criteria

1. THE `document_translator_v3` module SHALL define `Chunk_Splitter`, `Context_Buffer`, `Glossary_Store`, `Font_Mapper`, `Style_Mapper`, and `_resolve_overflow` at module scope so each is importable with a direct `from document_translator_v3 import X` statement.
2. WHEN `pytest Model/tests/test_units.py` is executed after all requirements are implemented, THE `Test_Suite` SHALL report zero collection errors attributable to `ImportError` or `AttributeError` on any of the six symbols listed in criterion 1.
3. WHEN `pytest Model/tests/test_units.py` is executed after all requirements are implemented, THE `Test_Suite` SHALL pass all test cases in `TestChunkSplitter*`, `TestContextBuffer`, `TestGlossaryStore`, `TestFontMapper`, `TestStyleMapper`, and `TestResolveOverflow*` without modification to the test file.
