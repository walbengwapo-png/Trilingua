# -*- coding: utf-8 -*-
"""
Document text extractor.

Responsible for reading various document formats and extracting
text blocks with metadata. Contains NO translation logic.

Reused from document_translator_v3.py with minimal changes.
"""

import os
import re
import csv


# ── Format Dispatcher ─────────────────────────────────────────────────────────

def analyze_document(file_path, pdf_column_mode="auto"):
    """Route the file to the correct reader based on its extension."""
    ext = os.path.splitext(file_path)[1].lower()
    reader = READERS.get(ext)
    if reader is None:
        supported = ", ".join(READERS.keys())
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {supported}")
    print(f"  [FILE] Detected format: {ext}")
    if ext == ".pdf":
        return reader(file_path, column_mode=pdf_column_mode), ext
    return reader(file_path), ext


# ── DOCX Reader ───────────────────────────────────────────────────────────────

def read_docx(file_path):
    """Read paragraphs, tables, headers, footers, and text boxes from a .docx file with style metadata."""
    from docx import Document
    from docx.oxml.ns import qn
    doc = Document(file_path)
    blocks = []

    def _extract_style_info(para, default_type="paragraph"):
        """Extract style metadata from a paragraph."""
        text = para.text.strip()
        if not text:
            return None
        font_color = None
        for run in para.runs:
            try:
                rgb = run.font.color.rgb
                if rgb is not None:
                    font_color = rgb
                    break
            except Exception:
                pass

        style_info = {
            "bold":        para.runs[0].bold if para.runs else False,
            "font_size":   para.runs[0].font.size if para.runs else None,
            "style_name":  para.style.name if para.style else None,
            "alignment":   para.alignment,
            "space_before": para.paragraph_format.space_before,
            "space_after":  para.paragraph_format.space_after,
            "font_color":  font_color,
        }
        return {"type": default_type, "text": text, "style": style_info}

    # ── Main body paragraphs ────────────────────────────────────────────────
    for para in doc.paragraphs:
        block = _extract_style_info(para, "paragraph")
        if block:
            blocks.append(block)

    # ── Headers and footers from all sections ────────────────────────────────
    for section in doc.sections:
        # Header
        header = section.header
        if header and not header.is_linked_to_previous:
            for para in header.paragraphs:
                block = _extract_style_info(para, "header")
                if block:
                    blocks.append(block)
        # Footer
        footer = section.footer
        if footer and not footer.is_linked_to_previous:
            for para in footer.paragraphs:
                block = _extract_style_info(para, "footer")
                if block:
                    blocks.append(block)

    # ── Text boxes (w:txbxContent inside the document body) ─────────────────
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for txbx in doc.element.body.iter(qn("w:txbxContent")):
        for p_elem in txbx.iter(qn("w:p")):
            texts = []
            for t_elem in p_elem.iter(qn("w:t")):
                if t_elem.text:
                    texts.append(t_elem.text)
            text = "".join(texts).strip()
            if text:
                blocks.append({
                    "type": "text_box",
                    "text": text,
                    "style": {},
                })

    # ── Table blocks ────────────────────────────────────────────────────────
    for table_index, table in enumerate(doc.tables):
        for row_idx, row in enumerate(table.rows):
            for col_idx, cell in enumerate(row.cells):
                col_span = 1
                if col_idx + 1 < len(row.cells):
                    if cell._tc is row.cells[col_idx + 1]._tc:
                        col_span = 0
                        for c in range(col_idx, len(row.cells)):
                            if row.cells[c]._tc is cell._tc:
                                col_span += 1
                            else:
                                break

                row_span = 1
                if row_idx + 1 < len(table.rows):
                    next_row = table.rows[row_idx + 1]
                    if col_idx < len(next_row.cells) and cell._tc is next_row.cells[col_idx]._tc:
                        row_span = 0
                        for r in range(row_idx, len(table.rows)):
                            if col_idx < len(table.rows[r].cells) and table.rows[r].cells[col_idx]._tc is cell._tc:
                                row_span += 1
                            else:
                                break

                cell_text = cell.text.strip()
                if not cell_text:
                    continue

                cell_bold = None
                cell_font_size = None
                for para in cell.paragraphs:
                    for run in para.runs:
                        if cell_bold is None and run.bold is not None:
                            cell_bold = run.bold
                        if cell_font_size is None and run.font.size is not None:
                            cell_font_size = run.font.size
                        if cell_bold is not None and cell_font_size is not None:
                            break
                    if cell_bold is not None and cell_font_size is not None:
                        break

                blocks.append({
                    "type":        "table_cell",
                    "text":        cell_text,
                    "table_index": table_index,
                    "row":         row_idx,
                    "col":         col_idx,
                    "col_span":    col_span,
                    "row_span":    row_span,
                    "style": {
                        "bold":      cell_bold,
                        "font_size": cell_font_size,
                    },
                })

    return blocks


# ── PDF Reader ────────────────────────────────────────────────────────────────

# Base-14 built-in abbreviations → (family, bold, italic)
_FONT_BASE14 = {
    "helv": ("helv", False, False), "helvb": ("helv", True, False),
    "helvi": ("helv", False, True), "helbo": ("helv", True, True),
    "helvbo": ("helv", True, True),
    "tiro": ("tiro", False, False), "tirob": ("tiro", True, False),
    "tiroi": ("tiro", False, True), "tirobi": ("tiro", True, True),
    "cour": ("cour", False, False), "courb": ("cour", True, False),
    "couri": ("cour", False, True), "coubi": ("cour", True, True),
}

_FONT_MONO_KEYWORDS = ("courier", "consolas", "mono", "monospace", "andale mono",
                       "source code", "cascadia", "fira code", "jetbrains")
_FONT_SERIF_KEYWORDS = ("times", "georgia", "roman", "garamond", "palatino",
                        "bookman", "caslon", "baskerville", "hoefler", "goudy")
_FONT_SANS_KEYWORDS = ("arial", "helvetica", "sans", "calibri", "segoe", "tahoma",
                       "verdana", "futura", "gill", "century gothic", "trebuchet",
                       "candara", "corbel", "open sans", "lucida", "franklin gothic",
                       "myriad", "noto sans", "roboto", "ubuntu", "dejavu sans")


def _clean_font_name(font_name):
    """Return the subset-stripped font name (``baaaaa+Tahoma`` → ``Tahoma``)."""
    if not font_name:
        return ""
    if "+" in font_name:
        return font_name.split("+", 1)[1]
    return font_name


def _normalize_font_name(font_name, flags=0):
    """Normalise a PDF font name to ``(family, bold, italic)``.

    Strips subset prefixes (``baaaaa+Tahoma`` → ``Tahoma``), resolves Base-14
    abbreviations (``helvb`` → ``("helv", True, False)``), and derives bold/italic
    from either the name itself or the span flags. This prevents downstream font
    resolution from hitting unsupported names like ``baaaaa+tahoma`` or ``helvb``.
    """
    if not font_name:
        return "helv", False, False
    name = font_name
    if "+" in name:
        name = name.split("+", 1)[1]
    lower = name.lower()

    if lower in _FONT_BASE14:
        return _FONT_BASE14[lower]

    bold = bool(flags & (2 ** 4))
    italic = bool(flags & (2 ** 1))
    if any(k in lower for k in ("bold", "heavy", "black", "semibold", "demi")):
        bold = True
    if any(k in lower for k in ("italic", "oblique")):
        italic = True

    if any(k in lower for k in _FONT_MONO_KEYWORDS):
        family = "cour"
    elif any(k in lower for k in _FONT_SERIF_KEYWORDS):
        family = "tiro"
    else:
        family = "helv"
    return family, bold, italic


def _collect_page_links(page):
    """Return the page's link annotations as plain dicts with rect arrays."""
    links = []
    for lnk in page.get_links():
        rect = lnk.get("from")
        if rect is None:
            continue
        links.append({
            "kind": lnk.get("kind", -1),
            "rect": [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)],
            "uri": lnk.get("uri", "") or "",
            "page": lnk.get("page"),
            "to": lnk.get("to"),
        })
    return links


def _links_hit(link, bbox):
    """True if a link rect overlaps *bbox*."""
    lx0, ly0, lx1, ly1 = link["rect"]
    x0, y0, x1, y1 = bbox
    return not (lx1 <= x0 or lx0 >= x1 or ly1 <= y0 or ly0 >= y1)


def _is_garbage_block(text, bbox, page_width, page_height):
    """Return True if a text block should be skipped."""
    stripped = text.strip()
    if re.fullmatch(r'\d+[\s.,/]*\d*', stripped):
        return True
    if stripped.lower().startswith('http') or stripped.lower().startswith('www'):
        return True
    words = [w for w in stripped.split() if re.search(r'[a-zA-Z\u0080-\uFFFF]', w)]
    if len(words) < 1:
        return True
    # Only drop very short blocks (≤3 words) very near page edges (top/bottom 1%)
    # Reduced from 2% to 1% to preserve more content (page numbers, labels, etc.)
    if len(words) <= 3 and page_height > 0 and len(bbox) >= 4:
        y0 = bbox[1]
        y1 = bbox[3]
        margin = page_height * 0.01
        if y0 < margin or y1 > (page_height - margin):
            return True
    return False


def _detect_block_alignment(bbox, page_width, page_height):
    """Detect text alignment from bounding box position.

    Returns 'left', 'center', 'right', or 'justify'.
    """
    x0, y0, x1, y1 = bbox
    block_width = x1 - x0
    left_margin = x0
    right_margin = page_width - x1

    if block_width > page_width * 0.05 and right_margin < page_width * 0.05 and left_margin > page_width * 0.10:
        return "right"

    if block_width < page_width * 0.85 and abs(left_margin - right_margin) < page_width * 0.05:
        return "center"

    if block_width > page_width * 0.90:
        return "justify"

    return "left"


def detect_columns(blocks, page_width):
    """Detect 1-3 columns using gap analysis, return reading order."""
    if not blocks:
        return []

    gap_threshold = 0.10 * page_width
    full_width_threshold = 0.90 * page_width

    full_width = []
    columnar = []
    for b in blocks:
        x0, y0, x1, y1 = b["position"]
        block_width = x1 - x0
        if block_width >= full_width_threshold:
            full_width.append(b)
        else:
            columnar.append(b)

    full_width.sort(key=lambda b: b["position"][1])

    if not columnar:
        return full_width

    x_sorted = sorted(columnar, key=lambda b: b["position"][0])
    gap_positions = []
    for i in range(len(x_sorted) - 1):
        right_edge = x_sorted[i]["position"][2]
        left_edge = x_sorted[i + 1]["position"][0]
        gap = left_edge - right_edge
        if gap >= gap_threshold:
            boundary = (right_edge + left_edge) / 2.0
            if not gap_positions or (boundary - gap_positions[-1]) > gap_threshold:
                gap_positions.append(boundary)
            if len(gap_positions) == 2:
                break

    if not gap_positions:
        columns = [columnar]
    elif len(gap_positions) == 1:
        boundary = gap_positions[0]
        col0 = [b for b in columnar if b["position"][2] <= boundary or
                (b["position"][0] + b["position"][2]) / 2 < boundary]
        col1 = [b for b in columnar if b not in col0]
        columns = [col0, col1]
    else:
        b0, b1 = gap_positions[0], gap_positions[1]
        col0 = [b for b in columnar if (b["position"][0] + b["position"][2]) / 2 < b0]
        col2 = [b for b in columnar if (b["position"][0] + b["position"][2]) / 2 >= b1]
        col1 = [b for b in columnar if b not in col0 and b not in col2]
        columns = [col0, col1, col2]

    if any(len(col) < 2 for col in columns):
        columns = [columnar]

    for col in columns:
        col.sort(key=lambda b: b["position"][1])

    columnar_ordered = []
    for col in columns:
        columnar_ordered.extend(col)

    result = []
    fw_idx = 0
    for block in columnar_ordered:
        block_y = block["position"][1]
        while fw_idx < len(full_width) and full_width[fw_idx]["position"][1] <= block_y:
            result.append(full_width[fw_idx])
            fw_idx += 1
        result.append(block)
    while fw_idx < len(full_width):
        result.append(full_width[fw_idx])
        fw_idx += 1

    if len(result) < len(blocks) * 0.5:
        print("  [PDF] Column detection dropped >50% of blocks — falling back to single column mode")
        fallback = []
        for col in columns:
            col.sort(key=lambda b: b["position"][1])
            fallback.extend(col)
        result_texts = {b["text"][:30] for b in fallback}
        for b in blocks:
            if b["text"][:30] not in result_texts:
                fallback.append(b)
        fallback.sort(key=lambda b: (b["page"], b["position"][1]))
        return fallback

    return result


def read_pdf(file_path, column_mode="auto"):
    """
    Read text blocks from a PDF with column detection.
    Uses TWO extraction methods and merges them for completeness.
    """
    import fitz
    blocks = []
    doc = fitz.open(file_path)

    for page_num in range(len(doc)):
        page = doc[page_num]
        pw = page.rect.width
        ph = page.rect.height

        # ── Method 1: dict mode (rich styles) ────────────────────────────────
        page_dict = page.get_text(
            "dict",
            flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES
        )

        page_links = _collect_page_links(page)

        raw_blocks_dict = []
        for rb in page_dict.get("blocks", []):
            if rb.get("type") != 0:
                continue
            lines = rb.get("lines", [])
            if not lines:
                continue

            parts = []
            line_records = []
            dom_size = 11.0
            dom_color = 0
            dom_bold = False
            dom_italic = False
            dom_font = "helv"
            dom_font_orig = ""

            for line in lines:
                lt = ""
                line_font = "helv"
                line_font_orig = ""
                line_size = 11.0
                line_color = 0
                line_bold = False
                line_italic = False
                baseline = None
                line_x0 = 0.0
                line_text_x1 = 0.0
                line_runs = []
                for span in line.get("spans", []):
                    st = span.get("text", "")
                    lt += st
                    if not st.strip():
                        continue
                    span_size = span.get("size", 11.0)
                    span_color = span.get("color", 0)
                    flags = span.get("flags", 0)
                    span_font = span.get("font", "")
                    if not line_font_orig and span_font:
                        line_font_orig = _clean_font_name(span_font)
                    if not dom_font_orig and span_font:
                        dom_font_orig = _clean_font_name(span_font)
                    fam, sp_bold, sp_italic = _normalize_font_name(span_font, flags)
                    line_font = fam
                    line_size = span_size
                    line_color = span_color
                    line_bold = line_bold or sp_bold
                    line_italic = line_italic or sp_italic
                    if baseline is None:
                        origin = span.get("origin")
                        if origin is not None:
                            baseline = float(origin[1])
                            line_x0 = float(origin[0])
                    span_bbox = span.get("bbox")
                    if span_bbox:
                        line_text_x1 = float(span_bbox[2])
                    dom_size = span_size
                    dom_color = span_color
                    dom_bold = dom_bold or sp_bold
                    dom_italic = dom_italic or sp_italic
                    dom_font = fam
                    line_runs.append({
                        "text": st,
                        "font": fam,
                        "font_original": _clean_font_name(span_font) or fam,
                        "size": max(6.0, min(float(span_size or 11.0), 72.0)),
                        "color": span_color,
                        "bold": sp_bold,
                        "italic": sp_italic,
                    })
                if lt.strip():
                    parts.append(lt.strip())
                    line_bbox = [float(v) for v in line.get("bbox", [0, 0, 0, 0])]
                    if baseline is None:
                        baseline = line_bbox[3]
                        line_x0 = line_bbox[0]
                        line_text_x1 = line_bbox[2]
                    if not line_runs:
                        line_runs = [{
                            "text": lt.strip(),
                            "font": line_font,
                            "font_original": line_font_orig or line_font,
                            "size": max(6.0, min(float(line_size or 11.0), 72.0)),
                            "color": line_color,
                            "bold": line_bold,
                            "italic": line_italic,
                        }]
                    line_records.append({
                        "text": lt.strip(),
                        "bbox": line_bbox,
                        "baseline": round(baseline, 2),
                        "x0": round(line_x0, 2),
                        "text_x1": round(line_text_x1, 2),
                        "font": line_font,
                        "font_original": line_font_orig or line_font,
                        "size": max(6.0, min(float(line_size or 11.0), 72.0)),
                        "color": line_color,
                        "bold": line_bold,
                        "italic": line_italic,
                        "runs": line_runs,
                        "links": [l for l in page_links if _links_hit(l, line_bbox)],
                    })

            block_text = " ".join(parts).strip()
            if not block_text:
                continue

            bbox = list(rb["bbox"])
            if _is_garbage_block(block_text, bbox, pw, ph):
                continue

            dom_size = max(6.0, min(float(dom_size or 11.0), 72.0))

            raw_blocks_dict.append({
                "type":     "paragraph",
                "text":     block_text,
                "position": bbox,
                "page":     page_num,
                "alignment": _detect_block_alignment(bbox, pw, ph),
                "style":    {"font_size": dom_size, "font": dom_font,
                             "font_original": dom_font_orig or dom_font,
                             "color": dom_color, "bold": dom_bold,
                             "italic": dom_italic},
                "lines":    line_records,
                "links":    [l for l in page_links if _links_hit(l, bbox)],
            })

        # ── Method 2: blocks mode (catches text dict mode misses) ────────────
        raw_blocks_blocks = []
        text_blocks = page.get_text("blocks", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for tb in text_blocks:
            if len(tb) < 6:
                continue
            x0, y0, x1, y1 = tb[0], tb[1], tb[2], tb[3]
            text = tb[4].strip() if tb[4] else ""
            if not text:
                continue
            bbox = [x0, y0, x1, y1]
            if _is_garbage_block(text, bbox, pw, ph):
                continue
            raw_blocks_blocks.append({
                "type":     "paragraph",
                "text":     text,
                "position": bbox,
                "page":     page_num,
            })

        # ── Merge: keep dict blocks (with style), add blocks-mode-only text ──
        def _rect(vals):
            return [float(v) for v in vals]

        def _area(bb):
            return max(0.0, bb[2] - bb[0]) * max(0.0, bb[3] - bb[1])

        def _intersects_much(a, b):
            ax0, ay0, ax1, ay1 = a
            bx0, by0, bx1, by1 = b
            ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
            iy = max(0.0, min(ay1, by1) - max(ay0, by0))
            inter = ix * iy
            if inter <= 0.0:
                return False
            smaller = min(_area(a), _area(b))
            return smaller > 0.0 and inter > 0.30 * smaller

        dict_rects = [_rect(b["position"]) for b in raw_blocks_dict]

        merged = list(raw_blocks_dict)
        for b in raw_blocks_blocks:
            bb = _rect(b["position"])
            if any(_intersects_much(bb, dr) for dr in dict_rects):
                continue
            text_key = (b["text"][:40].strip().lower(), round(b["position"][1], 0))
            if text_key not in dict_text_keys:
                block_links = [l for l in page_links if _links_hit(l, b["position"])]
                merged.append({
                    "type":     "paragraph",
                    "text":     b["text"],
                    "position": b["position"],
                    "page":     page_num,
                    "style":    {"font_size": 11, "font": "helv", "color": 0, "bold": False},
                    "lines":    [{
                        "text":     b["text"],
                        "bbox":     b["position"],
                        "baseline": round(b["position"][3], 2),
                        "x0":       round(b["position"][0], 2),
                        "text_x1":  round(b["position"][2], 2),
                        "font":     "helv",
                        "font_original": "helv",
                        "size":     11.0,
                        "color":    0,
                        "bold":     False,
                        "italic":   False,
                        "runs":     [{
                            "text":     b["text"],
                            "font":     "helv",
                            "font_original": "helv",
                            "size":     11.0,
                            "color":    0,
                            "bold":     False,
                            "italic":   False,
                        }],
                        "links":    block_links,
                    }],
                    "links":    block_links,
                })

        merged.sort(key=lambda b: b["position"][1])

        # ── Apply column_mode to select/order blocks ─────────────────────────
        match column_mode:
            case "single":
                selected = sorted(merged, key=lambda b: b["position"][1])
            case "left":
                selected = sorted(
                    [b for b in merged if (b["position"][0] + b["position"][2]) / 2 < pw / 2],
                    key=lambda b: b["position"][1],
                )
            case "right":
                selected = sorted(
                    [b for b in merged if (b["position"][0] + b["position"][2]) / 2 >= pw / 2],
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

        blocks.extend(selected)

    page_count = len(doc)
    doc.close()
    print(f"  [PDF] Extracted {len(blocks)} block(s) from {page_count} page(s)")
    return blocks


# ── TXT Reader ────────────────────────────────────────────────────────────────

def read_txt(file_path):
    """Read plain text file."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', raw) if p.strip()]
    if not paragraphs:
        paragraphs = [l.strip() for l in raw.splitlines() if l.strip()]
    return [{"type": "paragraph", "text": p, "style": {}} for p in paragraphs
            if len(p.split()) >= 1]


# ── Markdown Reader ───────────────────────────────────────────────────────────

def read_md(file_path):
    """Read Markdown file, preserving structure markers for translation."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    blocks = []
    in_code_block = False
    code_block_lines = []

    for line in raw.splitlines():
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                in_code_block = False
                blocks.append({"type": "code", "text": "\n".join(code_block_lines), "style": {}})
                code_block_lines = []
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_block_lines.append(line)
            continue

        if not stripped:
            continue

        heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading_match:
            blocks.append({"type": "header", "text": stripped, "style": {}})
            continue

        if stripped.startswith(">"):
            blocks.append({"type": "paragraph", "text": stripped, "style": {}})
            continue

        list_match = re.match(r'^(\s*[-*+]|\s*\d+\.)\s+(.+)$', stripped)
        if list_match:
            blocks.append({"type": "list_item", "text": stripped, "style": {}})
            continue

        blocks.append({"type": "paragraph", "text": stripped, "style": {}})

    return blocks if blocks else [{"type": "paragraph", "text": "", "style": {}}]


# ── RTF Reader ────────────────────────────────────────────────────────────────

def read_rtf(file_path):
    """Read RTF file with proper paragraph detection."""
    from striprtf.striprtf import rtf_to_text
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    plain = rtf_to_text(raw)
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', plain) if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in plain.splitlines() if p.strip()]
    return [{"type": "paragraph", "text": p, "style": {}} for p in paragraphs
            if len(p.split()) >= 1]


# ── ODT Reader ────────────────────────────────────────────────────────────────

def read_odt(file_path):
    """Read ODT file including paragraphs, headings, and table cells."""
    from odf.opendocument import load as odf_load
    from odf.text import P, H
    from odf.table import Table, TableRow, TableCell
    from odf import teletype
    doc = odf_load(file_path)
    blocks = []

    for elem in doc.getElementsByType(P) + doc.getElementsByType(H):
        text = teletype.extractText(elem).strip()
        if text and len(text.split()) >= 1:
            block_type = "header" if isinstance(elem, H) else "paragraph"
            blocks.append({"type": block_type, "text": text, "style": {}})

    for table in doc.getElementsByType(Table):
        for row in table.getElementsByType(TableRow):
            for cell in row.getElementsByType(TableCell):
                cell_text_parts = []
                for p in cell.getElementsByType(P):
                    t = teletype.extractText(p).strip()
                    if t:
                        cell_text_parts.append(t)
                cell_text = " ".join(cell_text_parts).strip()
                if cell_text and len(cell_text.split()) >= 1:
                    blocks.append({"type": "table_cell", "text": cell_text, "style": {}})

    return blocks if blocks else [{"type": "paragraph", "text": "", "style": {}}]


# ── CSV Reader ────────────────────────────────────────────────────────────────

def read_csv(file_path):
    """Read CSV file."""
    rows = []
    with open(file_path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(row)
    return {"type": "csv", "data": rows}


# ── PPTX Reader ───────────────────────────────────────────────────────────────

def read_pptx(file_path):
    """Read text from PowerPoint slides."""
    from pptx import Presentation
    prs = Presentation(file_path)
    blocks = []
    block_id = 0

    for slide_idx, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para_idx, para in enumerate(shape.text_frame.paragraphs):
                text = para.text.strip()
                if text and len(text.split()) >= 1:
                    bold = None
                    italic = None
                    font_size = None
                    for run in para.runs:
                        if bold is None and run.bold is not None:
                            bold = run.bold
                        if italic is None and run.font.italic is not None:
                            italic = run.font.italic
                        if font_size is None and run.font.size is not None:
                            font_size = run.font.size
                        if bold is not None and italic is not None and font_size is not None:
                            break

                    blocks.append({
                        "type":      "paragraph",
                        "text":      text,
                        "slide":     slide_idx,
                        "shape_id":  shape.shape_id,
                        "para_idx":  para_idx,
                        "style": {
                            "bold":      bold,
                            "italic":    italic,
                            "font_size": font_size,
                        },
                    })
                    block_id += 1

    return blocks


# ── XLSX Reader ───────────────────────────────────────────────────────────────

def read_xlsx(file_path):
    """Read text from Excel cells."""
    from openpyxl import load_workbook
    wb = load_workbook(file_path, data_only=True)
    blocks = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        for row in ws.iter_rows():
            for cell in row:
                if cell.value and isinstance(cell.value, str) and len(cell.value.split()) >= 1:
                    blocks.append({
                        "type":  "cell",
                        "text":  cell.value,
                        "sheet": sheet_name,
                        "row":   cell.row,
                        "col":   cell.column,
                    })

    wb.close()
    return blocks


# ── Reader Registry ───────────────────────────────────────────────────────────

READERS = {
    ".docx": read_docx,
    ".pdf":  read_pdf,
    ".txt":  read_txt,
    ".md":   read_md,
    ".rtf":  read_rtf,
    ".odt":  read_odt,
    ".csv":  read_csv,
    ".pptx": read_pptx,
    ".xlsx": read_xlsx,
}