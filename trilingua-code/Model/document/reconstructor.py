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

    runs[0].text = translated_text
    for run in runs[1:]:
        run.text = ""


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


def write_pdf_preserved(blocks, original_pdf_path, output_file):
    """
    Redact original text from a PDF and insert translations while preserving layout.
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

    doc = fitz.open(original_pdf_path)

    pages_blocks = {}
    for block in blocks:
        p = block.get("page", 0)
        if p not in pages_blocks:
            pages_blocks[p] = []
        pages_blocks[p].append(block)

    # Phase 1: Add redaction annotations
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
                redact_rect = fitz.Rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1)
                page.add_redact_annot(redact_rect)
            except Exception as e:
                print(f"  Redact annot error: {str(e)[:100]}")

    for page_num in range(len(doc)):
        try:
            doc[page_num].apply_redactions()
        except Exception as e:
            print(f"  Apply redactions error page {page_num}: {str(e)[:100]}")

    # Phase 2: Insert translated text
    all_bboxes = []
    for p_num in sorted(pages_blocks.keys()):
        if p_num >= len(doc):
            continue
        for block in pages_blocks[p_num]:
            bbox = block.get("position", [50, 50, 500, 100])
            if len(bbox) >= 4:
                all_bboxes.append({
                    "page": p_num, "bbox": bbox, "text": block["text"],
                })

    for page_num, page_blocks in pages_blocks.items():
        if page_num >= len(doc):
            continue
        page = doc[page_num]
        page_width = page.rect.width
        page_other_bboxes = [
            pb["bbox"] for pb in all_bboxes if pb["page"] == page_num
        ]

        for block in page_blocks:
            try:
                bbox = block.get("position", [50, 50, 500, 100])
                x0, y0, x1, y1 = bbox

                style = block.get("style", {})
                resolved_font = _resolve_font(style)
                text_color = _resolve_color(style.get("color", 0))
                font_size = float(style.get("font_size", 11) or 11)
                font_size = max(6.0, min(font_size, 72.0))
                alignment = _detect_alignment(block, page_width)

                bg_color = None
                try:
                    from .layout import BackgroundSampler
                    bg_color = BackgroundSampler.sample(page, (x0, y0, x1, y1))
                except Exception:
                    pass

                text_rect = fitz.Rect(x0, y0, x1, y1)
                remaining = page.insert_textbox(
                    text_rect, block["text"],
                    fontsize=font_size, fontname=resolved_font,
                    color=text_color, align=alignment,
                )

                if remaining < 0:
                    overflow_result = _resolve_overflow(
                        page=page, block_text=block["text"],
                        x0=x0, y0=y0, x1=x1, y1=y1,
                        font_size=font_size, resolved_font=resolved_font,
                        other_bboxes=page_other_bboxes,
                        page_height=page.rect.height,
                        original_doc=doc, page_num=page_num,
                        bg_color=bg_color, initial_remaining=remaining,
                        text_color=text_color, alignment=alignment,
                    )
                    if not overflow_result["resolved"]:
                        print(f"  Unresolved overflow on page {page_num}")

            except Exception as e:
                print(f"  Layout error for block: {str(e)[:100]}")
                try:
                    fallback_rect = fitz.Rect(x0, y0, x1, y1 + 60)
                    page.insert_textbox(
                        fallback_rect, block["text"],
                        fontsize=11, fontname="helv", color=(0, 0, 0),
                    )
                except Exception:
                    pass

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


def reconstruct_document(blocks, output_file, original_file=None, original_ext=None):
    """Write translated blocks to the appropriate output format."""
    ext = os.path.splitext(output_file)[1].lower()

    if ext == ".docx":
        write_docx(blocks, output_file, original_file)
    elif ext == ".pdf" and original_file:
        write_pdf_preserved(blocks, original_file, output_file)
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