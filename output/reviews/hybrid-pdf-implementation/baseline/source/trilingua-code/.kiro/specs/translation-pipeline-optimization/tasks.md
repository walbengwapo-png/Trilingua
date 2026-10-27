# Implementation Plan: Translation Pipeline Optimization

## Overview

Implement eleven targeted fixes to `Model/document_translator_v3.py`. The work is grouped by concern: new classes (`Chunk_Splitter`, `Font_Mapper`, `Style_Mapper`), a new helper function (`_resolve_overflow`), dead-code removal, and format-specific repairs (PDF column detection, DOCX multi-run/header-footer, CSV language-code, PPTX notes/tables). A separate `Model/tests/test_properties.py` file holds all Hypothesis property tests. The existing `Model/tests/test_units.py` is never modified.

## Tasks

- [x] 1. Scaffold `test_properties.py` and verify import smoke tests
  - [x] 1.1 Create `Model/tests/test_properties.py` with the file-level import block and six smoke-test assertions confirming `Chunk_Splitter`, `Context_Buffer`, `Glossary_Store`, `Font_Mapper`, `Style_Mapper`, and `_resolve_overflow` are importable from `document_translator_v3`
    - Add `from document_translator_v3 import Chunk_Splitter, Context_Buffer, Glossary_Store, Font_Mapper, Style_Mapper, _resolve_overflow` and a pytest smoke test that asserts each symbol is not `None`
    - These tests will initially fail (symbols don't exist yet) and turn green incrementally as each class is added
    - _Requirements: 12.1, 12.2_

- [ ] 2. Implement `Chunk_Splitter` class
  - [-] 2.1 Add `Chunk_Splitter` at module scope in `Model/document_translator_v3.py`
    - Implement the `split(self, text, max_tokens=400, hard_cap=600, min_tokens=10)` method using the word-token model described in the design (steps 1–9)
    - Handle the empty/whitespace edge case: return `[""]`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_
  - [ ]* 2.2 Write property test for `Chunk_Splitter` — Property 1: round-trip
    - **Property 1: Chunk_Splitter round-trip preserves all words**
    - **Validates: Requirements 1.8**
    - Use `@given(st.text(min_size=1))` with `@settings(max_examples=100)`
    - Assert `" ".join(w for c in chunks for w in c.split()) == " ".join(text.split())`
  - [ ]* 2.3 Write property test for `Chunk_Splitter` — Property 2: short text never split
    - **Property 2: Short text is never split**
    - **Validates: Requirements 1.3**
    - Use `@given(st.integers(min_value=1, max_value=80), st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=80))` to generate (max_tokens, word_list) pairs where `len(word_list) <= max_tokens`
    - Assert result is a single-element list equal to the original text
  - [ ]* 2.4 Write property test for `Chunk_Splitter` — Property 3: min_tokens respected
    - **Property 3: Split respects sentence boundaries and min_tokens**
    - **Validates: Requirements 1.7**
    - Use `@given(st.text(min_size=1), st.integers(min_value=1, max_value=20))` for `(text, min_tokens)`
    - Assert every chunk contains `>= min_tokens` tokens unless the whole input is shorter

- [ ] 3. Wire `Chunk_Splitter` into `batch_translate_blocks()`
  - [-] 3.1 In `batch_translate_blocks()`, replace the direct `_translate_single(block["text"], ...)` call with a loop that calls `Chunk_Splitter().split(block["text"])`, invokes `_translate_single()` once per chunk, and rejoins the translated chunks with `" ".join(translated_chunks)`
    - Honour `context_buffer` integration at the block level (not the chunk level): call `context_buffer.get_hint()` once before the chunk loop and `context_buffer.push()` once after the rejoin (only on success)
    - _Requirements: 1.10, 3.1, 3.2, 3.3_

- [ ] 4. Implement token budget enforcement in `_translate_with_mistral()`
  - [-] 4.1 Inside `_translate_with_mistral()`, compute `estimated_input_tokens = len(prompt_string) // 4` before building the `requests.post` payload; set `dynamic_max_tokens = max(1, 4096 - estimated_input_tokens)` if `estimated_input_tokens > 1500`, else `2048`; log `[TOKEN BUDGET]` warning if `estimated_input_tokens > 3500`
    - Replace the existing hard-coded `max_tokens=2048` with `dynamic_max_tokens`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 5. Remove dead `Context_Buffer` construction from `batch_translate_blocks()`
  - [x] 5.1 Delete the unconditional `ctx = Context_Buffer()` line and any associated `ctx.get_hint()` / `ctx.push()` calls; replace with `hint = context_buffer.get_hint() if context_buffer is not None else ""`
    - Ensure the `Context_Buffer` class definition itself is left untouched and remains importable
    - _Requirements: 3.1, 3.4_

- [ ] 6. Re-enable PDF column detection in `read_pdf()`
  - [-] 6.1 Replace the unconditional `selected = merged` assignment with the `match column_mode` block described in the design, including the `"auto"`, `"single"`, `"left"`, `"right"`, and invalid-mode `ValueError` branches
    - Add the `[COLUMN FALLBACK]` log line inside the `"auto"` branch when `detect_columns()` returns < 50% of the input block count
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - [ ]* 6.2 Write property test for column filter — Property 4: left/right modes
    - **Property 4: PDF column filter correctness — left/right modes**
    - **Validates: Requirements 4.3, 4.4**
    - Use `@given(st.lists(st.builds(dict, position=st.lists(st.floats(min_value=0, max_value=1000), min_size=4, max_size=4)), min_size=0), st.floats(min_value=1, max_value=2000))` for `(blocks, page_width)`
    - Assert all returned blocks satisfy the correct centre-x condition and are sorted by `position[1]`

- [x] 7. Implement `Font_Mapper` class
  - [x] 7.1 Add `Font_Mapper` at module scope in `Model/document_translator_v3.py`
    - Implement `resolve(self, font_name, embedded_fonts, *, page=None, bbox=None)` with the six-priority resolution chain from the design; print `⚠️` warning for `None`/empty and unknown-font cases
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_
  - [ ]* 7.2 Write property test for `Font_Mapper` — Property 5: keyword classification
    - **Property 5: Font_Mapper keyword classification**
    - **Validates: Requirements 5.3, 5.4, 5.5**
    - Use `@given(st.sampled_from(["courier","consolas","mono","times","georgia","roman","arial","helvetica","sans"]), st.text(), st.text())` to build font names with a keyword somewhere in the string
    - Assert the correct return value (`"cour"`, `"tiro"`, or `"helv"`) with monospace priority
  - [ ]* 7.3 Write property test for `Font_Mapper` — Property 6: embedded-font passthrough
    - **Property 6: Font_Mapper embedded-font passthrough**
    - **Validates: Requirements 5.2**
    - Use `@given(st.text(min_size=1))` for a font name `f`; build `embedded_fonts = {f.lower()}`
    - Assert `Font_Mapper().resolve(f, embedded_fonts) == f`

- [ ] 8. Wire `Font_Mapper` into `write_pdf_preserved()`
  - [~] 8.1 In `write_pdf_preserved()`, build `embedded_fonts` once per page using `fitz.Document.get_page_fonts()`; replace the inline `FONT_MAP` dict and `_resolve_font()` helper with a call to `Font_Mapper().resolve(style.get("font"), embedded_fonts)` for every block
    - _Requirements: 5.8_

- [ ] 9. Implement `_resolve_overflow()` top-level function
  - [-] 9.1 Add `_resolve_overflow(page, block_text, x0, y0, x1, y1, font_size, resolved_font, other_bboxes, page_height, original_doc, page_num, bg_color, initial_remaining, text_color=(0,0,0), align=0)` at module scope
    - Implement the four-step algorithm: no-overflow early return → downward expansion (collision check within 2 pt) → font reduction loop (down to 7 pt) → continuation block return
    - Return the `{"resolved", "continuation", "expanded", "final_font"}` dict in all branches
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - [ ]* 9.2 Write property test for `_resolve_overflow` — Property 7: no-op when no overflow
    - **Property 7: _resolve_overflow no-op when no overflow**
    - **Validates: Requirements 6.2**
    - Use `@given(st.floats(min_value=0.0, max_value=10000.0))` for `initial_remaining`; mock `page` with a `MagicMock` that tracks `insert_textbox` calls
    - Assert return equals `{"resolved": True, "continuation": False, "expanded": False, "final_font": font_size}` and `insert_textbox` was never called
  - [ ]* 9.3 Write property test for `_resolve_overflow` — Property 8: downward expansion preserves font size
    - **Property 8: _resolve_overflow downward expansion preserves font size**
    - **Validates: Requirements 6.3**
    - Use `@given(st.floats(max_value=-0.001))` for `initial_remaining`; configure mock page to return `>= 0` for `insert_textbox`; set `other_bboxes=[]` and a large `page_height`
    - Assert `expanded=True`, `final_font == font_size`, and `insert_textbox` called exactly once

- [ ] 10. Wire `_resolve_overflow()` into `write_pdf_preserved()`
  - [~] 10.1 In `write_pdf_preserved()`, when `page.insert_textbox()` returns a negative value, replace the existing inline font-shrink loop with a call to `_resolve_overflow()` passing all required arguments; handle the returned dict to optionally enqueue a continuation block
    - _Requirements: 6.6_

- [ ] 11. Preserve DOCX multi-run formatting in `translate_docx_inplace()`
  - [-] 11.1 Extract the paragraph-level translation logic into a `_apply_translation_to_paragraph(para, translated_text, glossary_store)` helper; implement the single-run fast path and the multi-run proportional-distribution algorithm from the design; ensure `run.bold`, `run.italic`, `run.font.size`, and `run.font.color.rgb` are never assigned
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [ ]* 11.2 Write property test for DOCX multi-run distribution — Property 11
    - **Property 11: DOCX multi-run distribution covers all translated text**
    - **Validates: Requirements 7.2**
    - Use `@given(st.lists(st.text(min_size=0), min_size=2, max_size=10), st.text(min_size=0))` for `(run_texts, translated_text)`; build mock `Run` objects preserving `bold`/`italic` values
    - Assert concatenation of updated `run.text` values equals `translated_text`, and formatting attributes are unchanged

- [ ] 12. Translate DOCX headers and footers in `translate_docx_inplace()`
  - [~] 12.1 After the body-paragraph loop in `translate_docx_inplace()`, iterate every `section` in `doc.sections`; for each of the six header/footer objects (`header`, `footer`, `first_page_header`, `first_page_footer`, `even_page_header`, `even_page_footer`), skip if `is_linked_to_previous`; translate non-empty paragraphs using `_translate_single()` with `block_type="header"` or `"footer"`
    - Update the `total` count computed before translation begins to include non-empty paragraphs from all non-linked section headers and footers
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 13. Implement `Style_Mapper` class
  - [x] 13.1 Add `Style_Mapper` at module scope in `Model/document_translator_v3.py`
    - Implement `resolve(self, style_name, available_styles)` that returns `style_name` unchanged if it is a non-empty string present in `available_styles`, and returns `"Normal"` in all other cases
    - _Requirements: 9.1, 9.2, 9.3_
  - [ ]* 13.2 Write property test for `Style_Mapper` — Property 9: identity for known styles
    - **Property 9: Style_Mapper identity for known styles**
    - **Validates: Requirements 9.2**
    - Use `@given(st.sets(st.text(min_size=1), min_size=1))` for `available_styles`; draw a member of that set as `style_name`
    - Assert `Style_Mapper().resolve(style_name, available_styles) == style_name`
  - [ ]* 13.3 Write property test for `Style_Mapper` — Property 10: fallback for all invalid inputs
    - **Property 10: Style_Mapper falls back to "Normal" for all invalid inputs**
    - **Validates: Requirements 9.3**
    - Use `@given(st.one_of(st.none(), st.just(""), st.text()))` for `style_name`; use `@given(st.sets(st.text(min_size=1)))` for `available_styles`; filter to cases where `style_name` is not in `available_styles`
    - Assert return value is `"Normal"`

- [ ] 14. Wire `Style_Mapper` into `write_docx()`
  - [-] 14.1 In the new-document code path of `write_docx()`, build `available_styles = {s.name for s in new_doc.styles}`; replace the direct `style_info.get("style_name", "Normal")` lookup with `Style_Mapper().resolve(style_info.get("style_name"), available_styles)`
    - _Requirements: 9.4_

- [ ] 15. Fix the CSV language-code round-trip in `run_pipeline()`
  - [ ] 15.1 In the CSV branch of `run_pipeline()`, remove the `LANGUAGES[source_lang]` / `LANGUAGES[target_lang]` lookups and pass `source_lang` and `target_lang` (human-readable names) directly as the `src_code` and `tgt_code` arguments to `_translate_single()`; verify that `_translate_single()` already has the `CODE_TO_LANG.get(src_code, src_code)` fallback and add it if missing
    - Do not modify `LANGUAGES` or `CODE_TO_LANG`
    - _Requirements: 10.1, 10.2, 10.3_

- [ ] 16. Extract PPTX notes and table shapes in `read_pptx()` and `translate_pptx_inplace()`
  - [~] 16.1 In `read_pptx()`, after the existing text-frame shape loop for each slide, add the notes-slide iteration block and the table-shape iteration block from the design; append blocks with `"type": "notes"` and `"type": "table_cell"` including all required key fields
    - _Requirements: 11.1, 11.2_
  - [~] 16.2 In `translate_pptx_inplace()`, build `notes_map` and `table_map` dicts keyed by `(slide, shape_id, para_idx)` and `(slide, shape_id, row, col)` respectively; after the existing shape-translation loop, add the notes-slide write-back loop and the table-cell write-back loop
    - _Requirements: 11.3, 11.4_
  - [ ]* 16.3 Write property test for PPTX read/write round-trip — Property 12
    - **Property 12: PPTX read/write round-trip for notes and table cells**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4**
    - Use `@given(st.lists(st.tuples(st.integers(0,5), st.integers(1,20), st.integers(0,5)), min_size=1))` to generate `(slide, shape_id, para_idx)` tuples; build a mock notes_map from these keys and assert every key resolves to exactly one block

- [~] 17. Final checkpoint — ensure all tests pass
  - Run `pytest Model/tests/test_units.py -v` and confirm zero failures and zero import errors
  - Run `pytest Model/tests/test_properties.py -v` and confirm all property tests pass
  - Run `pytest Model/tests/ -v` for the combined suite
  - Ensure all tasks pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All implementation is confined to `Model/document_translator_v3.py` (new symbols added at module scope) and the new `Model/tests/test_properties.py`; `Model/tests/test_units.py` is never modified
- The six symbols `Chunk_Splitter`, `Context_Buffer`, `Glossary_Store`, `Font_Mapper`, `Style_Mapper`, `_resolve_overflow` must exist at module scope by the time any test collection runs (Req 12)
- Property tests use Hypothesis `@settings(max_examples=100)` and the tag format `# Feature: translation-pipeline-optimization, Property {N}: {property_text}`
- Tasks 3.1 and 5.1 both touch `batch_translate_blocks()`; implement 5.1 first (dead-code removal) then 3.1 (Chunk_Splitter wiring) to avoid merge conflicts
- Tasks 8.1 and 10.1 both touch `write_pdf_preserved()`; implement them in sequence (font mapper first, then overflow resolver) within a single editing session

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "9.1", "13.1"] },
    { "id": 2, "tasks": ["5.1", "7.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4", "3.1", "4.1", "6.1", "7.2", "7.3", "11.1", "13.2", "13.3", "14.1", "15.1"] },
    { "id": 4, "tasks": ["6.2", "8.1", "9.2", "9.3", "11.2", "12.1", "16.1"] },
    { "id": 5, "tasks": ["10.1", "16.2", "16.3"] }
  ]
}
```
