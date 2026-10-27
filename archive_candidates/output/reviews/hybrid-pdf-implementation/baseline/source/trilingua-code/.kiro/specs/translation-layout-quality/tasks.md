# Implementation Plan: Translation Layout Quality

## Overview

Implement ten focused components inside `Model/document_translator_v3.py` that improve translation quality (Chunk_Splitter, Context_Buffer, Glossary_Store, BLEU_Reporter) and document layout fidelity (Font_Mapper, Background_Sampler, PDF overflow containment, Style_Mapper, DOCX_Writer v2, Column_Detector v2). All property-based tests live in `Model/tests/test_properties.py` and unit tests in `Model/tests/test_units.py`, using pytest + Hypothesis. No changes are made to `server.py` or the Laravel layer.

---

## Tasks

- [x] 1. Set up test infrastructure and shared fixtures
  - Create `Model/tests/` directory with `__init__.py` and `conftest.py`
  - Add `conftest.py` fixtures: a minimal `fitz.Page` mock, a sample DOCX `Document` factory, and a small block-list factory
  - Verify `pytest`, `hypothesis`, and `sacrebleu` are importable; add them to a `requirements-dev.txt` if absent
  - _Requirements: 1.1–1.6, 2.1–2.5, 3.1–3.7, 4.1–4.5, 5.1–5.6, 6.1–6.6, 7.1–7.6, 8.1–8.6, 9.1–9.6, 10.1–10.5_

- [x] 2. Implement `Chunk_Splitter`
  - [x] 2.1 Write the `Chunk_Splitter` class in `document_translator_v3.py`
    - Implement `split(text, max_tokens=80, hard_cap=150, min_tokens=5) -> list[str]`
    - Split only at sentence-ending punctuation (`. ! ?`) followed by whitespace or end-of-string
    - Extend to next boundary (up to `hard_cap`) when no boundary exists within `max_tokens`
    - Return `[text]` when no sentence-ending punctuation exists anywhere
    - Enforce minimum chunk size of `min_tokens` (merge forward if needed)
    - Replace the existing `_split_long_text()` call inside `_translate_single()`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 2.2 Write unit tests for `Chunk_Splitter`
    - Block with exactly 80 tokens → no split
    - Block with 81 tokens, boundary at token 75 → split at 75
    - Block with no sentence-ending punctuation → single chunk
    - Block with 5 tokens → single chunk, no minimum violation
    - Block with 4 tokens → single chunk (below threshold, allowed)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 2.3 Write property test for `Chunk_Splitter` — Property 1: Chunk boundaries fall at sentence endings
    - **Property 1: Chunk boundaries fall at sentence endings**
    - Generate random text with 81–300 tokens and random sentence-ending punctuation placement
    - Assert every chunk except possibly the last ends with `.`, `!`, or `?`
    - **Validates: Requirements 1.1**

  - [x] 2.4 Write property test for `Chunk_Splitter` — Property 2: Chunk content round-trip
    - **Property 2: Chunk content round-trip**
    - Generate random text strings of any length
    - Assert `" ".join(splitter.split(text))` equals `" ".join(text.split())` (normalized whitespace)
    - **Validates: Requirements 1.6**

  - [x] 2.5 Write property test for `Chunk_Splitter` — Property 3: Chunk minimum size
    - **Property 3: Chunk minimum size**
    - Generate random text strings with ≥ 5 tokens
    - Assert every chunk contains at least 5 whitespace-delimited tokens
    - **Validates: Requirements 1.4**

- [x] 3. Implement `Context_Buffer`
  - [x] 3.1 Write the `Context_Buffer` class in `document_translator_v3.py`
    - Implement `__init__(window_size=2)`, `push(translated_text)`, `get_hint() -> str`, `clear()`
    - Use `collections.deque(maxlen=window_size)` as the backing store
    - `get_hint()` returns buffer entries joined by `" ||| "`, or `""` if empty
    - Instantiate once in `run_pipeline()` and pass into `batch_translate_blocks()`
    - Inside `_translate_single()`, prepend hint with `" ||| "` delimiter; truncate hint from front when combined token count exceeds 400
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.2 Write unit tests for `Context_Buffer`
    - Empty buffer returns `""`
    - After 1 push, hint contains 1 entry
    - After 3 pushes (window=2), hint contains only last 2 entries
    - `clear()` resets buffer to empty
    - _Requirements: 2.1, 2.2, 2.5_

  - [x] 3.3 Write property test for `Context_Buffer` — Property 4: Context hint token budget
    - **Property 4: Context hint token budget**
    - Generate random context hint strings and source block strings of varying lengths
    - Assert `len(tokenizer(hint + " ||| " + source)["input_ids"][0]) <= 400` after truncation logic
    - **Validates: Requirements 2.3**

- [x] 4. Implement `Glossary_Store`
  - [x] 4.1 Write the `Glossary_Store` class in `document_translator_v3.py`
    - Implement `__init__(pairs)`, `apply(text) -> str`, and `_match_case(original_token, target_term) -> str`
    - Raise `ValueError` on duplicate source terms (case-insensitive) identifying the duplicate
    - Raise `ValueError` when `len(pairs) > 1000`
    - `apply()` uses `re.sub` with `\b` word boundaries for whole-word, case-insensitive matching
    - `_match_case()` applies all-caps / title-case / lowercase pattern from matched token to target term
    - Call `glossary_store.apply()` on each translated block text inside `batch_translate_blocks()` after `_translate_single()` returns
    - Accept `glossary` as an optional parameter in `run_pipeline()` (default `None`)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 4.2 Write unit tests for `Glossary_Store`
    - Duplicate source terms raise `ValueError` identifying the duplicate
    - 1001 pairs raise `ValueError`
    - Empty glossary: `apply()` returns text unchanged
    - Whole-word match: `"cat"` in `"the cat sat"` → replaced; `"cat"` in `"concatenate"` → not replaced
    - Capitalisation: `"CAT"` → all-caps target; `"Cat"` → title-case target; `"cat"` → lowercase target
    - _Requirements: 3.2, 3.3, 3.5, 3.7_

  - [x] 4.3 Write property test for `Glossary_Store` — Property 5: Glossary whole-word substitution
    - **Property 5: Glossary whole-word substitution**
    - Generate random text strings and random glossary term pairs
    - Assert after `apply()`, no whole-word occurrence of any source term remains; no partial-word match was replaced
    - **Validates: Requirements 3.2**

  - [x] 4.4 Write property test for `Glossary_Store` — Property 6: Glossary capitalisation preservation
    - **Property 6: Glossary capitalisation preservation**
    - Generate random glossary target terms and random capitalisation patterns (all-caps, title-case, lowercase)
    - Assert `_match_case(token, target)` produces the correct capitalisation for each pattern
    - **Validates: Requirements 3.3**

- [x] 5. Checkpoint — core translation components
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement `Font_Mapper`
  - [x] 6.1 Write the `Font_Mapper` class in `document_translator_v3.py`
    - Implement `resolve(font_name, embedded_fonts) -> str`
    - Case-insensitive exact match against `embedded_fonts` → return `font_name`
    - Classify by `SANS_SERIF_KEYWORDS`, `SERIF_KEYWORDS`, `MONO_KEYWORDS` → return `"helv"`, `"tiro"`, or `"cour"`
    - Unknown or exception → return `"helv"` and log a warning with page/bbox
    - Update `read_pdf()` to store `block["style"]["font"]` from the dominant span's `span["font"]` field
    - Update `write_pdf_preserved()` to call `Font_Mapper.resolve()` per block, passing `set` of font names from `fitz.Document.get_page_fonts()`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 6.2 Write unit tests for `Font_Mapper`
    - `"ArialMT"` not in embedded fonts → `"helv"`
    - `"TimesNewRomanPS"` not in embedded fonts → `"tiro"`
    - `"CourierNew"` not in embedded fonts → `"cour"`
    - Font name in embedded fonts → returns that font name unchanged
    - Unknown font name → `"helv"` with warning
    - _Requirements: 4.2, 4.3, 4.4_

- [x] 7. Implement `Background_Sampler`
  - [x] 7.1 Write the `Background_Sampler` class in `document_translator_v3.py`
    - Implement `sample(page, bbox) -> tuple[float,float,float] | None`
    - Render page to pixmap via `page.get_pixmap()`; clamp corner coordinates to page bounds before sampling
    - Return `(r, g, b)` floats in `[0,1]` if all four corners match exactly; return `None` if corners differ
    - Return `None` (no exception) for zero-width or zero-height bbox
    - Return `None` and log a warning on any exception
    - Update `write_pdf_preserved()`: call `Background_Sampler.sample()` before drawing the erase rect; use returned color as fill, or use clip-and-redraw strategy when `None`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 7.2 Write unit tests for `Background_Sampler`
    - Zero-width bbox → returns `None`, no exception
    - Zero-height bbox → returns `None`, no exception
    - Uniform color corners → returns that color tuple
    - Mixed color corners → returns `None`
    - _Requirements: 5.1, 5.2, 5.5_

- [x] 8. Implement PDF overflow containment
  - [x] 8.1 Replace the overflow handling block inside `write_pdf_preserved()` in `document_translator_v3.py`
    - Step 1: `insert_textbox()` with original rect; if `remaining >= 0`, done
    - Step 2: check if expanding downward by `abs(remaining) + font_size` would bring bottom within 2pt of any other block on the page
    - Step 3: if no collision, expand rect and re-insert
    - Step 4: if collision, reduce `font_size` by 1pt and retry from step 1; repeat until `font_size == 6`
    - Step 5: if still overflowing at 6pt, insert remaining text in a continuation box of same width placed 4pt below the last block on the page
    - Step 6: if continuation box extends beyond page bottom, clip to page boundary and log a warning
    - All other blocks on the page are read-only during this process
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 8.2 Write unit tests for PDF overflow containment
    - No overflow: no font size change, no continuation box
    - Overflow with space below: rect expanded, no font reduction
    - Overflow with adjacent block collision: font reduced until fits
    - Font reaches 6pt: continuation box created
    - Continuation box beyond page bottom: clipped, warning logged
    - _Requirements: 6.2, 6.3, 6.4, 6.6_

  - [x] 8.3 Write property test for overflow containment — Property 7: Overflow resolution does not move other blocks
    - **Property 7: Overflow resolution does not move other blocks**
    - Generate random page layouts with multiple blocks, one designated as overflowing
    - Assert after overflow resolution, all non-overflowing blocks have unchanged `position` values
    - **Validates: Requirements 6.5**

- [x] 9. Checkpoint — PDF writer components
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement `Style_Mapper`
  - [x] 10.1 Write the `Style_Mapper` class in `document_translator_v3.py`
    - Implement `resolve(style_name, available_styles) -> str`
    - Return `style_name` if it is in `available_styles`; return `"Normal"` for `None`, empty string, or unknown name
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 10.2 Write unit tests for `Style_Mapper`
    - Known style name in available styles → returned as-is
    - `None` → `"Normal"`
    - Empty string → `"Normal"`
    - Unknown style name → `"Normal"`
    - _Requirements: 7.2, 7.3_

- [x] 11. Implement `read_docx` v2 and `write_docx` v2 (DOCX_Writer v2)
  - [x] 11.1 Update `read_docx()` in `document_translator_v3.py` to extract full style and table metadata
    - Extract `para.style.name`, `para.alignment`, `para.paragraph_format.space_before`, `para.paragraph_format.space_after`, and `run.font.color.rgb` per run
    - Store all extracted fields in `block["style"]` under keys `style_name`, `alignment`, `space_before`, `space_after`, `font_color`
    - Extract all tables: iterate `doc.tables`, store each cell as `{"type": "table_cell", "text": ..., "table_index": int, "row": int, "col": int, "row_span": int, "col_span": int, "style": {"bold": ..., "font_size": ...}}`
    - Append table cell blocks to the returned block list after paragraph blocks
    - _Requirements: 7.1, 7.4, 7.5, 7.6, 8.1_

  - [x] 11.2 Update `write_docx()` in `document_translator_v3.py` to reconstruct styles, formatting, and tables
    - Use `Style_Mapper.resolve()` to apply paragraph style; copy `alignment`, `space_before`, `space_after` when set
    - Copy `run.font.color.rgb` when `font_color` is set in block style
    - Group `table_cell` blocks by `table_index`; reconstruct each table at the correct body position index using `doc.add_table()`; apply merged cell spans; set run bold and font size when explicitly set in source
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.6, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 11.3 Write unit tests for DOCX_Writer v2
    - Paragraph style name extracted and applied correctly
    - Alignment copied to output paragraph
    - `space_before` / `space_after` copied when set; not set when source is `None`
    - Run font color copied when set
    - Table row/column count preserved
    - Merged cell spans preserved
    - Empty cells not translated
    - Table position index preserved in document body
    - _Requirements: 7.2, 7.4, 7.5, 7.6, 8.2, 8.3, 8.5, 8.6_

  - [x] 11.4 Write property test for DOCX_Writer v2 — Property 8: DOCX paragraph style round-trip
    - **Property 8: DOCX paragraph style round-trip**
    - Generate random lists of paragraph style names from the set of standard DOCX styles
    - Assert output paragraph style name equals source style name for every paragraph whose style exists in the output document
    - **Validates: Requirements 7.2**

  - [x] 11.5 Write property test for DOCX_Writer v2 — Property 9: DOCX paragraph formatting preservation
    - **Property 9: DOCX paragraph formatting preservation**
    - Generate random alignment values and spacing values (Pt objects)
    - Assert output alignment and spacing match source values when explicitly set
    - **Validates: Requirements 7.4, 7.5**

  - [x] 11.6 Write property test for DOCX_Writer v2 — Property 10: DOCX run font color preservation
    - **Property 10: DOCX run font color preservation**
    - Generate random `RGBColor` values
    - Assert output run `font.color.rgb` equals source run `font.color.rgb`
    - **Validates: Requirements 7.6**

  - [x] 11.7 Write property test for DOCX_Writer v2 — Property 11: Table cell translation completeness
    - **Property 11: Table cell translation completeness**
    - Generate random tables with a mix of empty and non-empty cells
    - Assert non-empty cells are translated (text changed or at minimum processed), empty cells remain empty
    - **Validates: Requirements 8.2**

  - [x] 11.8 Write property test for DOCX_Writer v2 — Property 12: Table structural preservation
    - **Property 12: Table structural preservation**
    - Generate random table dimensions (rows 1–10, cols 1–10) with random merge spans
    - Assert output table has same row count, column count, and merge spans as source
    - **Validates: Requirements 8.3**

  - [x] 11.9 Write property test for DOCX_Writer v2 — Property 13: Table run formatting preservation
    - **Property 13: Table run formatting preservation**
    - Generate random bold (True/False/None) and font size (None or 6–72pt) values per run
    - Assert output run bold and font size match source when explicitly set; unset when source is unset
    - **Validates: Requirements 8.4**

- [x] 12. Checkpoint — DOCX writer components
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Implement `BLEU_Reporter`
  - [x] 13.1 Write the `BLEU_Reporter` class in `document_translator_v3.py`
    - Implement `compute(translated_blocks, reference_file) -> float | None`
    - Read `reference_file` (one block per non-empty line); align by index up to `min(len(translated_blocks), len(ref_lines))`
    - Log a warning if counts differ
    - Return `sacrebleu` corpus BLEU score (0.0–100.0), or `None` on any read/parse error (log warning with path and error)
    - Update `run_pipeline()` to accept optional `reference_file=None` parameter; call `BLEU_Reporter.compute()` at the end of the pipeline
    - Change `run_pipeline()` return value from `(output_file, translated_blocks)` to `{"output_file": ..., "translated_blocks": ..., "bleu_score": float | None}`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 13.2 Write unit tests for `BLEU_Reporter`
    - No reference file: `bleu_score` is `None`, no error raised
    - Matching counts: BLEU score is a float in `[0, 100]`
    - Mismatched counts: BLEU computed over aligned pairs, warning printed
    - Unreadable file: `bleu_score` is `None`, warning printed
    - _Requirements: 9.2, 9.3, 9.4, 9.6_

- [x] 14. Implement `Column_Detector` v2
  - [x] 14.1 Write the `detect_columns(blocks, page_width)` function in `document_translator_v3.py`
    - Use x-coordinate gap analysis: gap ≥ 10% of `page_width` between rightmost edge of one group and leftmost edge of next group → column boundary
    - Support 1, 2, or 3 columns per page
    - Extract full-width blocks (width ≥ 90% of `page_width`) first; interleave with columnar blocks by y-coordinate
    - Sort blocks within each column by top y-coordinate; merge columns left-to-right
    - Fall back to single-column (all blocks sorted by y) if < 2 blocks per candidate column
    - Replace the `_detect_columns()` call in `read_pdf()` with `detect_columns()`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 14.2 Write unit tests for `Column_Detector` v2
    - Single-column page: all blocks returned sorted by y
    - Two-column page with 15% gap: two columns detected
    - Two-column page with 8% gap: treated as single column
    - Three-column page: three columns detected
    - Full-width block above columnar blocks: appears first in output
    - Fewer than 2 blocks per candidate column: single-column fallback
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 14.3 Write property test for `Column_Detector` v2 — Property 14: Column gap threshold
    - **Property 14: Column gap threshold**
    - Generate random page widths and block x-positions with gaps of varying sizes
    - Assert column boundary detected if and only if gap ≥ 10% of page width
    - **Validates: Requirements 10.1**

  - [x] 14.4 Write property test for `Column_Detector` v2 — Property 15: Column reading order
    - **Property 15: Column reading order**
    - Generate random multi-column block layouts with shuffled y-coordinates
    - Assert within each column group blocks are sorted by top y-coordinate; column groups appear left-to-right
    - **Validates: Requirements 10.3**

  - [x] 14.5 Write property test for `Column_Detector` v2 — Property 16: Full-width block ordering
    - **Property 16: Full-width block ordering**
    - Generate random pages with full-width blocks and columnar blocks at various y-positions
    - Assert each full-width block precedes all columnar blocks whose top y-coordinate is greater than the full-width block's top y-coordinate
    - **Validates: Requirements 10.4**

- [x] 15. Wire all components into `run_pipeline()` and integration pass
  - [x] 15.1 Audit `run_pipeline()` and all call sites in `document_translator_v3.py`
    - Confirm `Chunk_Splitter` replaces `_split_long_text` everywhere
    - Confirm `Context_Buffer` is instantiated once per call and `clear()` is called at start
    - Confirm `Glossary_Store` is instantiated from the `glossary` parameter (or skipped when `None`)
    - Confirm `BLEU_Reporter` is called at the end when `reference_file` is not `None`
    - Confirm return value is the new result dict `{"output_file", "translated_blocks", "bleu_score"}`
    - Confirm `detect_columns` replaces `_detect_columns` in `read_pdf()`
    - _Requirements: 1.5, 2.1, 3.1, 9.3, 10.1_

  - [x] 15.2 Write integration smoke tests
    - Translate a minimal synthetic DOCX (2 paragraphs + 1 table) end-to-end; assert output file exists and result dict has all three keys
    - Translate a minimal synthetic PDF (2 blocks, 2 columns) end-to-end; assert output file exists
    - _Requirements: 1.5, 2.1, 3.1, 7.1, 8.1, 9.3, 10.1_

- [x] 16. Final checkpoint — full test suite
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Checkpoints at tasks 5, 9, 12, and 16 ensure incremental validation
- Property tests validate universal correctness properties across all valid inputs
- Unit tests validate specific examples and edge cases
- `server.py` and the Laravel layer are out of scope — do not modify them
- The `run_pipeline()` public signature is preserved; new parameters (`glossary`, `reference_file`) use `None` defaults so existing callers are unaffected

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "3.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "3.2", "3.3", "4.2", "4.3", "4.4"] },
    { "id": 3, "tasks": ["6.1", "7.1", "8.1", "10.1", "11.1"] },
    { "id": 4, "tasks": ["6.2", "7.2", "8.2", "8.3", "10.2", "11.2", "14.1"] },
    { "id": 5, "tasks": ["11.3", "11.4", "11.5", "11.6", "11.7", "11.8", "11.9", "14.2", "14.3", "14.4", "14.5"] },
    { "id": 6, "tasks": ["13.1"] },
    { "id": 7, "tasks": ["13.2", "15.1"] },
    { "id": 8, "tasks": ["15.2"] }
  ]
}
```
