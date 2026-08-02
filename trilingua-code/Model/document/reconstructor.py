# -*- coding: utf-8 -*-
"""
Document reconstructor.

Responsible for taking translated text blocks and writing them back
into the original document format while preserving layout.

Contains NO translation logic and NO provider-specific code.
Reused from document_translator_v3.py.
"""

import os
import platform
import re
import csv
import shutil
import subprocess
import tempfile

from .layout import BackgroundSampler


def _apply_translation_to_paragraph(para, translated_text, glossary_store):
    """
    Apply a translated string to a paragraph's runs, preserving per-run formatting.
    
    Uses proportional text distribution: calculates each run's share of the
    original text (by character count), then distributes the translated text
    across runs proportionally. This preserves character-level formatting
    like bold words, colored text, and mixed font sizes within a paragraph.
    
    If the paragraph has only one run, sets run.text directly (fast path).
    If the paragraph has multiple runs, distributes proportionally.
    """
    if glossary_store is not None:
        translated_text = glossary_store.apply(translated_text)

    runs = para.runs
    if not runs:
        para.add_run(translated_text)
        return

    if len(runs) == 1:
        runs[0].text = translated_text
        return

    # Multi-run: distribute translated text proportionally across runs
    # Calculate each run's character share of the original text
    original_text = "".join(r.text for r in runs)
    orig_len = len(original_text)
    tgt_len = len(translated_text)

    if orig_len == 0 or tgt_len == 0:
        # Fallback: put all text in first run, clear rest
        runs[0].text = translated_text
        for run in runs[1:]:
            run.text = ""
        return

    # Distribute proportionally
    char_pos = 0
    for i, run in enumerate(runs):
        if i == len(runs) - 1:
            # Last run gets all remaining text
            run.text = translated_text[char_pos:]
        else:
            # Calculate this run's share of the original text
            run_orig_len = len(run.text)
            # Proportional share of translated text
            run_tgt_len = max(0, int(tgt_len * run_orig_len / orig_len))
            # Ensure we don't exceed remaining
            run_tgt_len = min(run_tgt_len, tgt_len - char_pos)
            run.text = translated_text[char_pos:char_pos + run_tgt_len]
            char_pos += run_tgt_len


def translate_docx_inplace(input_file, output_file, source_lang, target_lang,
                           glossary_store=None, progress_callback=None):
    """
    Translate a DOCX file by iterating its paragraphs and tables in-place.
    """
    from docx import Document
    from docx.oxml.ns import qn
    from dto.requests import LANGUAGES
    # We need a translation function — this is provided by the pipeline
    # This function will be called with a callable translator
    raise NotImplementedError(
        "translate_docx_inplace is now a template. "
        "Use document_pipeline.py's in-place translation with injected translator."
    )


def _translate_docx_inplace_with_translator(input_file, output_file, translate_fn,
                                            glossary_store=None, progress_callback=None):
    """
    Translate a DOCX file in-place using a provided translation function.
    
    Args:
        input_file: Path to source DOCX
        output_file: Path to save translated DOCX
        translate_fn: Callable(text, block_type) -> translated_text
        glossary_store: Optional GlossaryStore for post-processing
        progress_callback: Optional callable(completed, total)
    """
    from docx import Document
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph

    doc = Document(input_file)
    total_paras = sum(1 for p in doc.paragraphs if p.text.strip())
    total_cells = sum(1 for t in doc.tables for r in t.rows for c in r.cells if c.text.strip())
    total_textboxes = 0
    for txbx in doc.element.body.iter(qn("w:txbxContent")):
        for p_elem in txbx.iter(qn("w:p")):
            texts = []
            for t_elem in p_elem.iter(qn("w:t")):
                if t_elem.text:
                    texts.append(t_elem.text)
            if "".join(texts).strip():
                total_textboxes += 1
    total_header_footer = 0
    for section in doc.sections:
        for para in section.header.paragraphs:
            if para.text.strip():
                total_header_footer += 1
        for para in section.footer.paragraphs:
            if para.text.strip():
                total_header_footer += 1
    total = total_paras + total_cells + total_textboxes + total_header_footer
    completed = 0

    # ── Translate headers and footers ─────────────────────────────────────
    for section in doc.sections:
        for para in section.header.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            translated_text = translate_fn(text, block_type="header")
            _apply_translation_to_paragraph(para, translated_text, glossary_store)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

        for para in section.footer.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            translated_text = translate_fn(text, block_type="footer")
            _apply_translation_to_paragraph(para, translated_text, glossary_store)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    # ── Translate paragraphs ─────────────────────────────────────────────
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        translated_text = translate_fn(text, block_type="paragraph")
        _apply_translation_to_paragraph(para, translated_text, glossary_store)
        completed += 1
        if progress_callback:
            progress_callback(completed, total)

    # ── Translate text boxes ─────────────────────────────────────────────
    for txbx in doc.element.body.iter(qn("w:txbxContent")):
        for p_elem in txbx.iter(qn("w:p")):
            texts = []
            for t_elem in p_elem.iter(qn("w:t")):
                if t_elem.text:
                    texts.append(t_elem.text)
            combined = "".join(texts).strip()
            if not combined:
                continue
            translated_text = translate_fn(combined, block_type="text_box")
            para_obj = Paragraph(p_elem, doc)
            _apply_translation_to_paragraph(para_obj, translated_text, glossary_store)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    # ── Translate table cells ────────────────────────────────────────────
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if not text:
                    continue
                translated_text = translate_fn(text, block_type="table_cell")
                if glossary_store is not None:
                    translated_text = glossary_store.apply(translated_text)
                first_para = True
                for p in cell.paragraphs:
                    if first_para:
                        _apply_translation_to_paragraph(p, translated_text, None)
                        first_para = False
                    elif p.text.strip() or p.runs:
                        for run in p.runs:
                            run.text = ""
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

    # ── Translate footnotes and endnotes ─────────────────────────────────
    try:
        for note_type_tag in ("w:footnote", "w:endnote"):
            for note_elem in doc.element.body.iter(qn(note_type_tag)):
                for p_elem in note_elem.iter(qn("w:p")):
                    texts = []
                    for t_elem in p_elem.iter(qn("w:t")):
                        if t_elem.text:
                            texts.append(t_elem.text)
                    combined = "".join(texts).strip()
                    if not combined:
                        continue
                    para_obj = Paragraph(p_elem, doc)
                    translated_text = translate_fn(combined, block_type="paragraph")
                    _apply_translation_to_paragraph(para_obj, translated_text, glossary_store)
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, total)
    except Exception:
        pass

    # ── Translate hyperlink text ────────────────────────────────────────
    try:
        for hyperlink in doc.element.body.iter(qn("w:hyperlink")):
            texts = []
            for t_elem in hyperlink.iter(qn("w:t")):
                if t_elem.text:
                    texts.append(t_elem.text)
            combined = "".join(texts).strip()
            if not combined:
                continue
            first = True
            for t_elem in hyperlink.iter(qn("w:t")):
                if t_elem.text and t_elem.text.strip():
                    if first:
                        translated_text = translate_fn(combined, block_type="paragraph")
                        if glossary_store is not None:
                            translated_text = glossary_store.apply(translated_text)
                        t_elem.text = translated_text
                        first = False
                    else:
                        t_elem.text = ""
            if not first:
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)
    except Exception:
        pass

    doc.save(output_file)


def translate_pptx_inplace(input_file, output_file, translate_fn,
                           glossary_store=None, progress_callback=None):
    """
    Translate a PPTX file by iterating slides/shapes/paragraphs in-place.
    Uses a provided translation function instead of hardcoded Mistral.
    """
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(input_file)

    def _count_text_paragraphs(shapes):
        count = 0
        for shape in shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                count += _count_text_paragraphs(shape.shapes)
            elif shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        for para in cell.text_frame.paragraphs:
                            if para.text.strip():
                                count += 1
            elif shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    if para.text.strip():
                        count += 1
        return count

    def _translate_shapes(shapes):
        nonlocal completed
        for shape in shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                _translate_shapes(shape.shapes)
                continue

            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        for para in cell.text_frame.paragraphs:
                            text = para.text.strip()
                            if not text:
                                continue
                            translated_text = translate_fn(text, block_type="table_cell")
                            if glossary_store is not None:
                                translated_text = glossary_store.apply(translated_text)
                            _apply_translation_to_paragraph(para, translated_text, None)
                            completed += 1
                            if progress_callback:
                                progress_callback(completed, total_items)
                continue

            if not shape.has_text_frame:
                continue

            block_type = "paragraph"
            if hasattr(shape, "placeholder_format") and shape.placeholder_format is not None:
                ph_idx = shape.placeholder_format.idx
                if ph_idx == 0:
                    block_type = "header"
                elif ph_idx == 1:
                    block_type = "paragraph"
                elif ph_idx in (2, 3):
                    block_type = "footer"

            for para in shape.text_frame.paragraphs:
                text = para.text.strip()
                if not text:
                    continue
                translated_text = translate_fn(text, block_type=block_type)
                if glossary_store is not None:
                    translated_text = glossary_store.apply(translated_text)
                _apply_translation_to_paragraph(para, translated_text, None)
                completed += 1
                if progress_callback:
                    progress_callback(completed, total_items)

    total_items = _count_text_paragraphs(
        shape for slide in prs.slides for shape in slide.shapes
    )
    completed = 0

    for slide in prs.slides:
        _translate_shapes(slide.shapes)

    prs.save(output_file)
    print(f"  [OK] PPTX saved with layout preservation ({completed} items translated)")


def translate_xlsx_inplace(input_file, output_file, translate_fn,
                           glossary_store=None, progress_callback=None):
    """
    Translate an XLSX file by iterating all cells in-place.
    Uses a provided translation function.
    """
    from openpyxl import load_workbook

    wb = load_workbook(input_file, data_only=True)
    total_cells = sum(
        1 for sheet_name in wb.sheetnames
        for row in wb[sheet_name].iter_rows()
        for cell in row
        if cell.value and isinstance(cell.value, str) and cell.value.strip()
        and not str(cell.value).strip().startswith("=")
    )
    completed = 0

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        for row in ws.iter_rows():
            for cell in row:
                if not cell.value or not isinstance(cell.value, str):
                    continue
                text = cell.value.strip()
                if not text or text.startswith("="):
                    continue
                translated_text = translate_fn(text, block_type="table_cell")
                if glossary_store is not None:
                    translated_text = glossary_store.apply(translated_text)
                cell.value = translated_text
                completed += 1
                if progress_callback:
                    progress_callback(completed, total_cells)

    wb.save(output_file)
    wb.close()
    print(f"  [OK] XLSX saved with perfect layout preservation ({completed} cells translated)")


def write_docx(blocks, output_file, original_file=None):
    """Legacy DOCX writer for RTF/ODT fallback (creates new document from blocks)."""
    from docx import Document
    from docx.shared import RGBColor
    from .layout import StyleMapper

    new_doc = Document()
    para_blocks = [b for b in blocks if b.get("type") == "paragraph"]
    table_blocks = [b for b in blocks if b.get("type") == "table_cell"]

    available_styles = {s.name for s in new_doc.styles}

    for block in para_blocks:
        style_info = block.get("style") or {}
        resolved_style = StyleMapper().resolve(style_info.get("style_name"), available_styles)
        para = new_doc.add_paragraph(block["text"], style=resolved_style)

        if style_info.get("alignment") is not None:
            para.alignment = style_info["alignment"]
        if style_info.get("space_before") is not None:
            para.paragraph_format.space_before = style_info["space_before"]
        if style_info.get("space_after") is not None:
            para.paragraph_format.space_after = style_info["space_after"]

        if para.runs:
            run = para.runs[0]
            if style_info.get("bold"):
                run.bold = True
            if style_info.get("font_size") is not None:
                run.font.size = style_info["font_size"]
            fc = style_info.get("font_color")
            if fc is not None:
                try:
                    if isinstance(fc, RGBColor):
                        run.font.color.rgb = fc
                    elif isinstance(fc, str):
                        run.font.color.rgb = RGBColor(*bytes.fromhex(fc.lstrip("#")))
                except Exception:
                    pass

    if table_blocks:
        tables_dict = {}
        for cell_block in table_blocks:
            tidx = cell_block["table_index"]
            if tidx not in tables_dict:
                tables_dict[tidx] = []
            tables_dict[tidx].append(cell_block)

        for tidx in sorted(tables_dict.keys()):
            cells = tables_dict[tidx]
            max_row = max(c["row"] for c in cells)
            max_col = max(c["col"] for c in cells)
            table = new_doc.add_table(rows=max_row + 1, cols=max_col + 1)

            merged = set()
            for cell_block in cells:
                r, c = cell_block["row"], cell_block["col"]
                if (r, c) in merged:
                    continue
                col_span = cell_block.get("col_span", 1)
                row_span = cell_block.get("row_span", 1)

                if col_span > 1 or row_span > 1:
                    end_r = min(r + row_span - 1, max_row)
                    end_c = min(c + col_span - 1, max_col)
                    try:
                        table.cell(r, c).merge(table.cell(end_r, end_c))
                    except Exception:
                        pass
                    for mr in range(r, end_r + 1):
                        for mc in range(c, end_c + 1):
                            merged.add((mr, mc))

                tbl_cell = table.cell(r, c)
                cell_text = cell_block.get("text", "").strip()
                if cell_text:
                    tbl_cell.paragraphs[0].clear()
                    run = tbl_cell.paragraphs[0].add_run(cell_text)
                    cell_style = cell_block.get("style") or {}
                    if cell_style.get("bold") is not None:
                        run.bold = cell_style["bold"]
                    if cell_style.get("font_size") is not None:
                        run.font.size = cell_style["font_size"]

    new_doc.save(output_file)
    print(f"  [OK] DOCX saved (new document from blocks)")


def _resolve_overflow(page, block_text, x0, y0, x1, y1, font_size, resolved_font,
                      other_bboxes, page_height, original_doc, page_num, bg_color,
                      initial_remaining, text_color=None, alignment=0):
    """
    Resolve PDF text overflow by trying expanded rect, reduced font, or continuation box.
    """
    import fitz

    MIN_FONT = 6.0
    COLLISION_GAP = 2.0

    if text_color is None:
        text_color = (0, 0, 0)

    if initial_remaining >= 0:
        return {
            "resolved": True, "continuation": False, "expanded": False,
            "final_font": font_size, "cont_rect": None, "clipped": False,
        }

    result = {
        "resolved": False, "continuation": False, "expanded": False,
        "final_font": font_size, "cont_rect": None, "clipped": False,
    }

    # Strategy 1: expand rect downward
    overflow = abs(initial_remaining)
    candidate_bottom = y1 + overflow + font_size

    collision = False
    last_below_bottom = y1
    for ob in other_bboxes:
        ob_top = ob[1]
        ob_bottom = ob[3]
        ob_left = ob[0]
        ob_right = ob[2]
        if ob_top > y0:
            last_below_bottom = max(last_below_bottom, ob_bottom)
            horizontal_overlap = (x0 < ob_right + COLLISION_GAP) and (x1 > ob_left - COLLISION_GAP)
            if ob_top < candidate_bottom + COLLISION_GAP and horizontal_overlap:
                collision = True
                break

    if not collision and candidate_bottom <= page_height:
        expanded_rect = fitz.Rect(x0, y0, x1, candidate_bottom)
        if bg_color:
            page.draw_rect(expanded_rect, color=bg_color, fill=bg_color)
        remaining = page.insert_textbox(
            expanded_rect, block_text,
            fontsize=font_size, fontname=resolved_font,
            color=text_color, align=alignment,
        )
        if remaining >= 0:
            return {
                "resolved": True, "continuation": False, "expanded": True,
                "final_font": font_size, "cont_rect": None, "clipped": False,
            }

    # Strategy 2: reduce font size
    current_font = font_size
    while current_font > MIN_FONT:
        current_font -= 1.0
        if current_font < MIN_FONT:
            current_font = MIN_FONT
            break
        rect = fitz.Rect(x0, y0, x1, y1)
        remaining = page.insert_textbox(
            rect, block_text,
            fontsize=current_font, fontname=resolved_font,
            color=text_color, align=alignment,
        )
        if remaining >= 0:
            return {
                "resolved": True, "continuation": False, "expanded": False,
                "final_font": current_font, "cont_rect": None, "clipped": False,
            }

    # Strategy 3: continuation box with collision detection
    cont_top = max(y1, last_below_bottom) + 4.0
    for _ in range(10):
        collides = False
        for ob in other_bboxes:
            ob_top, ob_bottom, ob_left, ob_right = ob[1], ob[3], ob[0], ob[2]
            if ob_bottom <= cont_top:
                continue
            horizontal_overlap = (x0 < ob_right + COLLISION_GAP) and (x1 > ob_left - COLLISION_GAP)
            if horizontal_overlap and ob_top < cont_top + COLLISION_GAP:
                cont_top = ob_bottom + 4.0
                collides = True
                break
        if not collides:
            break
    cont_height = overflow + MIN_FONT
    cont_bottom = cont_top + cont_height

    clipped = False
    if cont_bottom > page_height:
        cont_bottom = page_height
        clipped = True

    cont_rect = fitz.Rect(x0, cont_top, x1, cont_bottom)
    if bg_color:
        page.draw_rect(cont_rect, color=bg_color, fill=bg_color)
    remaining = page.insert_textbox(
        cont_rect, block_text,
        fontsize=MIN_FONT, fontname=resolved_font,
        color=text_color, align=alignment,
    )

    if clipped:
        print(f"  ⚠️  Continuation box clipped to page boundary on page {page_num}")

    return {
        "resolved": remaining >= 0, "continuation": True,
        "expanded": False, "final_font": MIN_FONT,
        "cont_rect": cont_rect if remaining >= 0 else None, "clipped": clipped,
    }


def _get_libreoffice_cmd():
    """Return the path to the LibreOffice executable for this OS.

    On Windows, soffice.exe is often not on PATH — search common locations.
    On Linux/macOS, "libreoffice" is typically on PATH after install.
    """
    if platform.system() == "Windows":
        candidates = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\LibreOffice\program\soffice.exe"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
    return "libreoffice"


def _is_libreoffice_available():
    """Return True if LibreOffice is installed and accessible."""
    cmd = _get_libreoffice_cmd()
    try:
        result = subprocess.run(
            [cmd, "--version"],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


def _wait_for_file(file_path, timeout=120, interval=2):
    """Wait for a file to appear (LibreOffice spawns a background process on Windows)."""
    import time as _time
    deadline = _time.time() + timeout
    while _time.time() < deadline:
        if os.path.exists(file_path):
            return True
        _time.sleep(interval)
    return False


def translate_pdf_via_libreoffice(input_file, output_file, translate_fn,
                                  glossary_store=None, progress_callback=None):
    """
    Translate a PDF by round-tripping through DOCX via LibreOffice.
    """
    tmp_dir = tempfile.mkdtemp()
    try:
        stem = os.path.splitext(os.path.basename(input_file))[0]
        docx_path = os.path.join(tmp_dir, f"{stem}.docx")
        pdf_path = os.path.join(tmp_dir, f"{stem}_translated.pdf")

        # Step 1: PDF → DOCX
        print("  [LibreOffice] Converting PDF to DOCX...")
        result = subprocess.run(
            [_get_libreoffice_cmd(), "--headless", "--convert-to", "docx",
             "--outdir", tmp_dir, input_file],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0 or not _wait_for_file(docx_path):
            raise RuntimeError(
                f"LibreOffice PDF→DOCX conversion failed: {result.stderr.strip()}"
            )

        # Step 2: Translate the DOCX in-place
        print("  [LibreOffice] Translating DOCX...")
        _translate_docx_inplace_with_translator(
            docx_path, docx_path, translate_fn,
            glossary_store=glossary_store,
            progress_callback=progress_callback,
        )

        # Step 3: DOCX → PDF
        print("  [LibreOffice] Converting translated DOCX back to PDF...")
        result = subprocess.run(
            [_get_libreoffice_cmd(), "--headless", "--convert-to", "pdf",
             "--outdir", tmp_dir, docx_path],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0 or not _wait_for_file(pdf_path):
            raise RuntimeError(
                f"LibreOffice DOCX→PDF conversion failed: {result.stderr.strip()}"
            )

        # Step 4: Copy to output
        shutil.copy2(pdf_path, output_file)
        print(f"  [OK] PDF saved with perfect layout preservation via LibreOffice")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Language-pair expansion coefficients for proactive font sizing ──────
# These are empirically derived ratios for common language pairs.
# Key: "source-target" → expansion factor (chars_target / chars_source)
# Values > 1.0 mean target text is typically longer than source.
_LANG_EXPANSION_COEFFS = {
    "English-Cebuano": 1.25,
    "English-Filipino": 1.35,
    "Cebuano-English": 0.85,
    "Cebuano-Filipino": 1.10,
    "Filipino-English": 0.80,
    "Filipino-Cebuano": 0.95,
}


def _get_lang_expansion(source_lang: str = "", target_lang: str = "") -> float:
    """Get the expected expansion factor for a language pair.
    
    Returns a multiplier: if > 1.0, target text is typically longer.
    Falls back to 1.0 (no expansion) for unknown pairs.
    """
    key = f"{source_lang}-{target_lang}"
    return _LANG_EXPANSION_COEFFS.get(key, 1.0)


def _truncate_to_fit(text: str, max_chars: int) -> tuple[str, str]:
    """Truncate text to fit within max_chars at the last word boundary.
    
    Returns (fits_text, overflow_text).
    If text fits entirely, overflow_text is empty.
    """
    if len(text) <= max_chars:
        return text, ""
    
    # Find the last space within max_chars
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        fits = text[:last_space]
        overflow = text[last_space + 1:]
    else:
        fits = truncated
        overflow = text[max_chars:]
    
    return fits.strip(), overflow.strip()


# Codepoints that PyMuPDF ``insert_text`` renders faithfully with a bare
# Base-14 fontname (helv/tiro/cour). Measured empirically: ASCII printable +
# Latin-1 (0xA1-0xFF), excluding nbsp (0xA0) and soft-hyphen (0xAD) which are
# rewritten to U+00B7. Any codepoint outside this set must NOT be routed to the
# bare Base-14 path, even though ``fitz.Font(...).has_glyph()`` reports
# coverage — insert_text silently mangles them to the middle-dot glyph.
_BASE14_RENDERABLE = frozenset(
    set(range(0x20, 0x7F))
    | set(range(0xA1, 0x100))
) - {0xAD}


def write_pdf_preserved(blocks, original_pdf_path, output_file,
                        layout_plan=None,
                        source_lang="", target_lang=""):
    """
    Replace original text in a PDF with translations while preserving layout.

    Strategy: per-line redact-and-reinsert.

      - Original text is removed per LINE via ``apply_redactions(images=0,
        graphics=0, text=0)`` so images and vector graphics survive untouched.
      - Translated block text is re-flowed into the original line boxes at their
        exact baseline/x0 with per-line font/size/colour and block alignment.
      - Overflow rules: expand into collision-checked whitespace first, then
        shrink the font down to a 70% floor. Text is never merged into the next
        block; excess words wrap to continuation lines inside the block's own box.
      - Hyperlink annotations are re-created at the translated line positions.
      - Garbage/passthrough blocks are skip-listed: original text and links stay.

    A per-page page-copy fallback re-runs the same core on a pristine copy of the
    page when a post-redaction invariant fails (I1 image bytes, I2 leftover glyphs,
    I3 bbox collision, I4 exception).
    """
    import fitz

    _BASE14_VARIANTS = {
        ("helv", False, False): "helv", ("helv", True, False): "hebo",
        ("helv", False, True): "heit", ("helv", True, True): "hebi",
        ("tiro", False, False): "tiro", ("tiro", True, False): "tibo",
        ("tiro", False, True): "titi", ("tiro", True, True): "tibi",
        ("cour", False, False): "cour", ("cour", True, False): "cobo",
        ("cour", False, True): "coit", ("cour", True, True): "cobi",
    }

    def _ensure_lines(block):
        """Backfill a single synthesized line for blocks without line records."""
        if block.get("lines"):
            return
        bbox = block.get("position", [50, 50, 500, 100])
        style = block.get("style", {})
        block["lines"] = [{
            "text": block.get("text", ""),
            "bbox": list(bbox),
            "baseline": round(float(bbox[3]), 2),
            "font": style.get("font", "helv"),
            "font_original": style.get("font_original", ""),
            "size": style.get("font_size", 11),
            "color": style.get("color", 0),
            "bold": style.get("bold", False),
            "italic": style.get("italic", False),
            "runs": [{
                "text": block.get("text", ""),
                "font": style.get("font", "helv"),
                "font_original": style.get("font_original", ""),
                "size": style.get("font_size", 11),
                "color": style.get("color", 0),
                "bold": style.get("bold", False),
                "italic": style.get("italic", False),
            }],
            "links": [],
        }]

    for _b in blocks:
        _ensure_lines(_b)

    def _clean_subset(name):
        return name.split("+", 1)[1] if "+" in name else name

    def _family_of(name):
        lower = (name or "").lower()
        if lower in ("helv", "hebo", "heit", "hebi"):
            return "helv"
        if lower in ("tiro", "tibo", "titi", "tibi"):
            return "tiro"
        if lower in ("cour", "cobo", "coit", "cobi"):
            return "cour"
        if any(k in lower for k in ("courier", "consolas", "mono", "monospace")):
            return "cour"
        if any(k in lower for k in ("liberation", "nimbus")) and any(
                k in lower for k in ("serif", "roman")):
            return "tiro"
        if any(k in lower for k in ("times", "georgia", "roman", "garamond",
                                    "palatino", "bookman", "baskerville", "serif",
                                    "caslon", "bembo", "bodoni", "hoefler",
                                    "cambria", "book", "charter", "jenson")):
            return "tiro"
        return "helv"

    def _safe_fontname(name):
        cleaned = re.sub(r"[^A-Za-z0-9]", "", name or "")[:30]
        if not cleaned:
            return "helv"
        if cleaned.lower() in ("helv", "heit", "hebo", "hebi", "tiro", "titi",
                               "tibo", "tibi", "cour", "coit", "cobo", "cobi"):
            return "f" + cleaned
        return cleaned

    def _resolve_color(color_val):
        if isinstance(color_val, int) and color_val != 0:
            c = fitz.sRGB_to_rgb(color_val)
            if isinstance(c, (tuple, list)) and len(c) >= 3:
                if max(c[:3]) > 1.0:
                    return tuple(round(v / 255.0, 6) for v in c[:3])
                return tuple(c[:3])
        return (0, 0, 0)

    def _block_alignment(block, page_width):
        alignment_str = block.get("alignment", "")
        if alignment_str:
            _align_map = {"left": 0, "center": 1, "right": 2, "justify": 3}
            if alignment_str in _align_map:
                return _align_map[alignment_str]
        bbox = block.get("position", [0, 0, 0, 0])
        x0, y0, x1, y1 = bbox
        block_center = (x0 + x1) / 2.0
        block_width = x1 - x0
        right_margin = page_width - x1
        left_margin = x0
        if block_width > page_width * 0.05 and right_margin < page_width * 0.05 and left_margin > page_width * 0.10:
            return 2
        if block_width < page_width * 0.85 and abs(block_center - page_width / 2.0) < page_width * 0.05:
            return 1
        if block_width > page_width * 0.90:
            return 3
        return 0

    # ---- open docs ----
    doc = fitz.open(original_pdf_path)
    src_doc = fitz.open(original_pdf_path)

    # ---- collect embedded font programs (raw + subset-stripped keys) ----
    _embedded_font_programs: dict[str, bytes] = {}
    for _pnum in range(len(src_doc)):
        for _f in src_doc.get_page_fonts(_pnum):
            _xref, _fname = _f[0], _f[3]
            if _fname in _embedded_font_programs:
                continue
            try:
                _info = src_doc.extract_font(_xref)
                _buf = _info[3]
                if _buf:
                    _embedded_font_programs[_fname] = _buf
                    _clean = _clean_subset(_fname)
                    if _clean and _clean != _fname and _clean not in _embedded_font_programs:
                        _embedded_font_programs[_clean] = _buf
            except Exception:
                pass

    _font_cache: dict[tuple[int, int], set[str]] = {}
    _fallback_used: set[str] = set()

    _SYSTEM_FONT_FILES = {
        ("helv", False, False): r"C:\Windows\Fonts\arial.ttf",
        ("helv", True, False): r"C:\Windows\Fonts\arialbd.ttf",
        ("helv", False, True): r"C:\Windows\Fonts\ariali.ttf",
        ("tiro", False, False): r"C:\Windows\Fonts\times.ttf",
        ("tiro", True, False): r"C:\Windows\Fonts\timesbd.ttf",
        ("tiro", False, True): r"C:\Windows\Fonts\timesi.ttf",
        ("cour", False, False): r"C:\Windows\Fonts\cour.ttf",
        ("cour", True, False): r"C:\Windows\Fonts\courbd.ttf",
        ("cour", False, True): r"C:\Windows\Fonts\couri.ttf",
    }
    _SYSTEM_FALLBACK_LIST = [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf",
                             r"C:\Windows\Fonts\times.ttf"]

    _BASE14_COMPAT_ORIGINALS = ("arial", "helvetica", "helvetica neue", "times",
                                "times new roman", "liberationserif", "liberationsans",
                                "liberationmono", "courier", "courier new", "nimbusroman")

    def _original_system_font(name, bold, italic):
        lower = (name or "").lower()
        if any(c in lower for c in _BASE14_COMPAT_ORIGINALS):
            return None
        if "tahoma" in lower:
            return r"C:\Windows\Fonts\tahomabd.ttf" if bold else r"C:\Windows\Fonts\tahoma.ttf"
        if "verdana" in lower:
            if bold and italic:
                return r"C:\Windows\Fonts\verdanaz.ttf"
            if bold:
                return r"C:\Windows\Fonts\verdanab.ttf"
            if italic:
                return r"C:\Windows\Fonts\verdanai.ttf"
            return r"C:\Windows\Fonts\verdana.ttf"
        if "calibri" in lower:
            if bold:
                return r"C:\Windows\Fonts\calibrib.ttf"
            if italic:
                return r"C:\Windows\Fonts\calibrii.ttf"
            return r"C:\Windows\Fonts\calibri.ttf"
        if "segoe" in lower:
            if bold:
                return r"C:\Windows\Fonts\segoeuib.ttf"
            if italic:
                return r"C:\Windows\Fonts\segoeuii.ttf"
            return r"C:\Windows\Fonts\segoeui.ttf"
        if "georgia" in lower:
            if bold:
                return r"C:\Windows\Fonts\georgiab.ttf"
            if italic:
                return r"C:\Windows\Fonts\georgiai.ttf"
            return r"C:\Windows\Fonts\georgia.ttf"
        if "cambria" in lower:
            if bold:
                return r"C:\Windows\Fonts\cambriab.ttf"
            if italic:
                return r"C:\Windows\Fonts\cambriai.ttf"
            return None
        if "garamond" in lower:
            if os.path.exists(r"C:\Windows\Fonts\garamond.ttf"):
                return r"C:\Windows\Fonts\garamond.ttf"
            return None
        return None

    def _insert_font(page_obj, name, buffer):
        key = (id(page_obj.parent), page_obj.xref)
        inserted = _font_cache.setdefault(key, set())
        if name in inserted:
            return
        try:
            page_obj.insert_font(fontname=name, fontbuffer=buffer)
            inserted.add(name)
        except Exception as _e:
            print(f"  [InsertWarn] page {page_obj.number}: insert_font failed "
                  f"fontname={name}: {type(_e).__name__}: {_e}")

    def _font_has_all(font_obj, cps):
        try:
            return all(font_obj.has_glyph(cp) for cp in cps)
        except Exception:
            return False

    def _base14_has_all(variant, cps):
        # NOTE: has_glyph() lies for the bare Base-14 insertion path — it reports
        # coverage for curly quotes/dashes/ellipsis that insert_text then mangles
        # to U+00B7. Use the empirically-safe renderable set instead.
        try:
            return all(cp in _BASE14_RENDERABLE for cp in cps)
        except Exception:
            return False

    def _resolve_line_font(style, page_obj, text):
        """Return (fontname, font_obj) with guaranteed glyph coverage for *text*.

        Preference: Base-14 variant (clean extraction, full Latin-1) → system
        TrueType font (covers exotic punctuation; the nbsp extraction artifact
        is visual-only). CID/Type0 subset fonts are never re-embedded because
        PyMuPDF ``insert_text`` corrupts spaces/letters with them on this version.
        """
        family_name = style.get("font_original") or style.get("font", "helv")
        family = _family_of(family_name)
        bold = bool(style.get("bold", False))
        italic = bool(style.get("italic", False))

        req_cps = {ord(ch) for ch in text if ord(ch) > 127}

        orig_path = _original_system_font(family_name, bold, italic)
        if orig_path and os.path.exists(orig_path):
            try:
                fnt = fitz.Font(fontfile=orig_path)
            except Exception:
                fnt = None
            if fnt is not None and _font_has_all(fnt, req_cps):
                _name = _safe_fontname("sys" + os.path.splitext(os.path.basename(orig_path))[0])
                _insert_font(page_obj, _name, fnt.buffer)
                _fallback_used.add(orig_path)
                return _name, fnt

        variant = _BASE14_VARIANTS.get((family, bold, italic), "helv")

        req_cps = {ord(ch) for ch in text if ord(ch) > 127}
        if not req_cps or _base14_has_all(variant, req_cps):
            try:
                return variant, fitz.Font(variant)
            except Exception:
                return "helv", fitz.Font("helv")

        preferred = _SYSTEM_FONT_FILES.get((family, bold, italic))
        candidates = [preferred] if preferred else []
        for _p in _SYSTEM_FALLBACK_LIST:
            if _p not in candidates:
                candidates.append(_p)
        for _path in candidates:
            if not os.path.exists(_path):
                continue
            try:
                fnt = fitz.Font(fontfile=_path)
            except Exception:
                continue
            if not _font_has_all(fnt, req_cps):
                continue
            _name = _safe_fontname("sys" + os.path.splitext(os.path.basename(_path))[0])
            _insert_font(page_obj, _name, fnt.buffer)
            _fallback_used.add(_path)
            return _name, fnt
        try:
            return variant, fitz.Font(variant)
        except Exception:
            return "helv", fitz.Font("helv")

    def _text_width(text, font_obj, fontsize):
        try:
            return font_obj.text_length(text, fontsize=fontsize)
        except Exception:
            return fontsize * 0.5 * len(text)

    def _image_snapshot(page):
        snap = []
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                pix = page.parent.extract_image(xref)
                snap.append((xref, pix.get("ext"), pix.get("image")))
            except Exception:
                snap.append((xref, None, None))
        snap.sort(key=lambda t: t[0])
        return snap

    def _spans_in_rects(page, rects):
        count = 0
        d = page.get_text("dict")
        for b in d.get("blocks", []):
            if b.get("type") != 0:
                continue
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    txt = sp.get("text", "")
                    if not txt.strip():
                        continue
                    sb = sp.get("bbox")
                    if not sb:
                        continue
                    sr = fitz.Rect(sb)
                    for rr in rects:
                        inter = sr & rr
                        if not inter.is_empty and inter.get_area() > 1.0:
                            count += 1
                            break
        return count

    def _count_spans(page):
        n = 0
        d = page.get_text("dict")
        for b in d.get("blocks", []):
            if b.get("type") != 0:
                continue
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    if sp.get("text", "").strip():
                        n += 1
        return n

    def _shrink_floor(base_size):
        # env override for measuring the contribution of the shrink-to-fit floor
        try:
            _f = float(os.environ.get("TRI_SHRINK_FLOOR", "0.70"))
        except ValueError:
            _f = 0.70
        return max(_f * base_size, 4.0)

    def _fit_chunk(words, start, font_obj, size, width):
        """Greedily take words that fit within *width* at *size*.

        Returns (chunk_text, next_index, fits). ``fits`` is False when even the
        first word does not fit at this size.
        """
        chunk = []
        idx = start
        for i in range(start, len(words)):
            trial = " ".join(chunk + [words[i]])
            if chunk and _text_width(trial, font_obj, size) > width:
                break
            if not chunk and _text_width(trial, font_obj, size) > width:
                return "", i, False
            chunk.append(words[i])
            idx = i + 1
        return " ".join(chunk), idx, True

    def _fit_chunk_runs(words, start, runs, size, width, page):
        """Greedily take words that fit within *width*, measuring each word at
        the width of the source run that verbatim-contains it (exact word match)
        or at the first run's font otherwise.

        A mixed-run line can be narrower than its bold-or-regular single-font
        estimate (bold headline + regular body), so the single-font ``_fit_chunk``
        would truncate words that the run-level path could actually place.

        Returns (chunk_text, next_index, fits).
        """
        import re as _re
        run_fonts = []
        for r in runs:
            rstyle = {
                "font": r.get("font", "helv"),
                "font_original": r.get("font_original", ""),
                "bold": r.get("bold", False),
                "italic": r.get("italic", False),
            }
            fn, fo = _resolve_line_font(rstyle, page, "")
            run_fonts.append((fo, max(1.0, len(r.get("text", "")))))
        run_word_lists = [list(_re.finditer(r"\S+", r.get("text", ""))) for r in runs]

        def _word_font(w):
            for i, wl in enumerate(run_word_lists):
                if any(m.group() == w for m in wl):
                    return run_fonts[i][0]
            return run_fonts[0][0]

        chunk = []
        idx = start
        total = 0.0
        for i in range(start, len(words)):
            w = words[i]
            ww = _text_width(w, _word_font(w), size)
            trial = total + (ww if not chunk else _text_width(" ", run_fonts[0][0], size) + ww)
            if chunk and trial > width:
                break
            if not chunk and ww > width:
                return "", i, False
            chunk.append(w)
            total = trial
            idx = i + 1
        return " ".join(chunk), idx, True

    def _expand_into_whitespace(x0, x1, baseline, size, occupied, page_width, block_x0, block_x1):
        y0b = baseline - size * 0.8
        y1b = baseline + size * 0.4
        right_block = min(block_x1, page_width)
        left_block = max(block_x0, 0.0)
        for r, _tag in occupied:
            if r.y1 < y0b or r.y0 > y1b:
                continue
            if r.x0 >= x1 and r.x0 < right_block:
                right_block = r.x0
            if r.x1 <= x0 and r.x1 > left_block:
                left_block = r.x1
        return left_block, right_block

    def _insert_line(page, text, x0, x1, y, fontname, font_obj, size, color, alignment):
        if not text:
            return None
        try:
            tw = _text_width(text, font_obj, size)
            if alignment == 1:
                px = x0 + (x1 - x0 - tw) / 2.0
            elif alignment == 2:
                px = x1 - tw
            else:
                px = x0
            page.insert_text((px, y), text, fontsize=size, fontname=fontname,
                             color=color)
            return fitz.Rect(px, y - size * 1.1, px + tw, y + size * 0.2)
        except Exception as e:
            print(f"  [InsertWarn] page {page.number}: insert_text failed "
                  f"fontname={fontname} text={text[:40]!r}: {type(e).__name__}: {e}")
            return None

    def _insert_line_runs(page, text, x0, x1, y, runs, alignment):
        """Place *text* across the source line's per-span runs, each run in its
        own resolved font/size/color.

        Whole whitespace-delimited tokens are assigned to a source run so a run
        boundary never falls inside a translated word (a mid-word style split is
        only reproduced when the source itself had one). A token whose text is
        unchanged by translation (numbers, proper nouns, symbols, loanwords) is
        matched verbatim to the single source run that contains that exact word,
        preserving its style bit-for-bit. All other tokens use the anchored
        proportional span overlap (anchored to the source line's own word
        sequence so leading overflow words spliced in by block-text flow do not
        skew positions). Inter-word spaces are attached to the preceding segment
        so genuine word boundaries remain distinguishable from splits.

        Returns the placed rect, or None if the run-based layout doesn't fit the
        line box (caller then falls back to the single-font path) or the runs
        collapse to a single style (no mixed formatting to preserve).
        """
        import re as _re
        if not text:
            return None
        if not runs or len(runs) < 2:
            return None
        tokens = list(_re.finditer(r"\S+", text))
        if not tokens:
            return None
        total_src = sum(max(1, len(r.get("text", ""))) for r in runs)
        # Anchor the proportional mapping to the source line's own word
        # sequence. The chunk may include leading overflow words (e.g. a sense
        # label spliced in by block-text flow) that are not part of this source
        # line; those must map to the first run without shifting every later
        # token's position. We find how many leading chunk tokens precede the
        # source line's first word and subtract that offset from each token's
        # mapped span. Fall back to unanchored proportional mapping when no
        # word alignment is found (genuine translations rarely match verbatim).
        src_words = list(_re.finditer(r"\S+", "".join(r.get("text", "") for r in runs)))
        lead = 0
        if src_words:
            first = src_words[0].group()
            for i, t in enumerate(tokens):
                if t.group() == first:
                    lead = i
                    break
        lead_chars = tokens[lead].start() if lead else 0
        tlen = max(1, len(text) - lead_chars)
        if tlen <= 0:
            tlen = max(1, len(text))
        # Per-run word lists for exact verbatim token matching: a word that is
        # unchanged by translation (numbers, proper nouns, symbols, loanwords)
        # is assigned to the single source run that contains that exact word, so
        # its style is preserved bit-for-bit. Ambiguous / unmatched tokens fall
        # back to the anchored proportional mapping below.
        run_word_lists = [list(_re.finditer(r"\S+", r.get("text", ""))) for r in runs]
        run_words_by_token = {}
        for t in tokens:
            matches = [i for i, wl in enumerate(run_word_lists)
                       if any(w.group() == t.group() for w in wl)]
            run_words_by_token[t.start()] = matches[0] if len(matches) == 1 else None

        def _run_for_token(tok):
            """Assign *tok* to the source run: exact word match first, else the
            run with majority overlap of its anchored proportional span."""
            exact = run_words_by_token.get(tok.start())
            if exact is not None:
                return exact
            s_start = max(0.0, tok.start() - lead_chars) * total_src / tlen
            s_end = max(0.0, tok.end() - lead_chars) * total_src / tlen
            best = 0
            best_ov = -1.0
            acc = 0
            for i, r in enumerate(runs):
                rlen = max(1, len(r.get("text", "")))
                b0, b1 = acc, acc + rlen
                ov = max(0.0, min(s_end, b1) - max(s_start, b0))
                if ov > best_ov:
                    best_ov = ov
                    best = i
                acc += rlen
            return best

        assignments = [_run_for_token(t) for t in tokens]
        # group consecutive tokens by run
        groups = []
        cur = assignments[0]
        cur_toks = [tokens[0]]
        for i in range(1, len(tokens)):
            if assignments[i] == cur:
                cur_toks.append(tokens[i])
            else:
                groups.append((cur, cur_toks))
                cur = assignments[i]
                cur_toks = [tokens[i]]
        groups.append((cur, cur_toks))

        if len(groups) < 2:
            return None

        # Build segment strings, attaching the inter-word space (if any) to the
        # preceding segment so word boundaries carry their space.
        segments = []
        for gi, (ridx, toks) in enumerate(groups):
            seg = text[toks[0].start():toks[-1].end()]
            if gi < len(groups) - 1:
                nxt_start = groups[gi + 1][1][0].start()
                if nxt_start > toks[-1].end():
                    seg += text[toks[-1].end():nxt_start]
            if seg:
                segments.append((seg, runs[ridx]))
        if len(segments) < 2:
            return None
        placed = []
        for seg, r in segments:
            rstyle = {
                "font": r.get("font", "helv"),
                "font_original": r.get("font_original", ""),
                "bold": r.get("bold", False),
                "italic": r.get("italic", False),
            }
            fn, fo = _resolve_line_font(rstyle, page, seg)
            sz = max(4.0, min(float(r.get("size", 11) or 11), 72.0))
            col = _resolve_color(r.get("color", 0))
            tw = _text_width(seg, fo, sz)
            placed.append((seg, fn, fo, sz, col, tw))
        total_w = sum(tw for _s, _f, _o, _z, _c, tw in placed)
        available = x1 - x0
        if total_w > available * 1.02:
            return None
        if alignment == 1:
            px = x0 + (available - total_w) / 2.0
        elif alignment == 2:
            px = x1 - total_w
        else:
            px = x0
        max_size = 0.0
        for seg, fn, fo, sz, col, tw in placed:
            try:
                page.insert_text((px, y), seg, fontsize=sz, fontname=fn, color=col)
            except Exception as e:
                print(f"  [InsertWarn] page {page.number}: run insert_text failed "
                      f"fontname={fn} text={seg[:40]!r}: {type(e).__name__}: {e}")
            px += tw
            max_size = max(max_size, sz)
        return fitz.Rect(x0, y - max_size * 1.1, x0 + total_w, y + max_size * 0.2)

    def _recreate_links(page, line, placed_rect, recreated=None):
        if placed_rect is None:
            return
        seen = set()
        for l in line.get("links", []):
            try:
                kind = l.get("kind", 2)
                uri = l.get("uri", "") or ""
                key = (kind, uri)
                if key in seen:
                    continue
                if kind == 2 and uri:
                    page.insert_link({"kind": fitz.LINK_URI, "from": placed_rect, "uri": uri})
                    seen.add(key)
                    if recreated is not None:
                        recreated[key] += 1
                elif kind == 1:
                    page.insert_link({"kind": fitz.LINK_GOTO, "from": placed_rect,
                                      "page": int(l.get("page", -1)),
                                      "to": fitz.Point(0, 0)})
                    seen.add(key)
                    if recreated is not None:
                        recreated[key] += 1
                elif kind == 3 and uri:
                    page.insert_link({"kind": fitz.LINK_NAMED, "from": placed_rect,
                                      "name": uri})
                    seen.add(key)
                    if recreated is not None:
                        recreated[key] += 1
            except Exception:
                pass

    def _line_alignment(ln, lx0, lx1):
        sx = float(ln.get("x0", lx0))
        tx1 = float(ln.get("text_x1", lx1))
        if (sx - lx0) < 2.0:
            return 0
        if (lx1 - tx1) < 2.0:
            return 2
        return 1

    def _insert_block(page, block, page_width, page_height, occupied, block_index, layout_plan, recreated=None):
        style = block.get("style", {})
        alignment = _block_alignment(block, page_width)
        if layout_plan is not None:
            for _adj in layout_plan.adjustments:
                if _adj.block_index == block_index and _adj.alignment_override is not None:
                    _am = {"left": 0, "center": 1, "right": 2, "justify": 3}
                    alignment = _am.get(_adj.alignment_override, alignment)
                    break
        lines = block.get("lines", []) or []
        if not lines:
            return
        translated = (block.get("text") or "").strip()
        words = translated.split()
        if not words:
            return
        if os.environ.get("TRI_DEBUG"):
            print(f"    [_insert_block] page {block.get('page')} block {block_index} "
                  f"words={len(words)} lines={len(lines)} pos={[round(v,1) for v in block.get('position',[0,0,0,0])]}")
        bbox = block.get("position", [0, 0, 0, 0])
        block_x0 = max(0.0, float(bbox[0]))
        block_x1 = min(page_width, float(bbox[2]))
        block_y1 = min(page_height, float(bbox[3]))

        bfontname, bfont_obj = _resolve_line_font(style, page, translated)
        bsize = max(4.0, min(float(style.get("font_size", 11) or 11), 72.0))
        bcolor = _resolve_color(style.get("color", 0))

        wi = 0
        last_baseline = None
        for ln in lines:
            if wi >= len(words):
                break
            lstyle = dict(style)
            if ln.get("font"):
                lstyle["font"] = ln["font"]
            if ln.get("font_original"):
                lstyle["font_original"] = ln["font_original"]
            if ln.get("bold") is not None:
                lstyle["bold"] = ln["bold"]
            if ln.get("italic") is not None:
                lstyle["italic"] = ln["italic"]
            if ln.get("size"):
                lstyle["font_size"] = ln["size"]
            if ln.get("color") is not None:
                lstyle["color"] = ln["color"]
            fontname, font_obj = _resolve_line_font(lstyle, page, " ".join(words[wi:]))
            base_size = max(4.0, min(float(lstyle.get("font_size", 11) or 11), 72.0))
            color = _resolve_color(lstyle.get("color", 0))
            lbbox = ln.get("bbox", [0, 0, 0, 0])
            lx0, ly0, lx1, ly1 = (float(v) for v in lbbox)
            baseline = float(ln.get("baseline", ly1))
            if lx1 <= lx0:
                continue
            available = lx1 - lx0
            lalign = _line_alignment(ln, lx0, lx1)

            rect_placed = None
            line_runs = ln.get("runs")
            if line_runs and len(line_runs) > 1:
                chunk, nxt, fits = _fit_chunk_runs(words, wi, line_runs, base_size,
                                                   available, page)
            else:
                chunk, nxt, fits = _fit_chunk(words, wi, font_obj, base_size, available)
            if fits:
                if line_runs and len(line_runs) > 1:
                    rect_placed = _insert_line_runs(page, chunk, lx0, lx1, baseline,
                                                    line_runs, lalign)
                    if rect_placed is None:
                        rect_placed = _insert_line(page, chunk, lx0, lx1, baseline,
                                                   fontname, font_obj, base_size, color, lalign)
                else:
                    rect_placed = _insert_line(page, chunk, lx0, lx1, baseline,
                                               fontname, font_obj, base_size, color, lalign)
                wi = nxt
            else:
                ex0, ex1 = _expand_into_whitespace(lx0, lx1, baseline, base_size,
                                                   occupied, page_width, block_x0, block_x1)
                if ex1 - ex0 > available:
                    chunk2, nxt2, fits2 = _fit_chunk(words, wi, font_obj, base_size, ex1 - ex0)
                    if fits2:
                        rect_placed = _insert_line(page, chunk2, ex0, ex1, baseline,
                                                   fontname, font_obj, base_size, color, lalign)
                        wi = nxt2
                if rect_placed is None:
                    shrink_size = _shrink_floor(base_size)
                    chunk3, nxt3, fits3 = _fit_chunk(words, wi, font_obj, shrink_size, available)
                    if fits3:
                        rect_placed = _insert_line(page, chunk3, lx0, lx1, baseline,
                                                   fontname, font_obj, shrink_size, color, lalign)
                        wi = nxt3
                    else:
                        rect_placed = _insert_line(page, words[wi], lx0, lx1, baseline,
                                                   fontname, font_obj, shrink_size, color, lalign)
                        wi += 1
            if rect_placed is not None:
                last_baseline = baseline
                _recreate_links(page, ln, rect_placed, recreated)

        if wi < len(words) and last_baseline is not None:
            line_h = bsize * 1.3
            y = last_baseline + line_h
            stop_reason = "unknown"
            while wi < len(words):
                cand = fitz.Rect(block_x0, y - bsize * 1.1, block_x1, y + line_h)
                if cand.y1 > page_height:
                    stop_reason = "page-bottom"
                    break
                blocked = False
                for r, tag in occupied:
                    if tag == block_index:
                        continue
                    inter = cand & r
                    if not inter.is_empty and inter.get_area() > 1.0:
                        blocked = True
                        stop_reason = f"occupied@{round(r.y0,1)}-{round(r.y1,1)}"
                        break
                if blocked:
                    break
                size = bsize
                chunk, nxt, fits = _fit_chunk(words, wi, bfont_obj, size, block_x1 - block_x0)
                if not fits:
                    size = _shrink_floor(bsize)
                    chunk, nxt, fits = _fit_chunk(words, wi, bfont_obj, size, block_x1 - block_x0)
                    if not fits:
                        chunk, nxt = words[wi], wi + 1
                rect_placed = _insert_line(page, chunk, block_x0, block_x1, y,
                                           bfontname, bfont_obj, size, bcolor, alignment)
                if rect_placed is not None:
                    wi = nxt
                else:
                    wi += 1
                y += line_h
            if wi < len(words):
                print(f"  [Layout] Overflow: {len(words) - wi} words exceed block box "
                      f"on page {block.get('page')} (block {block_index}) — truncated "
                      f"(no cross-block merge) stop={stop_reason} blockbox="
                      f"[{round(block_y1,1)}<{round(page_height,1)}] "
                      f"words={words[wi:wi+8]}")

    def _norm_line(t):
        return " ".join(t.split())

    def _span_overlaps(page):
        """Return list of (normA, normB) overlapping line pairs."""
        d = page.get_text("dict")
        line_texts = []
        for b in d.get("blocks", []):
            if b.get("type") != 0:
                continue
            for ln in b.get("lines", []):
                rects = []
                for sp in ln.get("spans", []):
                    if not sp.get("text", "").strip():
                        continue
                    sb = sp.get("bbox")
                    if not sb:
                        continue
                    rects.append((fitz.Rect(sb), float(sp.get("size", 11) or 11)))
                if rects:
                    line_texts.append((_norm_line(" ".join(sp.get("text", "") for sp in ln.get("spans", []))), rects))
        pairs = []
        for i in range(len(line_texts)):
            for j in range(i + 1, len(line_texts)):
                for sa, sza in line_texts[i][1]:
                    for sb, szb in line_texts[j][1]:
                        inter = sa & sb
                        if inter.is_empty:
                            continue
                        min_sz = min(sza, szb)
                        if inter.get_area() > 4.0 and inter.height > min_sz * 0.35:
                            pairs.append((line_texts[i][0], line_texts[j][0]))
                            break
        return pairs

    def _pre_existing_overlap(a, b, src_pairs):
        """True if the two (normalized) line texts already overlapped in source."""
        if not a or not b:
            return False
        for pa, pb in src_pairs:
            if not pa or not pb:
                continue
            hit_a = a in pa or pa in a or a.split()[0] in pa or pa.split()[0] in a
            hit_b = b in pb or pb in b or b.split()[0] in pb or pb.split()[0] in b
            if hit_a and hit_b:
                return True
            hit_a2 = a in pb or pb in a or a.split()[0] in pb or pb.split()[0] in a
            hit_b2 = b in pa or pa in b or b.split()[0] in pa or pa.split()[0] in b
            if hit_a2 and hit_b2:
                return True
        return False

    def _collision_check(page, translatable, occupied, src_page=None):
        count = 0
        src_pairs = _span_overlaps(src_page) if src_page is not None else []
        d = page.get_text("dict")
        line_rects = []
        for b in d.get("blocks", []):
            if b.get("type") != 0:
                continue
            for ln in b.get("lines", []):
                rects = []
                for sp in ln.get("spans", []):
                    if not sp.get("text", "").strip():
                        continue
                    sb = sp.get("bbox")
                    if not sb:
                        continue
                    rects.append((fitz.Rect(sb), float(sp.get("size", 11) or 11)))
                if rects:
                    line_rects.append((_norm_line(" ".join(sp.get("text", "") for sp in ln.get("spans", []))), rects))
        for i in range(len(line_rects)):
            for j in range(i + 1, len(line_rects)):
                for sa, sza in line_rects[i][1]:
                    for sb, szb in line_rects[j][1]:
                        inter = sa & sb
                        if inter.is_empty:
                            continue
                        min_sz = min(sza, szb)
                        if inter.get_area() > 4.0 and inter.height > min_sz * 0.35:
                            if _pre_existing_overlap(line_rects[i][0], line_rects[j][0], src_pairs):
                                continue
                            count += 1
                            if os.environ.get("TRI_DEBUG") and count <= 8:
                                print(f"    [_collision] A={line_rects[i][0][:26]!r} "
                                      f"B={line_rects[j][0][:26]!r} "
                                      f"area={inter.get_area():.1f} h={inter.height:.1f} "
                                      f"bboxA={[round(v,1) for v in sa]} "
                                      f"bboxB={[round(v,1) for v in sb]}")
                            break
        return count

    def _process_page(doc, page_num, translatable, occupied, src_page, layout_plan):
        page = doc[page_num]
        page_width = page.rect.width
        page_height = page.rect.height
        issues = []
        from collections import Counter as _Counter
        recreated = _Counter()
        try:
            imgs_before = _image_snapshot(page)
            redact_rects = []
            src_pix = src_page.get_pixmap() if src_page is not None else None
            for b in translatable:
                for ln in b.get("lines", []):
                    lbbox = ln.get("bbox", [0, 0, 0, 0])
                    lx0, ly0, lx1, ly1 = (float(v) for v in lbbox)
                    if lx1 <= lx0 or ly1 <= ly0:
                        continue
                    pad = 2.5
                    rr = fitz.Rect(max(0.0, lx0 - pad), max(0.0, ly0 - pad),
                                   min(page_width, lx1 + pad), min(page_height, ly1 + pad))
                    redact_rects.append(rr)
                    bg = BackgroundSampler.sample(src_page, (rr.x0, rr.y0, rr.x1, rr.y1), src_pix)
                    page.add_redact_annot(rr, fill=bg if bg is not None else None)
                    for l in ln.get("links", []):
                        fr = l.get("from")
                        if not fr:
                            continue
                        lr = fitz.Rect(fr)
                        if not lr.is_empty:
                            redact_rects.append(lr)
                            bg = BackgroundSampler.sample(src_page, (lr.x0, lr.y0, lr.x1, lr.y1), src_pix)
                            page.add_redact_annot(lr, fill=bg if bg is not None else None)
            if not redact_rects:
                return True, issues
            page.apply_redactions(images=0, graphics=0, text=0)

            if os.environ.get("TRI_DEBUG"):
                print(f"    [_process_page] page {page_num} redacted "
                      f"{len(redact_rects)} rects; spans-after={_count_spans(page)}")

            if _image_snapshot(page) != imgs_before:
                issues.append("I1:image-bytes-changed")

            leftover = _spans_in_rects(page, redact_rects)
            if leftover:
                issues.append(f"I2:orig-spans-remain({leftover})")

            for bi, b in enumerate(translatable):
                _insert_block(page, b, page_width, page_height, occupied, bi, layout_plan, recreated)
        except Exception as e:
            issues.append(f"I4:exception:{str(e)[:90]}")

        if not issues:
            collide = _collision_check(page, translatable, occupied, src_page)
            if collide:
                issues.append(f"I3:collision({collide})")

        _reconcile_links(page, src_page, recreated)
        return len(issues) == 0, issues

    def _reconcile_links(page, src_page, recreated):
        """Restore link annotations that redaction removed.

        Redaction deletes link annotations whose rects intersect any redaction
        rect. Kept (translatable) links are normally re-created per line (and
        tracked in `recreated`); this pass restores any source link still
        missing afterwards (e.g. passthrough links on preserved garbage text
        whose rects happened to overlap a redaction rect, or duplicate-URI
        links that share a single re-created anchor). Note that links inserted
        via insert_link() are not visible to page.get_links() until the
        document is saved, so recreated keys are passed in explicitly.
        """
        from collections import Counter
        have = Counter(recreated)
        for l in page.get_links():
            uri = l.get("uri", "") or ""
            if uri:
                have[(l.get("kind", 2), uri)] += 1
        need = Counter()
        for l in src_page.get_links():
            uri = l.get("uri", "") or ""
            if uri:
                need[(l.get("kind", 2), uri)] += 1
        for key, cnt in need.items():
            missing = cnt - have.get(key, 0)
            if missing <= 0:
                continue
            kind, uri = key
            for l in src_page.get_links():
                if missing <= 0:
                    break
                if l.get("uri", "") != uri:
                    continue
                if l.get("kind", 2) != kind:
                    continue
                fr = l.get("from")
                if not fr:
                    continue
                try:
                    page.insert_link({"kind": kind, "from": fitz.Rect(fr), "uri": uri})
                    missing -= 1
                except Exception:
                    pass

    def _fallback_page(doc, src_doc, page_num):
        doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)
        doc.delete_page(page_num)
        last = doc.page_count - 1
        doc.move_page(last, page_num)

    # ---- group blocks by page ----
    pages_blocks = {}
    for block in blocks:
        p = block.get("page", 0)
        pages_blocks.setdefault(p, []).append(block)

    fallback_log = {}
    still_failing = {}

    for page_num in sorted(pages_blocks):
        page_blocks = pages_blocks[page_num]
        if page_num >= len(doc):
            continue
        translatable = [b for b in page_blocks if not b.get("passthrough")]
        if not translatable:
            continue
        src_page = src_doc[page_num]
        occupied = []
        for bi, b in enumerate(translatable):
            for ln in b.get("lines", []):
                lb = ln.get("bbox", [0, 0, 0, 0])
                occupied.append((fitz.Rect([float(v) for v in lb]), bi))
        transl_rects = [r for r, _ in occupied]
        for tb in src_page.get_text("blocks"):
            if len(tb) < 6:
                continue
            txt = (tb[4] or "").strip()
            if not txt:
                continue
            tr = fitz.Rect(tb[0], tb[1], tb[2], tb[3])
            if any(tr.intersects(x) for x in transl_rects):
                continue
            occupied.append((tr, None))

        ok, issues = _process_page(doc, page_num, translatable, occupied, src_page, layout_plan)
        if not ok:
            _fallback_page(doc, src_doc, page_num)
            fallback_log[page_num] = issues
            ok2, issues2 = _process_page(doc, page_num, translatable, occupied, src_page, layout_plan)
            if not ok2:
                still_failing[page_num] = issues2

    for pn, iss in fallback_log.items():
        print(f"  [Fallback] page {pn}: triggered by {iss}")
    for pn, iss in still_failing.items():
        print(f"  [Fallback] page {pn}: still failing after rebuild: {iss}")

    doc.save(output_file, incremental=False)
    doc.close()
    src_doc.close()

def write_txt(blocks, output_file):
    """Write blocks to plain text."""
    with open(output_file, "w", encoding="utf-8") as f:
        for block in blocks:
            if isinstance(block, dict):
                f.write(block.get("text", "") + "\n\n")


def write_csv(blocks_data, output_file):
    """Write translated CSV data preserving row/column structure."""
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(blocks_data)


def write_pptx(blocks, output_file, original_file=None):
    """
    Write translated blocks to a PowerPoint file.
    Modifies the original PPTX in-place, preserving all formatting.
    """
    from pptx import Presentation

    if original_file and os.path.exists(original_file):
        prs = Presentation(original_file)
        para_blocks = [b for b in blocks if b.get("type") == "paragraph"]

        block_map = {}
        for b in para_blocks:
            key = (b.get("slide"), b.get("shape_id"), b.get("para_idx"))
            block_map[key] = b

        for slide_idx, slide in enumerate(prs.slides):
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                for para_idx, para in enumerate(shape.text_frame.paragraphs):
                    key = (slide_idx, shape.shape_id, para_idx)
                    if key in block_map:
                        translated_text = block_map[key]["text"]
                        _apply_translation_to_paragraph(para, translated_text, None)

        prs.save(output_file)
        print(f"  [OK] PPTX saved with full layout preservation")


def write_xlsx(blocks, output_file, original_file=None):
    """
    Write translated blocks to an Excel file.
    Modifies the original XLSX in-place, preserving all formatting.
    """
    from openpyxl import load_workbook

    if original_file and os.path.exists(original_file):
        wb = load_workbook(original_file)
        cell_blocks = [b for b in blocks if b.get("type") == "cell"]

        for block in cell_blocks:
            sheet_name = block.get("sheet")
            if sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                cell = ws.cell(row=block["row"], column=block["col"])
                cell.value = block["text"]

        wb.save(output_file)
        wb.close()
        print(f"  [OK] XLSX saved with full layout preservation")
    else:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Translated"

        cell_blocks = [b for b in blocks if b.get("type") == "cell"]
        for block in cell_blocks:
            ws.cell(row=block.get("row", 1), column=block.get("col", 1)).value = block["text"]

        wb.save(output_file)
        print(f"  [OK] XLSX saved (new workbook)")


def choose_output_path(input_file, output_dir=""):
    """Decide output filename based on input format capabilities."""
    base = os.path.splitext(os.path.basename(input_file))[0]
    ext = os.path.splitext(input_file)[1].lower()
    WRITABLE_FORMATS = {
        ".docx": ".docx", ".txt": ".txt", ".md": ".md",
        ".pdf":  ".pdf",  ".csv": ".csv",
        ".rtf":  ".docx", ".odt": ".docx",
        ".pptx": ".pptx", ".xlsx": ".xlsx",
    }
    out_ext = WRITABLE_FORMATS.get(ext, ".docx")
    out_name = f"translated_{base}{out_ext}"
    return os.path.join(output_dir, out_name) if output_dir else out_name


def reconstruct_document(blocks, output_file, original_file=None, original_ext=None,
                         source_lang="", target_lang="",
                         layout_plan=None):
    """Write translated blocks to the appropriate output format."""
    ext = os.path.splitext(output_file)[1].lower()

    if ext == ".docx":
        write_docx(blocks, output_file, original_file)
    elif ext == ".pdf" and original_file:
        write_pdf_preserved(blocks, original_file, output_file,
                            layout_plan=layout_plan,
                            source_lang=source_lang, target_lang=target_lang)
    elif ext == ".pptx":
        write_pptx(blocks, output_file, original_file)
    elif ext == ".xlsx":
        write_xlsx(blocks, output_file, original_file)
    elif ext in {".txt", ".md"}:
        write_txt(blocks, output_file)
    elif ext == ".csv":
        if isinstance(blocks, list) and blocks and "data" in blocks[0]:
            write_csv(blocks[0]["data"], output_file)
        else:
            write_csv(blocks, output_file)
    else:
        write_txt(blocks, output_file)