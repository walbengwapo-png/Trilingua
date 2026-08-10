# Design Document: Translation Pipeline Optimization

## Overview

This document describes the technical design for fixing ten defects in `Model/document_translator_v3.py`, the Python microservice powering Trilingua's document translation pipeline.

The changes are surgical: each fix is confined to a single well-defined responsibility. No existing public API signatures are broken. All new symbols are added at module scope so the existing test suite in `Model/tests/test_units.py` imports cleanly.

### Goals

1. Prevent mid-sentence truncation via a `Chunk_Splitter` class.
2. Enforce dynamic token budgets in `_translate_with_mistral`.
3. Remove the dead `Context_Buffer` construction inside `batch_translate_blocks`.
4. Re-enable PDF column detection so `column_mode` is honoured.
5. Centralise PDF font resolution in a `Font_Mapper` class.
6. Replace inline PDF overflow logic with a `_resolve_overflow` function.
7. Preserve per-run DOCX formatting during translation.
8. Translate DOCX headers and footers.
9. Centralise DOCX style resolution in a `Style_Mapper` class.
10. Fix the fragile CSV language-code round-trip.
11. Extract PPTX notes slides and table shapes during reading.

### Non-Goals

- No changes to the Laravel/PHP layer.
- No new external Python packages.
- No alterations to existing class constructors or function signatures beyond what the requirements specify.

---

## Architecture

The microservice is a single Python module (`document_translator_v3.py`) with no internal sub-packages. The translation pipeline follows a read → translate → write pattern:

```
run_pipeline()
  ├── analyze_document()        ← reads source file, returns blocks + ext
  │     └── read_pdf / read_docx / read_pptx / ...
  ├── batch_translate_blocks()  ← translates list of blocks via Mistral API
  │     ├── Chunk_Splitter      ← NEW: splits long blocks before API call
  │     └── _translate_single() → _translate_with_mistral()
  └── reconstruct_document()   ← writes translated blocks to output file
        └── write_pdf_preserved / write_docx / write_pptx / ...
```

For DOCX, PPTX, and XLSX the pipeline bypasses the read→batch→write path and uses dedicated in-place translators (`translate_docx_inplace`, `translate_pptx_inplace`, `translate_xlsx_inplace`) that open the original file and update it directly.

All ten fixes remain inside this single module. The class hierarchy after the changes:

```
document_translator_v3.py
  ├── Chunk_Splitter          ← NEW (Req 1)
  ├── Context_Buffer          (existing, kept for importability)
  ├── Glossary_Store          (existing, unchanged)
  ├── Font_Mapper             ← NEW (Req 5)
  ├── Style_Mapper            ← NEW (Req 9)
  └── _resolve_overflow()     ← NEW top-level function (Req 6)
```

---

## Components and Interfaces

### 1. `Chunk_Splitter` (new class, Req 1)

Responsible for splitting a long text block into translation-safe chunks at sentence boundaries before the Mistral API is called.

```python
class Chunk_Splitter:
    def split(
        self,
        text: str,
        max_tokens: int = 400,
        hard_cap: int = 600,
        min_tokens: int = 10,
    ) -> list[str]:
        ...
```

**Algorithm** (word-token model; one token = one whitespace-delimited word):

1. If `len(text.split()) <= max_tokens`, return `[text]`.
2. Scan tokens left-to-right; record the index of every token that ends with `.`, `!`, or `?` as a candidate split boundary.
3. Pick the **last** candidate boundary at or before `max_tokens` as the preferred split point.
4. If no candidate exists within `max_tokens`, extend the search up to `hard_cap`; pick the first candidate found.
5. If no candidate exists anywhere within `hard_cap`, return `[text]` (no split).
6. Split: `first_chunk = tokens[:boundary+1]`, `remainder = tokens[boundary+1:]`.
7. If `len(remainder) < min_tokens`, merge remainder back into first chunk and return `[text]`.
8. Recursively apply the same logic to `remainder` to produce additional chunks.
9. Guarantee: `" ".join(word for c in result for word in c.split()) == " ".join(text.split())`.

**Integration point:** `batch_translate_blocks()` calls `Chunk_Splitter().split(block["text"])` before each `_translate_single()` call, then rejoins translated chunks with `" ".join(translated_chunks)`.

---

### 2. Token Budget Enforcement (Req 2)

No new class; logic is added inside `_translate_with_mistral()`.

```python
# Before building the requests.post payload:
prompt_string = build_prompt(text, source_lang, target_lang, block_type)
estimated_input_tokens = len(prompt_string) // 4

if estimated_input_tokens > 3500:
    print(f"[TOKEN BUDGET] estimated_input={estimated_input_tokens} source={text[:60]!r}")

if estimated_input_tokens > 1500:
    dynamic_max_tokens = max(1, 4096 - estimated_input_tokens)
else:
    dynamic_max_tokens = 2048   # default
```

**Decision rationale:** The formula `floor(char_count / 4)` approximates BPE tokens at ~4 chars/token, which is conservative enough for English/Cebuano/Filipino. No new dependency needed.

---

### 3. Dead `Context_Buffer` Construction Removal (Req 3)

The current `batch_translate_blocks()` builds a `Context_Buffer` object unconditionally (even when `context_buffer=None`) and calls `context_buffer.get_hint()` without checking whether the argument is `None`. The fix removes the unconditional construction:

```python
# BEFORE (dead code):
ctx = Context_Buffer()  # always built, never used when context_buffer is None

# AFTER:
# No construction. Check the argument directly:
hint = context_buffer.get_hint() if context_buffer is not None else ""
```

The `Context_Buffer` class itself is unchanged and remains importable.

---

### 4. PDF Column Detection Re-enabled (Req 4)

The current `read_pdf()` sets `selected = merged` unconditionally, bypassing `detect_columns()`. The fix wires up the `column_mode` parameter properly:

```python
match column_mode:
    case "single":
        selected = sorted(merged, key=lambda b: b["position"][1])
    case "left":
        selected = sorted(
            [b for b in merged if (b["position"][0]+b["position"][2])/2 < pw/2],
            key=lambda b: b["position"][1],
        )
    case "right":
        selected = sorted(
            [b for b in merged if (b["position"][0]+b["position"][2])/2 >= pw/2],
            key=lambda b: b["position"][1],
        )
    case "auto":
        result = detect_columns(merged, pw)
        if len(result) < 0.5 * len(merged):
            print(f"[COLUMN FALLBACK] page {page_num}: detect_columns returned "
                  f"{len(result)}/{len(merged)} blocks — falling back to single column")
            selected = sorted(merged, key=lambda b: b["position"][1])
        else:
            selected = result
    case _:
        raise ValueError(
            f"Invalid column_mode {column_mode!r}. "
            "Accepted values: 'auto', 'single', 'left', 'right'."
        )
```

**Note:** The existing `detect_columns()` function already contains its own >50% fallback guard; the outer `read_pdf()` guard is an additional safety net that also emits the required `[COLUMN FALLBACK]` log line.

---

### 5. `Font_Mapper` (new class, Req 5)

Centralises all PDF font-name resolution logic for `write_pdf_preserved()`.

```python
class Font_Mapper:
    _MONO_KEYWORDS  = ("courier", "consolas", "mono")
    _SERIF_KEYWORDS = ("times", "georgia", "roman")
    _SANS_KEYWORDS  = ("arial", "helvetica", "sans")

    def resolve(
        self,
        font_name: str | None,
        embedded_fonts: set[str],
        *,
        page: int | None = None,
        bbox: list | None = None,
    ) -> str:
        ...
```

**Resolution priority (highest to lowest):**

1. If `font_name` is `None` or empty string → return `"helv"` and print `⚠️` warning.
2. If `font_name.lower()` matches any element of `embedded_fonts` lowercased → return `font_name` as-is (preserve caller's case).
3. If `font_name.lower()` contains any monospace keyword → return `"cour"`.
4. If `font_name.lower()` contains any serif keyword → return `"tiro"`.
5. If `font_name.lower()` contains any sans-serif keyword → return `"helv"`.
6. Otherwise → return `"helv"` and print a `⚠️` warning including the font name.

`write_pdf_preserved()` replaces its inline `FONT_MAP` dict and `_resolve_font()` helper with a call to `Font_Mapper().resolve(style.get("font"), embedded_fonts)`, where `embedded_fonts` is built once per page from `fitz.Document.get_page_fonts()`.

---

### 6. `_resolve_overflow()` (new top-level function, Req 6)

Replaces the inline overflow-handling loop inside `write_pdf_preserved()`.

```python
def _resolve_overflow(
    page,
    block_text: str,
    x0: float, y0: float, x1: float, y1: float,
    font_size: float,
    resolved_font: str,
    other_bboxes: list[list[float]],
    page_height: float,
    original_doc,
    page_num: int,
    bg_color: tuple | None,
    initial_remaining: float,
    text_color: tuple = (0, 0, 0),
    align: int = 0,
) -> dict:
    ...
```

**Return value:** `{"resolved": bool, "continuation": bool, "expanded": bool, "final_font": float}`

**Algorithm:**

1. **No overflow** (`initial_remaining >= 0`): Return immediately with `{"resolved": True, "continuation": False, "expanded": False, "final_font": font_size}` without calling `insert_textbox`.
2. **Attempt downward expansion:**
   - Compute candidate expanded bottom: `new_y1 = y1 + abs(initial_remaining / font_size) * font_size`.
   - Check collision: for each `other_bbox` in `other_bboxes`, if `abs(other_bbox[1] - new_y1) < 2.0`, collision detected.
   - If `new_y1 <= page_height` and no collision: call `page.insert_textbox(fitz.Rect(x0, y0, x1, new_y1), ...)` once. Return `{"resolved": True, "expanded": True, "continuation": False, "final_font": font_size}`.
3. **Attempt font reduction** (expansion blocked): Try each `f` in `range(int(font_size) - 1, 6, -1)` (down to 7 pt). Call `page.insert_textbox(fitz.Rect(x0, y0, x1, y1), ..., fontsize=f)`. First `f` returning `>= 0` → return `{"resolved": True, "expanded": False, "continuation": False, "final_font": f}`.
4. **Continuation block**: All font sizes exhausted. Return `{"resolved": False, "continuation": True, "expanded": False, "final_font": 7}`.

---

### 7. DOCX Multi-Run Formatting Preservation (Req 7)

The current `translate_docx_inplace()` blanks all runs and sets the first run's text — destroying formatting in multi-run paragraphs.

**New algorithm for paragraph translation:**

```python
def _apply_translation_to_paragraph(para, translated_text, glossary_store):
    runs = para.runs
    if not runs:
        para.add_run(translated_text)
        return

    if len(runs) == 1:
        runs[0].text = translated_text   # preserve all formatting attrs
        return

    # Multi-run: proportional distribution
    source = "".join(r.text for r in runs)
    src_len = len(source) if len(source) > 0 else 1
    tgt_len = len(translated_text)

    pos = 0
    for i, run in enumerate(runs):
        if i == len(runs) - 1:
            run.text = translated_text[pos:]  # last run gets remainder
        else:
            budget = math.floor(tgt_len * len(run.text) / src_len)
            run.text = translated_text[pos: pos + budget]
            pos += budget
        # Bold, italic, font size, color are NOT touched
```

**Key invariants:**
- `run.bold`, `run.italic`, `run.font.size`, `run.font.color.rgb` are never assigned.
- A run with zero-length source text receives an empty string; its formatting is not modified.
- The concatenation of all updated `run.text` values equals `translated_text`.

---

### 8. DOCX Headers and Footers Translation (Req 8)

`translate_docx_inplace()` is extended to iterate every `section` in `doc.sections` and translate non-linked header/footer paragraphs:

```python
for section in doc.sections:
    for hf_obj, hf_type in [
        (section.header, "header"),
        (section.footer, "footer"),
        (section.first_page_header, "header"),
        (section.first_page_footer, "footer"),
        (section.even_page_header, "header"),
        (section.even_page_footer, "footer"),
    ]:
        if hf_obj.is_linked_to_previous:
            continue
        for para in hf_obj.paragraphs:
            if not para.text.strip():
                continue
            # translate para using _translate_single with block_type=hf_type
```

**Progress tracking:** The `total` count is computed before translation begins and includes all non-empty header/footer paragraphs from non-linked sections.

---

### 9. `Style_Mapper` (new class, Req 9)

Safely resolves DOCX paragraph style names to avoid `KeyError` on missing styles.

```python
class Style_Mapper:
    def resolve(
        self,
        style_name: str | None,
        available_styles: set[str],
    ) -> str:
        if not style_name:          # None or empty string
            return "Normal"
        if style_name in available_styles:
            return style_name
        return "Normal"             # unconditional fallback
```

**Integration:** `write_docx()` (new-document code path) calls:
```python
available_styles = {s.name for s in new_doc.styles}
resolved = Style_Mapper().resolve(style_info.get("style_name"), available_styles)
para.style = new_doc.styles[resolved]
```

---

### 10. CSV Language-Code Round-Trip Fix (Req 10)

The current CSV branch in `run_pipeline()` performs:
```python
src_code = LANGUAGES[source_lang]   # e.g. "eng_Latn"
tgt_code = LANGUAGES[target_lang]
_translate_single(cell, src_code, tgt_code, ...)
```

`_translate_single()` then looks up `CODE_TO_LANG[src_code]` to get back `"English"` — a pointless round-trip that breaks if `source_lang` is already a name not in `LANGUAGES`.

**Fix:** Pass language names directly:
```python
_translate_single(cell, source_lang, target_lang, ...)
```

`_translate_single()` already handles the case where `src_code` is not a key in `CODE_TO_LANG` by using the value as-is (`CODE_TO_LANG.get(src_code, src_code)`). No changes to `_translate_single()` are needed beyond verifying this fallback is present.

`LANGUAGES` and `CODE_TO_LANG` are left unchanged so non-CSV callers that pass language codes continue to work.

---

### 11. PPTX Notes and Table Shape Extraction (Req 11)

**`read_pptx()` additions:**

After iterating text-frame shapes on each slide, add:

```python
# Notes slide
if slide.has_notes_slide:
    notes_slide = slide.notes_slide
    for shape in notes_slide.shapes:
        if not shape.has_text_frame:
            continue
        for para_idx, para in enumerate(shape.text_frame.paragraphs):
            text = para.text.strip()
            if text:
                blocks.append({
                    "type": "notes", "text": text,
                    "slide": slide_idx, "shape_id": shape.shape_id,
                    "para_idx": para_idx,
                })

# Table shapes
from pptx.util import MSO_SHAPE_TYPE
for shape in slide.shapes:
    if shape.shape_type == MSO_SHAPE_TYPE.TABLE:
        tbl = shape.table
        for row_idx, row in enumerate(tbl.rows):
            for col_idx, cell in enumerate(row.cells):
                text = cell.text.strip()
                if text:
                    blocks.append({
                        "type": "table_cell", "text": text,
                        "slide": slide_idx, "shape_id": shape.shape_id,
                        "row": row_idx, "col": col_idx,
                    })
```

**`translate_pptx_inplace()` additions:**

```python
# Notes lookup
notes_map: dict[tuple, block] = {}
table_map: dict[tuple, block] = {}
for b in translated_blocks:
    if b["type"] == "notes":
        notes_map[(b["slide"], b["shape_id"], b["para_idx"])] = b
    elif b["type"] == "table_cell":
        table_map[(b["slide"], b["shape_id"], b["row"], b["col"])] = b

for slide_idx, slide in enumerate(prs.slides):
    if slide.has_notes_slide:
        ns = slide.notes_slide
        for shape in ns.shapes:
            if not shape.has_text_frame:
                continue
            for para_idx, para in enumerate(shape.text_frame.paragraphs):
                key = (slide_idx, shape.shape_id, para_idx)
                if key in notes_map:
                    _distribute_translated_text(para, notes_map[key]["text"])

    for shape in slide.shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.TABLE:
            tbl = shape.table
            for row_idx, row in enumerate(tbl.rows):
                for col_idx, cell in enumerate(row.cells):
                    key = (slide_idx, shape.shape_id, row_idx, col_idx)
                    if key in table_map:
                        for para in cell.text_frame.paragraphs:
                            _distribute_translated_text(para, table_map[key]["text"])
                            break
```

---

## Data Models

### Block (existing, extended)

All reader functions return a list of block dicts. The existing schema is:

```
{
  "type":     str,       # "paragraph" | "header" | "footer" | "notes" | "table_cell" | ...
  "text":     str,
  "style":    dict,      # {"font_size": float, "font": str, "color": int, "bold": bool}
  "position": list[float],  # [x0, y0, x1, y1], PDF only
  "page":     int,       # PDF only
  "slide":    int,       # PPTX only
  "shape_id": int,       # PPTX only
  "para_idx": int,       # PPTX paragraph blocks and notes blocks
  "row":      int,       # PPTX table_cell and XLSX cell
  "col":      int,       # PPTX table_cell and XLSX cell
}
```

**New fields added by Req 11:**

| Field | Added to types |
|-------|---------------|
| `"type": "notes"` | PPTX notes-slide blocks |
| `"type": "table_cell"` | PPTX table cell blocks (previously only XLSX used this) |

### `_resolve_overflow` return dict

```
{
  "resolved":     bool,   # True if text was successfully placed
  "continuation": bool,   # True if text couldn't fit (caller may create continuation block)
  "expanded":     bool,   # True if the bounding box was expanded downward
  "final_font":   float,  # Font size actually used
}
```

### `Font_Mapper` internal keyword tables

```python
_MONO_KEYWORDS  = ("courier", "consolas", "mono")     # → "cour"
_SERIF_KEYWORDS = ("times", "georgia", "roman")        # → "tiro"
_SANS_KEYWORDS  = ("arial", "helvetica", "sans")       # → "helv"
```

### `Chunk_Splitter` parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_tokens` | 400 | Preferred maximum tokens per chunk (word-count model) |
| `hard_cap` | 600 | Absolute maximum before giving up on splitting |
| `min_tokens` | 10 | Minimum tokens in a trailing chunk; smaller chunks are merged |

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

The following properties were derived from the prework analysis of the acceptance criteria. Each property is suitable for property-based testing (PBT) with a library such as [Hypothesis](https://hypothesis.readthedocs.io/).

---

### Property 1: Chunk_Splitter round-trip preserves all words

*For any* non-empty string `text`, calling `Chunk_Splitter().split(text)` and then joining all chunks — `" ".join(word for c in chunks for word in c.split())` — SHALL equal `" ".join(text.split())`.

No words are dropped, duplicated, or reordered across the split boundary.

**Validates: Requirements 1.8**

---

### Property 2: Short text is never split

*For any* non-empty string `text` whose whitespace-delimited token count is ≤ `max_tokens`, `Chunk_Splitter().split(text, max_tokens=max_tokens)` SHALL return a single-element list whose only element equals `text`.

**Validates: Requirements 1.3**

---

### Property 3: Split respects sentence boundaries and min_tokens

*For any* text and any `min_tokens` value, every chunk in the result of `Chunk_Splitter().split(text, min_tokens=min_tokens)` SHALL contain at least `min_tokens` whitespace-delimited tokens — unless the entire input `text` itself contains fewer than `min_tokens` tokens (in which case the single-element result is allowed to be short).

**Validates: Requirements 1.7**

---

### Property 4: PDF column filter correctness — left/right modes

*For any* list of blocks with random `position` bounding boxes and any `page_width`, when `read_pdf()` is called with `column_mode="left"`, every block in the result SHALL satisfy `(position[0] + position[2]) / 2 < page_width / 2`; when called with `column_mode="right"`, every block in the result SHALL satisfy `(position[0] + position[2]) / 2 >= page_width / 2`. In both cases the result SHALL be sorted in ascending order by `position[1]`.

Properties 4-left and 4-right are combined because they test the same filter mechanism with symmetric inputs.

**Validates: Requirements 4.3, 4.4**

---

### Property 5: Font_Mapper keyword classification

*For any* font name string that (a) is not present in the `embedded_fonts` set and (b) contains at least one monospace keyword (`courier`, `consolas`, `mono`), `Font_Mapper().resolve(font_name, embedded_fonts)` SHALL return `"cour"`. Similarly, a font name containing a serif keyword (`times`, `georgia`, `roman`) SHALL return `"tiro"`, and a font name containing a sans-serif keyword (`arial`, `helvetica`, `sans`) SHALL return `"helv"`. Monospace keywords take priority over serif and sans-serif keywords.

**Validates: Requirements 5.3, 5.4, 5.5**

---

### Property 6: Font_Mapper embedded-font passthrough

*For any* font name `f` and any `embedded_fonts` set that contains `f` (under case-insensitive matching), `Font_Mapper().resolve(f, embedded_fonts)` SHALL return `f` unchanged (the caller's exact casing is preserved).

**Validates: Requirements 5.2**

---

### Property 7: _resolve_overflow no-op when no overflow

*For any* positive value of `initial_remaining`, `_resolve_overflow(page, ..., initial_remaining=initial_remaining)` SHALL return `{"resolved": True, "continuation": False, "expanded": False, "final_font": font_size}` without calling `page.insert_textbox()`.

**Validates: Requirements 6.2**

---

### Property 8: _resolve_overflow downward expansion preserves font size

*For any* overflow scenario (`initial_remaining < 0`) where no collision exists within `2 pt` of the expanded bottom edge and the expanded bounding box does not exceed `page_height`, `_resolve_overflow()` SHALL return `{"resolved": True, "expanded": True, "final_font": font_size}` (the original font size is unchanged) and SHALL call `page.insert_textbox()` exactly once.

**Validates: Requirements 6.3**

---

### Property 9: Style_Mapper identity for known styles

*For any* non-empty style name `s` and any `available_styles` set that contains `s`, `Style_Mapper().resolve(s, available_styles)` SHALL return `s` unchanged.

**Validates: Requirements 9.2**

---

### Property 10: Style_Mapper falls back to "Normal" for all invalid inputs

*For any* value of `style_name` that is either `None`, an empty string, or a non-empty string not present in `available_styles`, `Style_Mapper().resolve(style_name, available_styles)` SHALL return `"Normal"` unconditionally — regardless of whether `"Normal"` itself is in `available_styles`.

**Validates: Requirements 9.3**

---

### Property 11: DOCX multi-run distribution covers all translated text

*For any* paragraph with N runs (N > 1) whose source texts have a total length > 0, after `translate_docx_inplace()` distributes the translated text, the concatenation of all updated `run.text` values SHALL equal the full `translated_text` string, and every run's `bold`, `italic`, `font.size`, and `font.color.rgb` attributes SHALL remain unchanged from their original values.

**Validates: Requirements 7.2**

---

### Property 12: PPTX read/write round-trip for notes and table cells

*For any* PPTX presentation containing notes slides or table shapes, every non-empty text block extracted by `read_pptx()` with `type="notes"` or `type="table_cell"` SHALL be uniquely addressable by the `(slide, shape_id, para_idx)` or `(slide, shape_id, row, col)` key tuple, and `translate_pptx_inplace()` SHALL write translated text back to exactly the block identified by that key.

**Validates: Requirements 11.1, 11.2, 11.3, 11.4**

---

## Error Handling

### `Chunk_Splitter`
- Empty or whitespace-only input: returns `[""]` without raising.
- `max_tokens <= 0`: undefined by requirements; implementation should treat as 1 to avoid infinite loops.
- No sentence boundaries within `hard_cap`: returns `[text]` as a single unsplit chunk (graceful degradation).

### `Font_Mapper`
- `None` or empty `font_name`: returns `"helv"` with `⚠️` warning printed to stdout.
- Unknown font (no keyword match, not embedded): returns `"helv"` with `⚠️` warning.
- Warnings are informational and do not raise exceptions, so a single bad font name never aborts PDF output.

### `Style_Mapper`
- `None` or missing style: unconditionally returns `"Normal"`, never raises `KeyError`.

### `_resolve_overflow`
- `page.insert_textbox()` raises an exception: the exception propagates to `write_pdf_preserved()`'s existing `except` handler.
- `other_bboxes` is empty: no collision check is performed; expansion proceeds if space is available.
- `font_size <= 7`: the font-reduction loop is skipped; returns `{"resolved": False, "continuation": True, ...}` immediately.

### PDF Column Detection
- `column_mode` not in `{"auto", "single", "left", "right"}`: raises `ValueError` with descriptive message listing accepted values.
- `detect_columns()` returns < 50% of input blocks: falls back to single-column order and logs `[COLUMN FALLBACK]`.

### CSV Language-Code Fix
- `source_lang` / `target_lang` not in `CODE_TO_LANG`: `_translate_single()` uses the value as-is — Mistral's prompt will contain the human-readable name directly, which is the desired behaviour.

### Token Budget
- `estimated_input_tokens > 3500`: logs `[TOKEN BUDGET]` warning but still attempts translation. Translation is never silently dropped.
- Computed `dynamic_max_tokens` = 0 (would happen if `estimated_input_tokens >= 4096`): clamped to `max(1, ...)` so Mistral always receives `max_tokens >= 1`.

### DOCX Headers/Footers
- `section.header` or `section.footer` raises an unexpected exception: caught by the existing `except Exception` guard in `translate_docx_inplace()`; the failed header/footer is skipped and progress continues.

### PPTX Notes/Tables
- `slide.has_notes_slide` is `False`: the notes-iteration block is skipped entirely.
- `shape.shape_type` is not `MSO_SHAPE_TYPE.TABLE`: the table-iteration block is skipped.
- Key lookup miss in `notes_map` / `table_map`: the cell/paragraph is silently skipped (no original text extraction means no translation is expected).

---

## Testing Strategy

### Dual Testing Approach

Every requirement is covered by both example-based unit tests and property-based tests where applicable. Unit tests verify specific concrete examples and edge conditions; property tests verify universal invariants across a wide input space.

### Property-Based Testing Library

Use **[Hypothesis](https://hypothesis.readthedocs.io/)** (already installed in many Python projects; add to `requirements-dev.txt` if not present). Each property test is configured with `@settings(max_examples=100)`.

Property test tag format: `# Feature: translation-pipeline-optimization, Property {N}: {property_text}`

### Unit Tests (example-based)

The existing `Model/tests/test_units.py` already contains detailed example-based tests for:
- `Chunk_Splitter` (classes `TestChunkSplitterBasic`, `TestChunkSplitterContentPreservation`, `TestChunkSplitterHardCap`, `TestChunkSplitterMinimumSize`)
- `Context_Buffer` (`TestContextBuffer`)
- `Glossary_Store` (`TestGlossaryStore`)
- `Font_Mapper` (`TestFontMapper`)
- `Style_Mapper` (`TestStyleMapper`)
- `_resolve_overflow` (`TestResolveOverflowNoOverflow`, `TestResolveOverflowExpandDownward`)

No modifications to the test file are required. All tests must pass after implementation.

### Property Tests

The following property tests should be added in a separate file `Model/tests/test_properties.py`:

| Property | Test function | Hypothesis strategy |
|----------|--------------|---------------------|
| P1 — Chunk round-trip | `test_chunk_splitter_round_trip` | `st.text(min_size=1)` |
| P2 — Short text not split | `test_short_text_no_split` | `st.integers(1, 80)` for max_tokens; `st.text` with ≤ max_tokens words |
| P3 — min_tokens respected | `test_min_tokens_respected` | `st.text`, random `min_tokens` |
| P4 — Left/right column filter | `test_column_filter_left_right` | `st.lists(st.floats)` for block positions |
| P5 — Font keyword classification | `test_font_mapper_keyword` | `st.sampled_from(keywords)` + `st.text()` prefix/suffix |
| P6 — Font embedded passthrough | `test_font_mapper_embedded` | `st.text(min_size=1)` for font names |
| P7 — Overflow no-op | `test_resolve_overflow_noop` | `st.floats(min_value=0.0)` for initial_remaining |
| P8 — Overflow expand | `test_resolve_overflow_expand` | `st.floats(max_value=-0.001)` for initial_remaining |
| P9 — Style_Mapper identity | `test_style_mapper_identity` | `st.sets(st.text(min_size=1))` for available_styles |
| P10 — Style_Mapper fallback | `test_style_mapper_fallback` | `st.one_of(st.none(), st.just(""), st.text())` for style_name |
| P11 — Multi-run distribution | `test_docx_run_distribution` | `st.lists(st.text(min_size=0), min_size=2)` for run texts |
| P12 — PPTX read/write round-trip | `test_pptx_notes_table_round_trip` | Mock PPTX objects with random slide/shape/para indices |

### Integration Tests

The following integration scenarios require mocking of external dependencies (Mistral API, `fitz`, `python-pptx`):

- **Req 1.10**: `batch_translate_blocks()` with a long block → verify `_translate_with_mistral` mock called once per chunk, results rejoined.
- **Req 3.1**: `batch_translate_blocks(context_buffer=None)` → verify no `Context_Buffer` construction.
- **Req 3.2**: `batch_translate_blocks(context_buffer=mock_buf, blocks=[...])` → verify `get_hint()` called len(blocks) times, `push()` called len(blocks) times.
- **Req 5.8**: `write_pdf_preserved()` → verify `Font_Mapper.resolve` is called with the correct arguments per block.
- **Req 6.6**: `write_pdf_preserved()` where `insert_textbox` returns negative → verify `_resolve_overflow` is called.
- **Req 8**: `translate_docx_inplace()` with a multi-section document → verify header/footer paragraphs are translated with correct block types.
- **Req 10**: `run_pipeline()` with a CSV file → mock `_translate_single`, verify it receives `source_lang`/`target_lang` names, not language codes.

### Smoke Tests

- Import each of `Chunk_Splitter`, `Context_Buffer`, `Glossary_Store`, `Font_Mapper`, `Style_Mapper`, `_resolve_overflow` directly — no `ImportError`.
- `LANGUAGES` and `CODE_TO_LANG` dicts present with expected keys.

### Test Execution

```bash
# Run all unit and property tests
pytest Model/tests/ -v

# Run only property tests
pytest Model/tests/test_properties.py -v

# Run existing unit tests (must all pass, no changes to file)
pytest Model/tests/test_units.py -v
```
