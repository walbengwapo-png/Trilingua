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
                                            glossary_store=None, progress_callback=None,
                                            save=True):
    """
    Translate a DOCX file in-place using a provided translation function.
    
    Args:
        input_file: Path to source DOCX
        output_file: Path to save translated DOCX
        translate_fn: Callable(text, block_type) -> translated_text
        glossary_store: Optional GlossaryStore for post-processing
        progress_callback: Optional callable(completed, total)
        save: Whether to write output_file. When False, the document is only
            walked (used to collect translatable text in call order without
            writing a file).
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

    if save:
        doc.save(output_file)


def translate_pptx_inplace(input_file, output_file, translate_fn,
                           glossary_store=None, progress_callback=None,
                           save=True):
    """
    Translate a PPTX file by iterating slides/shapes/paragraphs in-place.
    Uses a provided translation function instead of a hardcoded AI provider.

    Args:
        save: Whether to write output_file. When False, the deck is only
            walked (used to collect translatable text in call order).
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
            # ``placeholder_format`` is exposed by python-pptx on every shape,
            # but accessing it for a regular text box raises ValueError
            # ("shape is not a placeholder"). Check the explicit flag before
            # asking the shape for placeholder metadata.
            if shape.is_placeholder:
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

    if save:
        prs.save(output_file)
        print(f"  [OK] PPTX saved with layout preservation ({completed} items translated)")


def translate_xlsx_inplace(input_file, output_file, translate_fn,
                           glossary_store=None, progress_callback=None,
                           save=True):
    """
    Translate an XLSX file by iterating all cells in-place.
    Uses a provided translation function.

    Args:
        save: Whether to write output_file. When False, the workbook is only
            walked (used to collect translatable text in call order).
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

    if save:
        wb.save(output_file)
        print(f"  [OK] XLSX saved with perfect layout preservation ({completed} cells translated)")
    wb.close()


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

    Strategy: preserve artwork, replace source text, fit complete blocks.

      - Original text is removed per LINE via ``apply_redactions(images=0,
        graphics=0, text=0)`` so images and vector graphics survive untouched.
      - Normalize page rotation, then measure complete translated blocks.
      - Expand into free space, with bounded shrinking to a readable floor.
      - Move overflowing blocks to continuation pages after their source page.
      - Hyperlink annotations are re-created at the translated line positions.
      - Garbage/passthrough blocks are skip-listed: original text and links stay.

    Reopen the saved PDF to validate fragment coverage, orientation and geometry.
    Failed checks raise PDFValidationError instead of returning a false success.
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

    # Native normalization keeps displayed artwork and links in one coordinate space.
    import copy
    original_blocks = blocks
    blocks = copy.deepcopy(blocks)
    transforms = {}
    for page_num in range(len(src_doc)):
        transforms[page_num] = src_doc[page_num].rotation_matrix
        src_doc[page_num].remove_rotation()
        doc[page_num].remove_rotation()
    for block in blocks:
        # Legacy symbol fonts use private-use codepoints for these bullet marks.
        block["text"] = (block.get("text") or "").translate({0xf07d: "•", 0xe601: "•"})
        page_num = int(block.get("page", 0))
        if page_num < 0 or page_num >= len(src_doc):
            raise ValueError(f"PDF block references missing page {page_num}")
        if block.get("pdf_coordinates") != "display":
            matrix = transforms[page_num]
            block["position"] = list(fitz.Rect(block.get("position", (0, 0, 0, 0))) * matrix)
            for line in block.get("lines", []):
                line["bbox"] = list(fitz.Rect(line["bbox"]) * matrix)
                line["baseline"] = line["bbox"][3] - float(line.get("size", 11)) * .2
                for link in line.get("links", []):
                    key = "rect" if "rect" in link else "from"
                    if link.get(key):
                        link[key] = list(fitz.Rect(link[key]) * matrix)
        # Old sidecars did not retain block style. Recover it from source lines.
        if not block.get("style") and block.get("lines"):
            # Older extraction sometimes combined a large heading with body.
            # Recover the dominant text style, rather than enlarging all body text.
            from collections import Counter
            weights = Counter()
            for line in block["lines"]:
                weights[(line.get("font"), line.get("size"), line.get("bold"),
                         line.get("italic"))] += len(line.get("text", ""))
            dominant = weights.most_common(1)[0][0]
            first = next(line for line in block["lines"] if (
                line.get("font"), line.get("size"), line.get("bold"), line.get("italic")) == dominant)
            block["style"] = {key: first[key] for key in
                              ("font", "font_original", "bold", "italic", "color") if key in first}
            block["style"]["font_size"] = first.get("size", 11)
        _ensure_lines(block)

    placements = []
    continuations = {}
    continuation_title = {
        "Cebuano": "Gipadayon gikan sa orihinal nga panid {}",
        "Filipino": "Karugtong mula sa orihinal na pahina {}",
    }.get(target_lang, "Continued from source page {}")
    continuation_reference = {
        "Cebuano": "Padayon sa panid {}",
        "Filipino": "Karugtong sa pahina {}",
    }.get(target_lang, "Continued on page {}")

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
        if total_w > available + .05:
            return None
        if alignment == 1:
            px = x0 + (available - total_w) / 2.0
        elif alignment == 2:
            px = x1 - total_w
        else:
            px = x0
        start_x = px
        max_size = 0.0
        top, bottom = y, y
        for seg, fn, fo, sz, col, tw in placed:
            try:
                page.insert_text((px, y), seg, fontsize=sz, fontname=fn, color=col)
            except Exception as e:
                print(f"  [InsertWarn] page {page.number}: run insert_text failed "
                      f"fontname={fn} text={seg[:40]!r}: {type(e).__name__}: {e}")
            px += tw
            max_size = max(max_size, sz)
            top = min(top, y - fo.ascender * sz)
            bottom = max(bottom, y - fo.descender * sz)
        return fitz.Rect(start_x, top, start_x + total_w, bottom)

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

    def _wrap_complete(text, font, size, width):
        """Wrap complete paragraphs; split long URLs/tokens without dropping chars."""
        result = []
        for paragraph in text.split("\n"):
            words = paragraph.split()
            if not words:
                result.append("")
                continue
            line = ""
            for word in words:
                if line and _text_width(line + " " + word, font, size) <= width:
                    line += " " + word
                    continue
                if line:
                    result.append(line)
                    line = ""
                while _text_width(word, font, size) > width:
                    end = 1
                    while end < len(word) and _text_width(word[:end + 1], font, size) <= width:
                        end += 1
                    if _text_width(word[:end], font, size) > width:
                        raise ValueError("PDF text area is narrower than a single glyph")
                    result.append(word[:end])
                    word = word[end:]
                line = word
            if line:
                result.append(line)
        return result

    def _block_metrics(block, page, size):
        _, font = _resolve_line_font(block.get("style", {}), page, block.get("text", ""))
        fonts = [font]
        styles = [block.get("style", {})] + [run for line in block.get("lines", [])
                                              for run in line.get("runs", [])]
        for style in styles:
            # Mixed runs can resolve ASCII segments to Base-14 while punctuation
            # uses a system font. Measure both choices before placing the line.
            fonts.extend(_resolve_line_font(style, page, text)[1]
                         for text in (block.get("text", ""), ""))
        ascent = max(font.ascender for font in fonts)
        descent = min(font.descender for font in fonts)
        return ascent, descent, max((ascent - descent) * size + 1.5, size * 1.35)

    def _place_lines(page, block, index, rect, lines, size, action, recreated=None):
        style = block.get("style", {})
        fontname, font = _resolve_line_font(style, page, block.get("text", ""))
        ascent, descent, leading = _block_metrics(block, page, size)
        y = rect.y0 + ascent * size
        alignment = _block_alignment(block, page.rect.width) if action == "fit" else 0
        runs = [dict(run, size=size) for line in block.get("lines", [])
                for run in line.get("runs", [])]
        mixed = len({(r.get("font"), r.get("bold"), r.get("italic"), r.get("color")) for r in runs}) > 1
        for text in lines:
            if text:
                placed = _insert_line_runs(page, text, rect.x0, rect.x1, y, runs, alignment) if mixed else None
                if placed is None:
                    placed = _insert_line(page, text, rect.x0, rect.x1, y, fontname,
                                          font, size, _resolve_color(style.get("color", 0)), alignment)
                    if placed is not None:
                        placed.y0 = y - font.ascender * size
                        placed.y1 = y - font.descender * size
                if placed is None:
                    raise ValueError(f"PDF insertion failed for block {index}")
                placements.append({"block_index": index, "source_page": block.get("page", 0),
                                   "page_xref": page.xref, "rect": list(placed),
                                   "text": text, "font_size": size, "action": action})
                links = block.get("links", []) or [link for ln in block.get("lines", [])
                                                   for link in ln.get("links", [])]
                _recreate_links(page, {"links": links}, placed, recreated)
            y += leading
        return y

    def _insert_block(page, block, page_width, page_height, occupied, block_index, layout_plan, recreated=None):
        index = block["_render_index"]
        text = (block.get("text") or "").strip()
        if not text:
            return
        box = fitz.Rect(block["position"]) & page.rect
        style = block.get("style", {})
        name, font = _resolve_line_font(style, page, text)
        base_size = max(8.0, min(float(style.get("font_size", 11) or 11), 72.0))
        role = block.get("type", "paragraph")
        floor = max(8.0, base_size * (.85 if role in {"heading", "title", "header"} else .8))
        # Extend downward only into free space in this column, never into another
        # block, table cell, illustration or text already placed on the page.
        bottom = min(page_height - 2, box.y1)
        candidates = []
        for rect, tag in occupied:
            if tag == block_index or rect.x1 <= box.x0 or rect.x0 >= box.x1:
                continue
            if rect.y0 >= box.y1 - .5:
                candidates.append(rect.y0 - 2)
        if candidates:
            bottom = max(bottom, min(candidates))
        elif role != "table_cell":
            bottom = page_height - 2
        area = fitz.Rect(box.x0, box.y0, box.x1, bottom)
        sizes = [base_size, max(floor, base_size * .9), floor]
        for size in dict.fromkeys(sizes):
            if area.width < _text_width("W", font, size) or area.height <= 0:
                break
            lines = _wrap_complete(text, font, size, area.width)
            source_runs = [dict(run, size=size) for line in block.get("lines", [])
                           for run in line.get("runs", [])]
            if len(block.get("lines", [])) == 1 and len(source_runs) > 1:
                chunk, end, fits = _fit_chunk_runs(text.split(), 0, source_runs, size, area.width, page)
                if fits and end == len(text.split()):
                    lines = [chunk]
            ascent, descent, leading = _block_metrics(block, page, size)
            height = (len(lines) - 1) * leading + (ascent - descent) * size
            target = fitz.Rect(area.x0, area.y0, area.x1, area.y0 + height)
            if height > area.height + .1:
                continue
            if any(tag != block_index and target.intersects(rect) and
                   (target & rect).get_area() > 1 for rect, tag in occupied):
                continue
            _place_lines(page, block, index, target, lines, size, "fit", recreated)
            occupied.append((target, block_index))
            return
        # Whole blocks move together to readable continuation pages. Nothing is
        # shortened, and source headings/bullets remain independent blocks.
        continuations.setdefault(block.get("page", 0), []).append(block)





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
            protected = [fitz.Rect(line["bbox"]) for block in pages_blocks.get(page_num, [])
                         if block.get("passthrough") for line in block.get("lines", [])]

            def redact_without_passthrough(rect):
                # Redaction padding and clipped source text can intersect icons
                # or numeric labels. Remove only the unprotected parts.
                pieces = [rect]
                for keep in protected:
                    remaining = []
                    for piece in pieces:
                        overlap = piece & keep
                        if overlap.is_empty:
                            remaining.append(piece)
                            continue
                        remaining.extend(candidate for candidate in (
                            fitz.Rect(piece.x0, piece.y0, piece.x1, overlap.y0),
                            fitz.Rect(piece.x0, overlap.y1, piece.x1, piece.y1),
                            fitz.Rect(piece.x0, overlap.y0, overlap.x0, overlap.y1),
                            fitz.Rect(overlap.x1, overlap.y0, piece.x1, overlap.y1),
                        ) if not candidate.is_empty)
                    pieces = remaining
                for piece in pieces:
                    redact_rects.append(piece)
                    bg = BackgroundSampler.sample(src_page, tuple(piece), src_pix)
                    page.add_redact_annot(piece, fill=bg if bg is not None else None)
            for b in translatable:
                for ln in b.get("lines", []):
                    lbbox = ln.get("bbox", [0, 0, 0, 0])
                    lx0, ly0, lx1, ly1 = (float(v) for v in lbbox)
                    if lx1 <= lx0 or ly1 <= ly0:
                        continue
                    pad = 2.5
                    rr = fitz.Rect(max(0.0, lx0 - pad), max(0.0, ly0 - pad),
                                   min(page_width, lx1 + pad), min(page_height, ly1 + pad))
                    redact_without_passthrough(rr)
                    for l in ln.get("links", []):
                        fr = l.get("from")
                        if not fr:
                            continue
                        lr = fitz.Rect(fr)
                        if not lr.is_empty:
                            redact_without_passthrough(lr)
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


    # ---- group blocks by page ----
    pages_blocks = {}
    for block in blocks:
        p = block.get("page", 0)
        pages_blocks.setdefault(p, []).append(block)

    source_pages = len(src_doc)
    source_artifacts = []
    for index, block in enumerate(blocks):
        block["_render_index"] = index
    extras = {}
    try:
        for page_num in sorted(pages_blocks):
            page_blocks = pages_blocks[page_num]
            for block in page_blocks:
                if not block.get("passthrough"):
                    continue
                for line in block.get("lines", []):
                    text = line.get("text", "").strip()
                    font = (line.get("font_original") or line.get("font", "")).lower()
                    rect = fitz.Rect(line["bbox"])
                    source_page = src_doc[page_num]
                    if not source_page.rect.contains(rect):
                        visible = source_page.get_text("text", clip=rect & source_page.rect).strip()
                        if text not in visible:
                            source_artifacts.append({"block_index": block["_render_index"],
                                                     "source_page": page_num,
                                                     "reason": "Pre-existing clipped source text", "text": text})
                            continue
                        rect &= source_page.rect
                    # Pure private-use icon codes represent artwork. They are
                    # protected from redaction, not treated as translated prose.
                    artwork = any(name in font for name in ("icons", "wingdings", "webdings", "zapfdingbats"))
                    if text and not artwork and not all(0xe000 <= ord(c) <= 0xf8ff or c.isspace() for c in text):
                        placements.append({"block_index": block["_render_index"],
                                           "source_page": page_num, "page_xref": doc[page_num].xref,
                                           "rect": list(rect), "text": line["text"],
                                           "font_size": line.get("size", 11), "action": "passthrough"})
            translatable = [b for b in page_blocks if not b.get("passthrough")]
            if not translatable:
                continue
            src_page = src_doc[page_num]
            occupied = [(fitz.Rect(b["position"]), i) for i, b in enumerate(translatable)]
            # Source blocks excluded from translation and illustrations are obstacles.
            for block in page_blocks:
                if block.get("passthrough"):
                    occupied.append((fitz.Rect(block["position"]), None))
            for image in src_page.get_image_info():
                occupied.append((fitz.Rect(image["bbox"]), None))
            # Ruled forms and tables have row boundaries even when extraction
            # labels their text as paragraphs. Never expand through those rules.
            drawings = src_page.get_drawings()
            for drawing in drawings:
                for item in drawing["items"]:
                    if item[0] == "l":
                        left, right = item[1:3]
                        if abs(left.y - right.y) < .5 and abs(left.x - right.x) >= 20:
                            occupied.append((fitz.Rect(min(left.x, right.x), left.y - .6,
                                                       max(left.x, right.x), left.y + .6), None))
                    elif item[0] == "re" and item[1].width >= 20:
                        rect = item[1]
                        for y in (rect.y0, rect.y1):
                            occupied.append((fitz.Rect(rect.x0, y - .6, rect.x1, y + .6), None))
            # Native clustering also covers vector illustrations (not exposed by
            # get_image_info). Text-bearing panels are backgrounds, not figures.
            for rect in src_page.cluster_drawings(drawings=drawings):
                text = src_page.get_text("text", clip=rect)
                if not any(character.isalpha() for character in text):
                    occupied.append((rect, None))
            translated_boxes = [fitz.Rect(b["position"]) for b in translatable]
            for raw in src_page.get_text("blocks"):
                rect = fitz.Rect(raw[:4])
                if len(raw) > 6 and raw[6] != 0:
                    continue
                if not any(rect.intersects(box) for box in translated_boxes):
                    occupied.append((rect, None))
            ok, issues = _process_page(doc, page_num, translatable, occupied, src_page, layout_plan)
            if not ok:
                raise ValueError(f"PDF reconstruction failed on page {page_num + 1}: {issues}")

        # Append, then reorder continuations immediately after their source page.
        for source_page, overflow_blocks in sorted(continuations.items()):
            width, height = src_doc[source_page].rect.width, src_doc[source_page].rect.height
            page, y = None, 0
            margin = min(36.0, width * .1, height * .1)
            for block in overflow_blocks:
                block = copy.deepcopy(block)
                # Pale/white source text may sit on a colored panel. Continuation
                # pages are white, so darken those colors while retaining styles.
                for style in [block.setdefault("style", {})] + [run for line in block.get("lines", [])
                                                                  for run in line.get("runs", [])]:
                    color = _resolve_color(style.get("color", 0))
                    if sum(channel * weight for channel, weight in zip(color, (.2126, .7152, .0722))) > .65:
                        style["color"] = 0
                style = block.get("style", {})
                size = max(10.0, min(float(style.get("font_size", 11) or 11), 24.0))
                for paragraph in block["text"].split("\n"):
                    # Resolve on a live page so font insertion belongs to that page.
                    if page is None:
                        page = doc.new_page(width=width, height=height)
                        extras.setdefault(source_page, []).append(page.number)
                        page.insert_text((margin, margin + 10),
                                         continuation_title.format(source_page + 1), fontsize=9)
                        y = margin + 28
                    fontname, font = _resolve_line_font(style, page, paragraph)
                    lines = _wrap_complete(paragraph, font, size, width - 2 * margin)
                    ascent, descent, leading = _block_metrics(block, page, size)
                    while lines:
                        capacity = int((height - margin - y - (ascent - descent) * size)
                                       / leading) + 1
                        if capacity < 1:
                            page = doc.new_page(width=width, height=height)
                            extras.setdefault(source_page, []).append(page.number)
                            page.insert_text((margin, margin + 10),
                                             continuation_title.format(source_page + 1), fontsize=9)
                            y = margin + 28
                            continue
                        part, lines = lines[:capacity], lines[capacity:]
                        rect = fitz.Rect(margin, y, width - margin, height - margin)
                        y = _place_lines(page, block, block["_render_index"], rect, part,
                                         size, "continuation") + (6 if block.get("type") == "heading" else 4)
                y += 4
        order = []
        for source_page in range(source_pages):
            order.append(source_page)
            order.extend(extras.get(source_page, []))
        # Add navigation at the original location only where it fits legibly.
        for source_page, overflow_blocks in continuations.items():
            page = doc[source_page]
            source_pix = src_doc[source_page].get_pixmap()
            for block in overflow_blocks:
                first_fragment = next(p for p in placements if p["block_index"] == block["_render_index"]
                                      and p["action"] == "continuation")
                target_page = next(p.number for p in doc if p.xref == first_fragment["page_xref"])
                label = continuation_reference.format(order.index(target_page) + 1)
                rect = fitz.Rect(block["lines"][0]["bbox"]) & page.rect
                fn, font = _resolve_line_font({"font": "helv"}, page, label)
                occupied_here = [fitz.Rect(p["rect"]) for p in placements if p["page_xref"] == page.xref]
                if (rect.width >= _text_width(label, font, 8) and rect.height >= (font.ascender - font.descender) * 8
                        and not any(rect.intersects(other) for other in occupied_here)):
                    background = BackgroundSampler.sample(src_doc[source_page], tuple(rect), source_pix)
                    color = block.get("style", {}).get("color", 0)
                    if background is not None:
                        color = 0xffffff if sum(channel * weight for channel, weight in
                                                zip(background, (.2126, .7152, .0722))) < .5 else 0
                    reference = {"text": label, "page": source_page,
                                 "style": {"font": "helv", "color": color}, "lines": []}
                    _place_lines(page, reference, block["_render_index"], rect, [label], 8, "reference")
        if extras:
            doc.select(order)
        saved_pages = {page.xref: page.number for page in doc}
        for placement in placements:
            placement["page"] = saved_pages[placement["page_xref"]]
        # Deflate/subset after all insertions, rather than embedding full fonts
        # and uncompressed page streams in every translated PDF.
        doc.subset_fonts()
        doc.save(output_file, garbage=3, deflate=True)
    finally:
        doc.close()
        src_doc.close()

    from validators.translation_validator import validate_pdf_output, PDFValidationError
    report = validate_pdf_output(output_file, placements, source_pages, blocks)
    report["source_artifacts"] = source_artifacts
    report["source_page_map"] = {str(page): order.index(page) for page in range(source_pages)}
    for index, block in enumerate(original_blocks):
        block["rendered_layout"] = {
            "status": report["status"],
            "fragments": [entry for entry in report["blocks"] if entry["block_index"] == index],
        }
    if report["status"] != "passed":
        raise PDFValidationError(report)
    return report


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
        return write_pdf_preserved(blocks, original_file, output_file,
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
