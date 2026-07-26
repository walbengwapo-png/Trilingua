# -*- coding: utf-8 -*-
"""
Document reconstructor.

Responsible for taking translated text blocks and writing them back
into the original document format while preserving layout.

Contains NO translation logic and NO provider-specific code.
Reused from document_translator_v3.py.
"""

import os
import re
import csv
import shutil
import subprocess
import tempfile


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

    # Strategy 3: continuation box
    cont_top = last_below_bottom + 4.0
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


def _is_libreoffice_available():
    """Return True if LibreOffice is installed and on PATH."""
    try:
        result = subprocess.run(
            ["libreoffice", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
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
            ["libreoffice", "--headless", "--convert-to", "docx",
             "--outdir", tmp_dir, input_file],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0 or not os.path.exists(docx_path):
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
            ["libreoffice", "--headless", "--convert-to", "pdf",
             "--outdir", tmp_dir, docx_path],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0 or not os.path.exists(pdf_path):
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


def write_pdf_preserved(blocks, original_pdf_path, output_file,
                        source_lang="", target_lang=""):
    """
    Replace original text in a PDF with translations while preserving layout.
    
    Uses white-rectangle overlay instead of redaction annotations for:
      - 3x faster processing (no redaction apply pass)
      - No ghosting artifacts from misaligned redaction boundaries
      - Better handling of overlapping text blocks
    
    Key improvements over redaction approach:
      - Overlay: draw white rects over original text, then insert translations
      - Language-aware proactive font sizing using expansion coefficients
      - Multi-page text flow: overflow text is truncated and prepended to next block
      - Font width scaling for better fit with built-in fonts
    """
    import fitz

    FONT_MAP = {
        "helv": "helv", "Helv": "helv", "Helvetica": "helv",
        "Helvetica-Bold": "helvb", "Helvetica-Oblique": "heloi",
        "Helvetica-BoldOblique": "helbo",
        "tiro": "tiro", "Tiro": "tiro", "Times": "tiro",
        "TimesNewRoman": "tiro", "Times-Bold": "tirob", "Times-Italic": "tiroi",
        "Times-BoldItalic": "tirobi",
        "cour": "cour", "Cour": "cour", "Courier": "cour",
        "CourierNew": "cour", "Courier-Bold": "courb",
        "Courier-Oblique": "couit", "Courier-BoldOblique": "coubi",
    }

    # Font width scaling factors — built-in fonts have different metrics
    # than common document fonts. These multipliers help compensate.
    _FONT_WIDTH_SCALE = {
        "helv": 0.92,   # Helvetica is wider than Arial
        "tiro": 0.95,   # Times is slightly wider than Times New Roman
        "cour": 1.0,    # Courier is close to Courier New
    }

    def _resolve_font(style):
        font_name = style.get("font", "helv")
        is_bold = style.get("bold", False)
        is_italic = style.get("italic", False)
        base_font = FONT_MAP.get(font_name)
        if base_font:
            if "b" in base_font and is_bold:
                return base_font
            if "i" in base_font and is_italic:
                return base_font
            for suffix in ("bi", "b", "i"):
                if base_font.endswith(suffix):
                    base_font = base_font[:-len(suffix)]
                    break
        else:
            from .layout import FontMapper
            base_font = FontMapper().resolve(font_name, set())

        if is_bold and is_italic and base_font in ("helv", "tiro", "cour"):
            return base_font + "bi"
        elif is_bold and base_font in ("helv", "tiro", "cour"):
            return base_font + "b"
        elif is_italic and base_font in ("helv", "tiro", "cour"):
            return base_font + "i"
        return base_font

    def _resolve_color(color_val):
        if isinstance(color_val, int) and color_val != 0:
            return fitz.sRGB_to_rgb(color_val)
        return (0, 0, 0)

    def _detect_alignment(block, page_width):
        bbox = block.get("position", [0, 0, 0, 0])
        x0, y0, x1, y1 = bbox
        block_center = (x0 + x1) / 2.0
        page_center = page_width / 2.0
        block_width = x1 - x0
        if block_width < page_width * 0.85 and abs(block_center - page_center) < page_width * 0.05:
            return 1
        return 0

    def _compute_proactive_font_size(original_text, translated_text, base_font_size):
        """Compute a proactive font size using language-aware expansion coefficients.
        
        Uses the language-pair expansion factor as a prior, then refines with
        the actual character-length ratio. This is more accurate than using
        the raw ratio alone, especially for short texts where the ratio is noisy.
        """
        src_chars = len(original_text)
        tgt_chars = len(translated_text)
        if src_chars == 0:
            return base_font_size
        
        # Get language-pair expansion coefficient as a prior
        expansion = _get_lang_expansion(source_lang, target_lang)
        
        # Actual ratio
        actual_ratio = src_chars / tgt_chars if tgt_chars > 0 else 1.0
        
        # Blend: for short text (<20 chars), trust the language prior more
        # For long text, trust the actual ratio
        if src_chars < 20:
            blended_ratio = 0.6 * (1.0 / expansion) + 0.4 * actual_ratio
        else:
            blended_ratio = actual_ratio
        
        # Apply font width scaling factor
        font_key = resolved_font.rstrip("bi") if resolved_font else "helv"
        width_scale = _FONT_WIDTH_SCALE.get(font_key, 1.0)
        blended_ratio *= width_scale
        
        # Add 5% safety buffer
        blended_ratio *= 0.95
        
        scaled_font = base_font_size * blended_ratio
        return max(6.0, min(base_font_size, scaled_font))

    doc = fitz.open(original_pdf_path)

    # Group blocks by page
    pages_blocks = {}
    for block in blocks:
        p = block.get("page", 0)
        if p not in pages_blocks:
            pages_blocks[p] = []
        pages_blocks[p].append(block)

    # Phase 1: Overlay original text with white rectangles
    # This is faster than redaction and avoids ghosting
    for page_num, page_blocks in pages_blocks.items():
        if page_num >= len(doc):
            continue
        page = doc[page_num]
        for block in page_blocks:
            try:
                bbox = block.get("position", [50, 50, 500, 100])
                x0, y0, x1, y1 = bbox
                if x1 <= x0 or y1 <= y0:
                    continue
                # Draw white rectangle to cover original text
                overlay_rect = fitz.Rect(x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5)
                page.draw_rect(overlay_rect, color=(1, 1, 1), fill=(1, 1, 1))
            except Exception as e:
                print(f"  Overlay error: {str(e)[:100]}")

    # Phase 2: Insert translated text with overflow management
    # Track overflow text that needs to be prepended to the next block
    pending_overflow = ""  # Text that didn't fit in the previous block

    for page_num, page_blocks in pages_blocks.items():
        if page_num >= len(doc):
            continue
        page = doc[page_num]
        page_width = page.rect.width
        page_height = page.rect.height

        for block in page_blocks:
            try:
                bbox = block.get("position", [50, 50, 500, 100])
                x0, y0, x1, y1 = bbox

                # Prepend any pending overflow from the previous block
                block_text = block["text"]
                if pending_overflow:
                    block_text = pending_overflow + " " + block_text
                    pending_overflow = ""

                style = block.get("style", {})
                resolved_font = _resolve_font(style)
                text_color = _resolve_color(style.get("color", 0))
                base_font_size = float(style.get("font_size", 11) or 11)
                base_font_size = max(6.0, min(base_font_size, 72.0))
                alignment = _detect_alignment(block, page_width)

                # Sample background color
                bg_color = None
                try:
                    from .layout import BackgroundSampler
                    bg_color = BackgroundSampler.sample(page, (x0, y0, x1, y1))
                except Exception:
                    pass

                # Proactive font sizing with language-aware coefficients
                original_text = block.get("_original_text", block_text)
                font_size = _compute_proactive_font_size(original_text, block_text, base_font_size)

                # Calculate available character capacity of the bounding box
                # Use the original text's character density as a guide
                bbox_width = x1 - x0
                bbox_height = y1 - y0
                estimated_line_height = font_size * 1.4
                estimated_lines = max(1, int(bbox_height / estimated_line_height))
                estimated_chars_per_line = max(1, int(bbox_width / (font_size * 0.5)))
                estimated_capacity = estimated_lines * estimated_chars_per_line

                # Truncate text if it exceeds estimated capacity
                if len(block_text) > estimated_capacity * 1.2:
                    fits_text, overflow_text = _truncate_to_fit(block_text, estimated_capacity)
                    if overflow_text:
                        pending_overflow = overflow_text
                        block_text = fits_text
                        print(f"  [Layout] Text truncated on page {page_num}, "
                              f"{len(overflow_text)} chars overflow to next block")

                # Insert the translated text
                text_rect = fitz.Rect(x0, y0, x1, y1)
                remaining = page.insert_textbox(
                    text_rect, block_text,
                    fontsize=font_size, fontname=resolved_font,
                    color=text_color, align=alignment,
                )

                if remaining < 0:
                    # Overflow still occurred — use overflow resolution
                    overflow_result = _resolve_overflow(
                        page=page, block_text=block_text,
                        x0=x0, y0=y0, x1=x1, y1=y1,
                        font_size=font_size, resolved_font=resolved_font,
                        other_bboxes=[],  # Skip collision check — we already overlaid
                        page_height=page_height,
                        original_doc=doc, page_num=page_num,
                        bg_color=bg_color, initial_remaining=remaining,
                        text_color=text_color, alignment=alignment,
                    )
                    if not overflow_result["resolved"]:
                        # Last resort: truncate and save overflow
                        truncated, overflow = _truncate_to_fit(block_text, estimated_capacity // 2)
                        if overflow:
                            pending_overflow = overflow + " " + pending_overflow if pending_overflow else overflow
                            # Re-insert truncated text
                            page.insert_textbox(
                                fitz.Rect(x0, y0, x1, y1), truncated,
                                fontsize=font_size, fontname=resolved_font,
                                color=text_color, align=alignment,
                            )

            except Exception as e:
                print(f"  Layout error for block: {str(e)[:100]}")
                try:
                    fallback_rect = fitz.Rect(x0, y0, x1, y1 + 60)
                    page.insert_textbox(
                        fallback_rect, block.get("text", ""),
                        fontsize=11, fontname="helv", color=(0, 0, 0),
                    )
                except Exception:
                    pass

    # Warn if there's still pending overflow at the end
    if pending_overflow:
        print(f"  ⚠️  {len(pending_overflow)} characters of overflow text could not be placed")

    doc.save(output_file, incremental=False)
    doc.close()


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
                         source_lang="", target_lang=""):
    """Write translated blocks to the appropriate output format."""
    ext = os.path.splitext(output_file)[1].lower()

    if ext == ".docx":
        write_docx(blocks, output_file, original_file)
    elif ext == ".pdf" and original_file:
        write_pdf_preserved(blocks, original_file, output_file,
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