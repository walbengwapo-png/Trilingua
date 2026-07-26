# -*- coding: utf-8 -*-
"""Document Translator v4 — Mistral AI Powered
=============================================
Replaces the NLLB-200 model with Mistral AI API for:
  - 5-10x faster translation
  - Better translation quality
  - No GPU required
  - No 2.5GB model download

Key improvements over v3:
  - Mistral AI API as the sole translation engine (NLLB removed)
  - Template-based DOCX writer (modifies original in-place → perfect layout)
  - PPTX support (read/write with python-pptx)
  - XLSX support (read/write with openpyxl)
  - Rate limiting and retry logic for API calls
  - Progress reporting via cache for frontend polling

Anti-hallucination features:
  - System message with strict constraints (no explanations, no additions)
  - Hallucination detection: explanatory phrases, verbosity, sentence inflation
  - Retry on hallucination with exponential backoff
  - Cleanup of explanatory prefixes/suffixes on final attempt
  - Graceful degradation (return best-effort translation rather than crash)
"""

import os
import re
import csv
import io
import json
import math
import time
import requests
from pathlib import Path

# ── Mistral AI Configuration ──────────────────────────────────────────────────
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"


def _get_mistral_api_key() -> str:
    """Get Mistral API key from environment (checked at runtime, not import time)."""
    key = os.environ.get("MISTRAL_API_KEY", "")
    if not key:
        raise RuntimeError(
            "MISTRAL_API_KEY environment variable is not set. "
            "Set it in your .env file or export it before starting the server."
        )
    return key


def _get_mistral_model() -> str:
    """Get Mistral model name from environment or use default."""
    return os.environ.get("MISTRAL_MODEL", "mistral-small-latest")

def _sanitize_translation(translated_text, original_text):
    """
    Clean up a translated string by removing leaked context delimiters,
    stray markers, and detecting hallucinated repetition.
    
    This is a safety net for edge cases where Mistral may output
    fragments of previous context or repeated phrases.
    """
    # 1. Strip leaked `|||` delimiters (from old Context_Buffer usage or model leakage)
    cleaned = re.sub(r'\s*\|\|\|\s*', ' ', translated_text)
    
    # 2. Strip stray "[Context:" markers if any leak through
    cleaned = re.sub(r'\[Context:[^\]]*\]', '', cleaned)
    
    # 3. Collapse repeated duplicate sentences (hallucination pattern)
    #    e.g. "A. A. A. B." → "A. B."
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    if len(sentences) >= 3:
        unique_sentences = []
        for s in sentences:
            s_norm = s.strip().lower()
            if not unique_sentences or s_norm != unique_sentences[-1].lower():
                unique_sentences.append(s.strip())
        if len(unique_sentences) < len(sentences):
            cleaned = ' '.join(unique_sentences)
    
    # 4. Adaptive hallucination threshold based on source text length
    #    Short text (headings, labels) naturally expands when translated
    #    Long text that expands >5x is likely hallucinated repetition
    orig_words = len(original_text.split())
    clean_words = len(cleaned.split())
    if orig_words > 0:
        if orig_words <= 3:
            threshold = 25   # 1-3 word headings expand significantly in Cebuano/Filipino
        elif orig_words <= 15:
            threshold = 10   # Short phrases
        else:
            threshold = 5    # Long text - true hallucination risk
        
        if clean_words > orig_words * threshold:
            print(f"  ⚠️  Hallucinated repetition detected ({clean_words} vs {orig_words} words, ratio={clean_words/orig_words:.1f}x > {threshold}x), retrying...")
            raise RuntimeError("Hallucinated repetition detected, will retry")
    
    # 5. Clean up excessive whitespace
    cleaned = re.sub(r' {2,}', ' ', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    
    return cleaned.strip()


# ── Language Codes (kept for compatibility with existing code) ─────────────────
LANGUAGES = {
    "English":  "eng_Latn",
    "Cebuano":  "ceb_Latn",
    "Filipino": "tgl_Latn",
}

# ── Mistral Translation ───────────────────────────────────────────────────────

def _detect_hallucination_in_output(translated_text, original_text):
    """
    Detect common hallucination patterns in translation output.
    
    Returns (is_hallucinated: bool, reason: str) tuple.
    Checks for:
      1. Explanatory prefixes/suffixes ("Here is...", "Translation:", etc.)
      2. Excessive verbosity (target >> source word count)
      3. Sentence count inflation (target has many more sentences than source)
      4. Proper name translation (heuristic: capitalized words changed)
    """
    if not translated_text or not original_text:
        return False, ""

    t = translated_text.strip()
    o = original_text.strip()

    # ── 1. Explanatory phrases ────────────────────────────────────────────────
    EXPLANATORY_PATTERNS = [
        r'^(here\s+(is|are|\'s)\s+the\s+translat)',
        r'^(the\s+translat)',
        r'^(translat(ion|ed)\s*:)',
        r'^(below\s+is)',
        r'^(in\s+\w+\s*,?\s*the\s+translat)',
        r'^(this\s+(is|translates?\s+to))',
        r'^(my\s+translat)',
        r'(here\s+is\s+the\s+translat)',
        r'(i\s+hope\s+this\s+helps)',
        r'(let\s+me\s+know\s+if)',
        r'(note\s*:)',
        r'(explanation\s*:)',
    ]
    for pat in EXPLANATORY_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return True, f"Explanatory phrase detected: {pat}"

    # ── 2. Verbosity check ────────────────────────────────────────────────────
    src_words = len(o.split())
    tgt_words = len(t.split())
    if src_words > 0:
        # For short text (≤5 words), allow up to 8x expansion (Cebuano/Filipino)
        # For medium text (6-30 words), allow up to 3x
        # For long text (>30 words), allow up to 2x
        if src_words <= 5:
            max_ratio = 8.0
        elif src_words <= 30:
            max_ratio = 3.0
        else:
            max_ratio = 2.0
        if tgt_words > src_words * max_ratio:
            return True, f"Excessive verbosity ({tgt_words}/{src_words} = {tgt_words/src_words:.1f}x > {max_ratio}x)"

    # ── 3. Sentence count inflation ───────────────────────────────────────────
    def _count_sentences(text):
        return len(re.findall(r'[.!?]+', text))

    src_sentences = _count_sentences(o)
    tgt_sentences = _count_sentences(t)
    if src_sentences > 0 and tgt_sentences > src_sentences * 3:
        return True, f"Sentence inflation ({tgt_sentences} vs {src_sentences} sentences)"
    # Also flag if source has no sentence-ending punctuation but target does (3+)
    if src_sentences == 0 and tgt_sentences >= 3:
        return True, f"Added sentence-ending punctuation ({tgt_sentences} found, source has none)"

    return False, ""


def _translate_with_mistral(text, source_lang, target_lang, block_type="paragraph"):
    """
    Translate a single text block using Mistral AI API.
    
    Features:
      - Retry up to 3 times with exponential backoff on rate limits / errors
      - Temperature 0.3 for natural but faithful translations
      - System message with strict anti-hallucination constraints
      - Hallucination detection with retry
      - 30-second timeout per request
      - Block type hint for structural context
    """
    api_key = _get_mistral_api_key()
    model = _get_mistral_model()

    # Map block type to human-readable description
    type_descriptions = {
        "paragraph":  "a body paragraph",
        "header":     "a document header",
        "footer":     "a document footer",
        "text_box":   "a text box",
        "table_cell": "a table cell",
        "heading":    "a document heading",
        "list_item":  "a list item",
    }
    type_desc = type_descriptions.get(block_type, block_type)

    # ── System message: strict translation constraints ────────────────────────
    system_msg = (
        "You are a professional document translator. "
        "Your ONLY task is to translate text. "
        "You must NEVER add, remove, or alter content beyond translation.\n\n"
        "STRICT RULES:\n"
        "1. Output ONLY the translated text — no labels, no explanations, no prefixes\n"
        "2. NEVER start output with 'Here is', 'Translation:', 'In ...:', or similar phrases\n"
        "3. The translation must contain EXACTLY the same information as the source — no extra sentences, no added context\n"
        "4. The translation must be roughly the same length as the source (±30% word count for long text)\n"
        "5. Keep ALL proper names (people, places, brands, organizations) unchanged\n"
        "6. Keep numbers, dates, URLs, email addresses, and code unchanged\n"
        "7. Preserve formatting: dashes, ellipsis, line breaks, CAPS, bullet points\n"
        "8. Preserve tone: children's book text stays simple and warm\n"
        "9. If source mixes languages, translate only the non-target language portions\n"
        "10. If unsure about a term, keep it unchanged rather than guessing"
    )

    # ── User message: examples + source text ──────────────────────────────────
    user_msg = f"Translate this {type_desc} from {source_lang} to {target_lang}.\n"

    # Add few-shot examples for Cebuano and Filipino
    if target_lang.lower() in ("cebuano", "filipino"):
        user_msg += f"\nExamples:\n"
        if target_lang.lower() == "cebuano":
            user_msg += (
                "  EN: I am going to the market. → CEB: Moadto ko sa merkado.\n"
                "  EN: What is your name? → CEB: Unsa imong pangalan?\n"
                "  EN: The cat sat on the mat. → CEB: Lingkod ang iring sa banig.\n"
                "  EN: 123 Main Street → CEB: 123 Main Street\n"
            )
        elif target_lang.lower() == "filipino":
            user_msg += (
                "  EN: I am going to the market. → FIL: Pupunta ako sa palengke.\n"
                "  EN: What is your name? → FIL: Ano ang pangalan mo?\n"
                "  EN: The cat sat on the mat. → FIL: Umupo ang pusa sa banig.\n"
                "  EN: 123 Main Street → FIL: 123 Main Street\n"
            )

    user_msg += f"\nSource text:\n{text}"

    # ── Token Budget Enforcement ──────────────────────────────────────────────
    total_chars = len(system_msg) + len(user_msg)
    estimated_input_tokens = total_chars // 4

    if estimated_input_tokens > 3500:
        print(f"[TOKEN BUDGET] estimated_input={estimated_input_tokens} source={text[:60]!r}")

    # Mistral Small 4 (mistral-small-latest) has 256K context window
    _CONTEXT_WINDOW = 256_000
    _MAX_OUTPUT = 8192
    available_for_output = _CONTEXT_WINDOW - estimated_input_tokens
    dynamic_max_tokens = max(1, min(available_for_output, _MAX_OUTPUT))

    for attempt in range(3):
        try:
            resp = requests.post(
                MISTRAL_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.3,
                    "max_tokens": dynamic_max_tokens,
                },
                timeout=30,
            )

            if resp.status_code == 429:
                # Rate limited — exponential backoff
                wait = 2 ** attempt
                print(f"  Warning: Rate limited, retrying in {wait}s...")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"].strip()
            
            # Remove any accidental markdown code block wrapping
            if result.startswith("```"):
                result = re.sub(r'^```[\w]*\n?', '', result)
                result = re.sub(r'\n?```$', '', result)
                result = result.strip()
            
            # ── Sanitize output ──────────────────────────────────────────────
            # Strip leaked delimiters and collapse repeated sentences
            try:
                result = _sanitize_translation(result, text)
            except RuntimeError as sanitize_err:
                if "Hallucinated repetition" in str(sanitize_err) and attempt < 2:
                    print(f"  ⚠️  Repeated hallucination detected, retrying ({attempt + 1}/3)...")
                    time.sleep(1)
                    continue
                elif "Hallucinated repetition" in str(sanitize_err):
                    print(f"  ⚠️  Using raw output after repetition hallucination")
                else:
                    print(f"  ⚠️  Sanitizer warning: {sanitize_err}")

            # ── Hallucination detection (new patterns) ───────────────────────
            is_hallucinated, reason = _detect_hallucination_in_output(result, text)
            if is_hallucinated:
                if attempt < 2:
                    print(f"  ⚠️  Hallucination detected ({reason}), retrying ({attempt + 1}/3)...")
                    time.sleep(1)
                    continue
                else:
                    # Last attempt: strip the offending prefix/suffix and return
                    print(f"  ⚠️  Hallucination persists after 3 attempts ({reason}), attempting cleanup...")
                    # Try to strip explanatory prefix/suffix
                    cleaned = re.sub(
                        r'^(here\s+(is|are|\'s)\s+the\s+translat\S*\s*[:\-]?\s*)',
                        '', result, flags=re.IGNORECASE
                    )
                    cleaned = re.sub(
                        r'^(translat\S*\s*[:\-]\s*)', '', cleaned, flags=re.IGNORECASE
                    )
                    cleaned = re.sub(
                        r'\s*\(?\s*let\s+me\s+know\s+if\s+.*$', '', cleaned, flags=re.IGNORECASE
                    )
                    cleaned = re.sub(
                        r'\s*\(?\s*i\s+hope\s+this\s+helps\s*\)?\s*$', '', cleaned, flags=re.IGNORECASE
                    )
                    cleaned = cleaned.strip()
                    if cleaned:
                        result = cleaned
                    # If cleanup still looks bad, use as-is (graceful degradation)

            # ── Output validation ────────────────────────────────────────────
            if not result:
                raise RuntimeError(f"Mistral returned empty translation for: {text[:60]}...")
            # Length ratio check — warn if suspiciously short or long
            src_len = len(text.split())
            tgt_len = len(result.split())
            if src_len > 0 and tgt_len > 0:
                ratio = tgt_len / src_len
                if ratio < 0.2:
                    print(f"  ⚠️  Translation ratio unusually LOW ({ratio:.2f}x): "
                          f"source={src_len} words → target={tgt_len} words")
                    print(f"       Source: {text[:80]}...")
                    print(f"       Target: {result[:80]}...")
                elif ratio > 8.0:
                    print(f"  ⚠️  Translation ratio unusually HIGH ({ratio:.2f}x): "
                          f"source={src_len} words → target={tgt_len} words")
                    print(f"       Source: {text[:80]}...")
                    print(f"       Target: {result[:80]}...")
            
            return result

        except requests.exceptions.Timeout:
            if attempt == 2:
                raise RuntimeError(f"Mistral API timed out after 3 attempts for text: {text[:50]}...")
            print(f"  Warning: Timeout, retrying ({attempt + 1}/3)...")
            time.sleep(1)

        except requests.exceptions.RequestException as e:
            if attempt == 2:
                raise RuntimeError(f"Mistral API error after 3 attempts: {e}")
            print(f"  Warning: API error: {e}, retrying ({attempt + 1}/3)...")
            time.sleep(1)

    # ── Emergency fallback ──────────────────────────────────────────────────
    # If we reach here after 3 retries (including sanitizer hallucinations),
    # return the raw result from the last successful API response.
    # This ensures a single bad block doesn't crash the entire document translation.
    try:
        if result and isinstance(result, str):
            print(f"  ⚠️  Using raw Mistral output after 3 failed sanitization attempts")
            return result
    except UnboundLocalError:
        pass
    
    raise RuntimeError("Mistral translation failed after 3 attempts.")


# ── File Readers ──────────────────────────────────────────────────────────────

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
    # These are not accessible via doc.paragraphs; we must walk the XML.
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for txbx in doc.element.body.iter(qn("w:txbxContent")):
        for p_elem in txbx.iter(qn("w:p")):
            # Build a temporary paragraph-like object to extract text
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
                # Detect column and row spans by comparing underlying XML elements
                col_span = 1
                # Check horizontal span: same _tc as next cell
                if col_idx + 1 < len(row.cells):
                    if cell._tc is row.cells[col_idx + 1]._tc:
                        # Count how many cells share this _tc horizontally
                        col_span = 0
                        for c in range(col_idx, len(row.cells)):
                            if row.cells[c]._tc is cell._tc:
                                col_span += 1
                            else:
                                break

                row_span = 1
                # Check vertical span: same _tc as cell in next row
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


def read_pdf(file_path, column_mode="auto"):
    """
    Read text blocks from a PDF with column detection.
    
    Uses TWO extraction methods and merges them:
      1. page.get_text("dict") — rich style info but may miss some text blocks
      2. page.get_text("blocks") — catches more text but has no style info
      
    Merging ensures no text is lost while preserving as much style info as possible.
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

        raw_blocks_dict = []
        for rb in page_dict.get("blocks", []):
            if rb.get("type") != 0:
                continue
            lines = rb.get("lines", [])
            if not lines:
                continue

            parts = []
            dom_size = 11.0
            dom_color = 0
            dom_bold = False
            dom_italic = False
            dom_font = "helv"

            for line in lines:
                lt = ""
                for span in line.get("spans", []):
                    st = span.get("text", "")
                    if st.strip():
                        lt += st
                        dom_size = span.get("size", dom_size)
                        dom_color = span.get("color", dom_color)
                        flags = span.get("flags", 0)
                        dom_bold = bool(flags & 2**4)
                        dom_italic = bool(flags & 2**1)
                        span_font = span.get("font", "")
                        if span_font:
                            dom_font = span_font
                if lt.strip():
                    parts.append(lt.strip())

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
                "style":    {"font_size": dom_size, "font": dom_font,
                             "color": dom_color, "bold": dom_bold,
                             "italic": dom_italic},
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
        # Build a set of normalized text keys from dict blocks for dedup
        dict_text_keys = set()
        for b in raw_blocks_dict:
            # Use first 40 chars of text + rounded y position as dedup key
            text_key = (b["text"][:40].strip().lower(), round(b["position"][1], 0))
            dict_text_keys.add(text_key)

        merged = list(raw_blocks_dict)  # start with all dict blocks (they have style)
        for b in raw_blocks_blocks:
            text_key = (b["text"][:40].strip().lower(), round(b["position"][1], 0))
            if text_key not in dict_text_keys:
                # This block was NOT captured by dict mode — add with default style
                merged.append({
                    "type":     "paragraph",
                    "text":     b["text"],
                    "position": b["position"],
                    "page":     page_num,
                    "style":    {"font_size": 11, "font": "helv", "color": 0, "bold": False},
                })

        # ── Sort merged blocks by page position (top-to-bottom) ─────────────
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


def _is_garbage_block(text, bbox, page_width, page_height):
    """Return True if a text block should be skipped."""
    stripped = text.strip()

    # Pure numeric content that's likely a page number or running number
    if re.fullmatch(r'\d+[\s.,/]*\d*', stripped):
        return True

    # Pure URLs (not useful to translate)
    if stripped.lower().startswith('http') or stripped.lower().startswith('www'):
        return True

    # No alphabetic/unicode words at all
    words = [w for w in stripped.split() if re.search(r'[a-zA-Z\u0080-\uFFFF]', w)]
    if len(words) < 1:
        return True

    # Position-based header/footer detection: blocks in top/bottom 4% of page
    # that are short (<=5 words) are likely page numbers or running headers
    if len(words) <= 5 and page_height > 0 and len(bbox) >= 4:
        y0 = bbox[1]
        y1 = bbox[3]
        margin = page_height * 0.04
        if y0 < margin or y1 > (page_height - margin):
            return True

    return False


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

    # Safety fallback: if column detection dropped more than 50% of blocks,
    # revert but preserve within-column y-order instead of flat-sorting everything
    if len(result) < len(blocks) * 0.5:
        print("  [PDF] Column detection dropped >50% of blocks — falling back to single column mode")
        # Preserve the column assignments we did have, just sort each column by y
        fallback = []
        for col in columns:
            col.sort(key=lambda b: b["position"][1])
            fallback.extend(col)
        # Add any blocks that were in full_width but not in result
        result_texts = {b["text"][:30] for b in fallback}
        for b in blocks:
            if b["text"][:30] not in result_texts:
                fallback.append(b)
        fallback.sort(key=lambda b: (b["page"], b["position"][1]))
        return fallback

    return result


def read_txt(file_path):
    """Read plain text file."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', raw) if p.strip()]
    if not paragraphs:
        paragraphs = [l.strip() for l in raw.splitlines() if l.strip()]
    return [{"type": "paragraph", "text": p, "style": {}} for p in paragraphs
            if len(p.split()) >= 1]


def read_md(file_path):
    """Read Markdown file, preserving structure markers for translation.

    Extracts paragraphs, headings, list items, and blockquotes as translatable
    blocks while preserving their Markdown syntax markers (e.g. '#', '>', '-').
    Code blocks (``` fenced) are preserved verbatim and NOT translated.
    """
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    blocks = []
    in_code_block = False
    code_block_lines = []

    for line in raw.splitlines():
        stripped = line.strip()

        # Fenced code blocks: preserve verbatim, do not translate
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

        # Headings: preserve the '#' markers
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading_match:
            blocks.append({"type": "header", "text": stripped, "style": {}})
            continue

        # Blockquotes: preserve the '>' marker
        if stripped.startswith(">"):
            blocks.append({"type": "paragraph", "text": stripped, "style": {}})
            continue

        # List items: preserve the marker
        list_match = re.match(r'^(\s*[-*+]|\s*\d+\.)\s+(.+)$', stripped)
        if list_match:
            blocks.append({"type": "list_item", "text": stripped, "style": {}})
            continue

        # Regular paragraph
        blocks.append({"type": "paragraph", "text": stripped, "style": {}})

    return blocks if blocks else [{"type": "paragraph", "text": "", "style": {}}]


def read_rtf(file_path):
    """Read RTF file with proper paragraph detection."""
    from striprtf.striprtf import rtf_to_text
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    plain = rtf_to_text(raw)
    # Split on paragraph breaks first (\par in RTF maps to double newlines),
    # then fall back to single newlines for soft breaks
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', plain) if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in plain.splitlines() if p.strip()]
    return [{"type": "paragraph", "text": p, "style": {}} for p in paragraphs
            if len(p.split()) >= 1]


def read_odt(file_path):
    """Read ODT file including paragraphs, headings, and table cells."""
    from odf.opendocument import load as odf_load
    from odf.text import P, H
    from odf.table import Table, TableRow, TableCell
    from odf import teletype
    doc = odf_load(file_path)
    blocks = []

    # Extract paragraphs and headings
    for elem in doc.getElementsByType(P) + doc.getElementsByType(H):
        text = teletype.extractText(elem).strip()
        if text and len(text.split()) >= 1:
            block_type = "header" if isinstance(elem, H) else "paragraph"
            blocks.append({"type": block_type, "text": text, "style": {}})

    # Extract table cells
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


def read_csv(file_path):
    """Read CSV file."""
    rows = []
    with open(file_path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(row)
    return {"type": "csv", "data": rows}


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
                    # Collect run-level formatting
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


# ── Format Dispatcher ─────────────────────────────────────────────────────────

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


# ── Translation Helpers ───────────────────────────────────────────────────────

def _translate_single(text, src_code, tgt_code, context_hint="", block_type="paragraph"):
    """
    Translate a single piece of text using Mistral AI.
    
    The src_code/tgt_code are NLLB-style codes (eng_Latn, ceb_Latn, tgl_Latn)
    kept for backward compatibility. We map them back to language names.
    block_type provides structural context (e.g. 'header', 'table_cell').
    """
    CODE_TO_LANG = {v: k for k, v in LANGUAGES.items()}
    source_lang = CODE_TO_LANG.get(src_code, src_code)
    target_lang = CODE_TO_LANG.get(tgt_code, tgt_code)

    # NOTE: Context hint is intentionally NOT prepended to the prompt.
    # Previous attempts to add context caused cascading hallucination where
    # Mistral would repeat the context text as part of its translation output.
    # Each block is translated independently for clean, isolated results.
    return _translate_with_mistral(text, source_lang, target_lang, block_type=block_type)


def batch_translate_blocks(blocks, source_lang, target_lang, batch_size=4,
                           context_window=1, glossary_store=None,
                           context_buffer=None, progress_callback=None):
    """
    Translate all blocks with context-aware batching.
    
    progress_callback: optional callable(completed, total) for frontend progress.
    """
    if not blocks:
        return []

    src_code = LANGUAGES[source_lang]
    tgt_code = LANGUAGES[target_lang]
    total = len(blocks)
    translated_blocks = []

    for i, block in enumerate(blocks):
        print(f"  Translating block {i+1}/{total}...", end="\r", flush=True)

        # Get context hint from buffer (once per block, not per chunk)
        hint = context_buffer.get_hint() if context_buffer is not None else ""

        # Split the block text into sentence-aligned chunks before API calls
        chunks = Chunk_Splitter().split(block["text"])
        translated_chunks = []
        for chunk in chunks:
            translated_chunk = _translate_single(
                chunk, src_code, tgt_code, context_hint=hint,
                block_type=block.get("type", "paragraph"),
            )
            translated_chunks.append(translated_chunk)
        translated_text = " ".join(translated_chunks)

        # Push rejoined result to context buffer (once per block, only on success)
        if context_buffer is not None:
            context_buffer.push(translated_text)

        # Apply glossary if provided
        if glossary_store is not None:
            translated_text = glossary_store.apply(translated_text)

        new_block = {
            "type":  block["type"],
            "text":  translated_text,
            "style": block.get("style", {}),
        }
        # Preserve position metadata for PDF
        if "position" in block:
            new_block["position"] = block["position"]
            new_block["page"] = block["page"]
            # Preserve original text for PDF expansion ratio calculation
            new_block["_original_text"] = block["text"]
        # Preserve slide/cell metadata for PPTX/XLSX
        if "slide" in block:
            new_block["slide"] = block["slide"]
            new_block["shape_id"] = block["shape_id"]
            new_block["para_idx"] = block["para_idx"]
        if "sheet" in block:
            new_block["sheet"] = block["sheet"]
            new_block["row"] = block["row"]
            new_block["col"] = block["col"]
        if "table_index" in block:
            new_block["table_index"] = block["table_index"]
            new_block["row"] = block["row"]
            new_block["col"] = block["col"]

        translated_blocks.append(new_block)

        # Report progress
        if progress_callback:
            progress_callback(i + 1, total)

    print(f"\n  [OK] Translation complete! ({total} blocks)")
    return translated_blocks


# ── Chunk Splitter ────────────────────────────────────────────────────────────

class BLEU_Reporter:
    """Computes BLEU scores between translated blocks and a reference file.

    Uses sacrebleu for BLEU computation.  Returns ``None`` (with a warning)
    when the reference file is missing, unreadable, or empty — never raises.
    """

    def compute(self, blocks, reference_file):
        """Compute BLEU score for *blocks* against *reference_file*.

        Parameters
        ----------
        blocks : list[dict]
            Translated blocks, each with a ``"text"`` key.
        reference_file : str | None
            Path to a plain-text reference file (one sentence per line).

        Returns
        -------
        float | None
            BLEU score in ``[0.0, 100.0]``, or ``None`` when scoring is not
            possible.
        """
        if reference_file is None:
            return None

        if not os.path.isfile(reference_file):
            print(f"  ⚠️  BLEU: reference file not found: {reference_file}")
            return None

        try:
            with open(reference_file, "r", encoding="utf-8") as f:
                ref_lines = [line.strip() for line in f if line.strip()]
        except OSError as e:
            print(f"  ⚠️  BLEU: cannot read reference file: {e}")
            return None

        if not ref_lines:
            print(f"  ⚠️  BLEU: reference file is empty: {reference_file}")
            return None

        hyp_texts = [b.get("text", "") for b in blocks if b.get("text", "").strip()]
        if not hyp_texts:
            print(f"  ⚠️  BLEU: no translated texts to score")
            return None

        # Align to the shorter of the two lists
        min_len = min(len(hyp_texts), len(ref_lines))
        if len(hyp_texts) != len(ref_lines):
            print(f"  ⚠️  BLEU: count mismatch (hyp={len(hyp_texts)} ref={len(ref_lines)}), aligning over {min_len} pairs")

        try:
            import sacrebleu
            refs = [ref_lines[:min_len]]
            hyps = hyp_texts[:min_len]
            bleu = sacrebleu.corpus_bleu(hyps, refs)
            return bleu.score
        except Exception as e:
            print(f"  ⚠️  BLEU: computation error: {e}")
            return None


class Chunk_Splitter:
    """Splits a long text block into translation-safe chunks at sentence boundaries.

    Uses a word-token model (one token = one whitespace-delimited word).
    Sentence boundaries are tokens that end with '.', '!', or '?'.
    """

    def split(
        self,
        text: str,
        max_tokens: int = 400,
        hard_cap: int = 600,
        min_tokens: int = 10,
    ) -> list:
        """Split *text* into chunks of at most *max_tokens* words, honouring
        sentence boundaries.

        Parameters
        ----------
        text:       The source text to split.
        max_tokens: Preferred maximum tokens (words) per chunk.
        hard_cap:   Absolute maximum tokens before giving up on splitting.
        min_tokens: Minimum tokens in a trailing chunk; smaller tails are merged
                    back into the previous chunk.

        Returns
        -------
        A list of strings whose concatenated words reproduce *text* exactly
        (round-trip property).
        """
        # Edge-case: empty or whitespace-only input.
        if not text or not text.strip():
            return [""]

        # Clamp max_tokens to at least 1 to avoid infinite loops.
        if max_tokens <= 0:
            max_tokens = 1

        tokens = text.split()

        # Step 1 — short-circuit: text already fits in one chunk.
        if len(tokens) <= max_tokens:
            return [text]

        # Steps 2-4 — find the best split boundary.
        # Collect candidate indices: tokens that end with '.', '!' or '?'
        # Preferred zone: [0, max_tokens)   → last candidate at or before max_tokens
        # Extended zone:  [max_tokens, hard_cap) → first candidate found
        best_boundary = None

        # Scan up to hard_cap (exclusive) to collect all candidates.
        scan_limit = min(hard_cap, len(tokens))

        # Pass 1: pick the LAST candidate within [0, max_tokens).
        for i in range(min(max_tokens, scan_limit)):
            if tokens[i].endswith(('.', '!', '?')):
                best_boundary = i  # keep updating → last candidate in window

        # Pass 2: if nothing found in preferred zone, take the FIRST candidate
        # in the extended zone [max_tokens, hard_cap).
        if best_boundary is None:
            for i in range(max_tokens, scan_limit):
                if tokens[i].endswith(('.', '!', '?')):
                    best_boundary = i
                    break  # first candidate wins

        # Step 5 — no candidate anywhere within hard_cap → return unsplit.
        if best_boundary is None:
            return [text]

        # Step 6 — split at the chosen boundary.
        first_tokens = tokens[:best_boundary + 1]
        remainder_tokens = tokens[best_boundary + 1:]

        # Step 7 — merge short tails back.
        if len(remainder_tokens) < min_tokens:
            return [text]

        # Step 8 — recurse on the remainder.
        first_chunk = " ".join(first_tokens)
        remainder_text = " ".join(remainder_tokens)
        rest_chunks = self.split(remainder_text, max_tokens, hard_cap, min_tokens)

        return [first_chunk] + rest_chunks


# ── Context Buffer ────────────────────────────────────────────────────────────

class Context_Buffer:
    """Sliding window of last N translated blocks for context hints."""

    def __init__(self, window_size: int = 2):
        from collections import deque
        self._buffer = deque(maxlen=window_size)

    def push(self, translated_text: str) -> None:
        self._buffer.append(translated_text)

    def get_hint(self) -> str:
        if not self._buffer:
            return ""
        return " ||| ".join(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()


# ── Glossary Store ────────────────────────────────────────────────────────────

class Glossary_Store:
    """Holds source→target term pairs and applies post-translation substitution."""

    def __init__(self, pairs: list | None = None):
        if pairs is None:
            pairs = []
        if len(pairs) > 1000:
            raise ValueError(f"Glossary_Store: too many term pairs ({len(pairs)}); maximum is 1000.")

        self._terms: list[tuple[str, str]] = []
        seen: dict[str, str] = {}

        for source, target in pairs:
            key = source.lower()
            if key in seen:
                raise ValueError(
                    f"Glossary_Store: duplicate source term '{source}' "
                    f"(already registered as '{seen[key]}')."
                )
            seen[key] = source
            self._terms.append((source, target))

        if self._terms:
            sorted_terms = sorted(self._terms, key=lambda p: len(p[0]), reverse=True)
            pattern = "|".join(
                r"\b" + re.escape(src) + r"\b" for src, _ in sorted_terms
            )
            self._regex = re.compile(pattern, re.IGNORECASE)
            self._lookup = {src.lower(): tgt for src, tgt in sorted_terms}
        else:
            self._regex = None
            self._lookup = {}

    def apply(self, text: str) -> str:
        if self._regex is None:
            return text

        def _replace(match: re.Match) -> str:
            original_token = match.group(0)
            target_term = self._lookup[original_token.lower()]
            return self._match_case(original_token, target_term)

        return self._regex.sub(_replace, text)

    @staticmethod
    def _match_case(original_token: str, target_term: str) -> str:
        if original_token.isupper():
            return target_term.upper()
        if original_token.istitle():
            return target_term.title()
        if original_token.islower():
            return target_term.lower()
        return target_term


# ── Font Mapper ───────────────────────────────────────────────────────────────

class Background_Sampler:
    """Samples the background colour of a PDF text block region.

    Uses the four corner pixels of the bbox to determine whether the
    background is a uniform colour.  Returns ``(r, g, b)`` floats in
    ``[0, 1]`` when uniform, or ``None`` when the background is
    non-uniform (mixed colours) or the bbox is degenerate.
    """

    @staticmethod
    def sample(page, bbox):
        """Sample background colour at the four corners of *bbox*.

        Parameters
        ----------
        page : fitz.Page
            The PDF page to sample.
        bbox : tuple[float, float, float, float]
            ``(x0, y0, x1, y1)`` bounding box in PDF points.

        Returns
        -------
        tuple[float, float, float] | None
            ``(r, g, b)`` in ``[0, 1]`` when all four corner pixels
            share the same colour, or ``None`` otherwise.
        """
        x0, y0, x1, y1 = bbox

        # Degenerate bbox → return None without raising
        if x0 >= x1 or y0 >= y1:
            return None

        pix = page.get_pixmap()

        # Map PDF coordinates to pixel coordinates
        pw = float(page.rect.x1 - page.rect.x0)
        ph = float(page.rect.y1 - page.rect.y0)
        if pw <= 0 or ph <= 0:
            return None
        px0 = max(0, min(pix.width - 1, int(x0 * pix.width / pw)))
        px1 = max(0, min(pix.width - 1, int(x1 * pix.width / pw)))
        py0 = max(0, min(pix.height - 1, int(y0 * pix.height / ph)))
        py1 = max(0, min(pix.height - 1, int(y1 * pix.height / ph)))

        corners = [
            pix.pixel(px0, py0),
            pix.pixel(px1, py0),
            pix.pixel(px0, py1),
            pix.pixel(px1, py1),
        ]

        # Check all four corners are identical
        first_r, first_g, first_b = corners[0]
        for r, g, b in corners[1:]:
            if r != first_r or g != first_g or b != first_b:
                return None

        return (first_r / 255.0, first_g / 255.0, first_b / 255.0)


class Font_Mapper:
    """Centralises PDF font-name resolution for ``write_pdf_preserved()``.

    Resolution priority (highest → lowest):

    1. ``font_name`` is ``None`` or empty → return ``"helv"`` with ⚠️ warning.
    2. ``font_name.lower()`` matches any entry in *embedded_fonts* lowercased
       → return ``font_name`` as-is (preserve caller's casing).
    3. ``font_name.lower()`` contains a monospace keyword → return ``"cour"``.
    4. ``font_name.lower()`` contains a serif keyword    → return ``"tiro"``.
    5. ``font_name.lower()`` contains a sans-serif keyword → return ``"helv"``.
    6. No match at all → return ``"helv"`` with ⚠️ warning.
    """

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
        # Priority 1 — None or empty
        if not font_name:
            print(f"⚠️ Font_Mapper: font_name is None or empty; falling back to 'helv'.")
            return "helv"

        lower = font_name.lower()

        # Priority 2 — embedded font (case-insensitive match)
        if any(lower == ef.lower() for ef in embedded_fonts):
            return font_name

        # Priority 3 — monospace keywords
        if any(kw in lower for kw in self._MONO_KEYWORDS):
            return "cour"

        # Priority 4 — serif keywords
        if any(kw in lower for kw in self._SERIF_KEYWORDS):
            return "tiro"

        # Priority 5 — sans-serif keywords
        if any(kw in lower for kw in self._SANS_KEYWORDS):
            return "helv"

        # Priority 6 — unknown font; warn and fall back
        print(f"⚠️ Font_Mapper: unknown font '{font_name}'; falling back to 'helv'.")
        return "helv"


class Style_Mapper:
    """Resolves a DOCX paragraph style name to a style available in the target document.

    Returns the style name unchanged when it is a non-empty string present in
    *available_styles*, and falls back to ``"Normal"`` in all other cases so
    that ``python-docx`` never raises a ``KeyError`` on a missing style.
    """

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


# ── In-Place Translation: DOCX, PPTX, XLSX ──────────────────────────────────

def _apply_translation_to_paragraph(para, translated_text, glossary_store):
    """
    Apply a translated string to a paragraph's runs, preserving per-run formatting.

    - No runs: add a new run with the translated text.
    - Single run: set run.text directly (all formatting attributes untouched).
    - Multiple runs: put the full translated text in the first run and clear
      subsequent runs.  This avoids splitting meaning across formatting boundaries
      (e.g. bold/italic would apply to the entire translation rather than being
      scrambled across arbitrary character positions).

    run.bold, run.italic, run.font.size, and run.font.color.rgb are NEVER
    assigned — only run.text is updated.
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

    # Multi-run: put full translation in first run, clear the rest
    runs[0].text = translated_text
    for run in runs[1:]:
        run.text = ""


def translate_docx_inplace(input_file, output_file, source_lang, target_lang,
                           glossary_store=None, progress_callback=None):
    """
    Translate a DOCX file by iterating its paragraphs and tables in-place.
    
    Unlike the old extract→translate→reconstruct pipeline, this function:
      - Opens the original document
      - Iterates EVERY paragraph in document order (preserving index correspondence)
      - Translates each paragraph's text via Mistral
      - Replaces text directly in the original paragraph (preserving all formatting)
      - Similarly iterates table cells by (table_idx, row, col)
      
    This guarantees perfect layout preservation because the document structure
    and paragraph indices are NEVER altered.
    """
    from docx import Document
    from docx.shared import RGBColor, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    src_code = LANGUAGES[source_lang]
    tgt_code = LANGUAGES[target_lang]

    doc = Document(input_file)
    total_paras = sum(1 for p in doc.paragraphs if p.text.strip())
    total_cells = sum(1 for t in doc.tables for r in t.rows for c in r.cells if c.text.strip())
    # Count text boxes for progress tracking
    from docx.oxml.ns import qn
    total_textboxes = 0
    for txbx in doc.element.body.iter(qn("w:txbxContent")):
        for p_elem in txbx.iter(qn("w:p")):
            texts = []
            for t_elem in p_elem.iter(qn("w:t")):
                if t_elem.text:
                    texts.append(t_elem.text)
            if "".join(texts).strip():
                total_textboxes += 1
    # Count headers and footers for progress tracking
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

    # ── Translate headers and footers in-place ─────────────────────────────
    for section in doc.sections:
        for para in section.header.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            print(f"  Translating header '{text[:40]}...' ({completed+1}/{total})", end="\r", flush=True)
            translated_text = _translate_single(text, src_code, tgt_code, block_type="header")
            _apply_translation_to_paragraph(para, translated_text, glossary_store)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

        for para in section.footer.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            print(f"  Translating footer '{text[:40]}...' ({completed+1}/{total})", end="\r", flush=True)
            translated_text = _translate_single(text, src_code, tgt_code, block_type="footer")
            _apply_translation_to_paragraph(para, translated_text, glossary_store)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    # ── Translate paragraphs in-place ────────────────────────────────────────
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        print(f"  Translating paragraph '{text[:40]}...' ({completed+1}/{total})", end="\r", flush=True)
        translated_text = _translate_single(text, src_code, tgt_code, block_type="paragraph")

        _apply_translation_to_paragraph(para, translated_text, glossary_store)

        completed += 1
        if progress_callback:
            progress_callback(completed, total)

    # ── Translate text boxes in-place ────────────────────────────────────────
    for txbx in doc.element.body.iter(qn("w:txbxContent")):
        for p_elem in txbx.iter(qn("w:p")):
            texts = []
            for t_elem in p_elem.iter(qn("w:t")):
                if t_elem.text:
                    texts.append(t_elem.text)
            combined = "".join(texts).strip()
            if not combined:
                continue

            print(f"  Translating text box '{combined[:40]}...' ({completed+1}/{total})", end="\r", flush=True)
            translated_text = _translate_single(combined, src_code, tgt_code, block_type="text_box")

            # Use python-docx Paragraph wrapper to preserve run formatting
            from docx.text.paragraph import Paragraph
            para_obj = Paragraph(p_elem, doc)
            _apply_translation_to_paragraph(para_obj, translated_text, glossary_store)

            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    # ── Translate table cells in-place ────────────────────────────────────────
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if not text:
                    continue

                print(f"  Translating cell '{text[:40]}...' ({completed+1}/{total})", end="\r", flush=True)
                translated_text = _translate_single(text, src_code, tgt_code, block_type="table_cell")

                if glossary_store is not None:
                    translated_text = glossary_store.apply(translated_text)

                # Translate ALL paragraphs in the cell, not just the first
                first_para = True
                for p in cell.paragraphs:
                    if first_para:
                        _apply_translation_to_paragraph(p, translated_text, None)
                        first_para = False
                    elif p.text.strip() or p.runs:
                        # Clear subsequent paragraphs since we merged into first
                        for run in p.runs:
                            run.text = ""

                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

    # ── Translate footnotes and endnotes ──────────────────────────────────
    try:
        from docx.oxml.ns import qn as _qn
        for note_type_tag in ("w:footnote", "w:endnote"):
            for note_elem in doc.element.body.iter(_qn(note_type_tag)):
                for p_elem in note_elem.iter(_qn("w:p")):
                    texts = []
                    for t_elem in p_elem.iter(_qn("w:t")):
                        if t_elem.text:
                            texts.append(t_elem.text)
                    combined = "".join(texts).strip()
                    if not combined:
                        continue
                    from docx.text.paragraph import Paragraph
                    para_obj = Paragraph(p_elem, doc)
                    print(f"  Translating note '{combined[:40]}...' ({completed+1}/{total})", end="\r", flush=True)
                    translated_text = _translate_single(combined, src_code, tgt_code, block_type="paragraph")
                    _apply_translation_to_paragraph(para_obj, translated_text, glossary_store)
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, total)
    except Exception:
        pass

    # ── Translate hyperlink text ──────────────────────────────────────────
    try:
        from docx.oxml.ns import qn as _qn
        for hyperlink in doc.element.body.iter(_qn("w:hyperlink")):
            texts = []
            for t_elem in hyperlink.iter(_qn("w:t")):
                if t_elem.text:
                    texts.append(t_elem.text)
            combined = "".join(texts).strip()
            if not combined:
                continue
            # Replace text in the first w:t element, clear the rest
            first = True
            for t_elem in hyperlink.iter(_qn("w:t")):
                if t_elem.text and t_elem.text.strip():
                    if first:
                        print(f"  Translating hyperlink '{combined[:40]}...' ({completed+1}/{total})", end="\r", flush=True)
                        translated_text = _translate_single(combined, src_code, tgt_code, block_type="paragraph")
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
    print(f"\n  [OK] DOCX saved with layout preservation ({completed} items translated)")


def translate_pptx_inplace(input_file, output_file, source_lang, target_lang,
                           glossary_store=None, progress_callback=None):
    """
    Translate a PPTX file by iterating slides/shapes/paragraphs in-place.
    Preserves ALL formatting (position, size, fonts, colors, images, etc.)
    because the original file structure is never rebuilt.

    Handles:
      - Regular shapes with text frames
      - Grouped shapes (recursive traversal)
      - Tables on slides
      - Placeholder type detection (title, subtitle, body)
    """
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    src_code = LANGUAGES[source_lang]
    tgt_code = LANGUAGES[target_lang]

    prs = Presentation(input_file)

    def _count_text_paragraphs(shapes):
        """Count translatable paragraphs in a list of shapes, including groups and tables."""
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

    def _translate_shapes(shapes, non_group=True):
        """Recursively translate text in shapes, handling groups and tables."""
        nonlocal completed
        for shape in shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                _translate_shapes(shape.shapes, non_group=False)
                continue

            # Handle tables on slides
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        for para in cell.text_frame.paragraphs:
                            text = para.text.strip()
                            if not text:
                                continue
                            print(f"  Translating PPTX table cell '{text[:40]}...' ({completed+1}/{total_items})", end="\r", flush=True)
                            translated_text = _translate_single(text, src_code, tgt_code, block_type="table_cell")
                            if glossary_store is not None:
                                translated_text = glossary_store.apply(translated_text)
                            _apply_translation_to_paragraph(para, translated_text, None)
                            completed += 1
                            if progress_callback:
                                progress_callback(completed, total_items)
                continue

            if not shape.has_text_frame:
                continue

            # Detect placeholder type for better translation context
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
                print(f"  Translating PPTX paragraph '{text[:40]}...' ({completed+1}/{total_items})", end="\r", flush=True)
                translated_text = _translate_single(text, src_code, tgt_code, block_type=block_type)
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
    print(f"\n  [OK] PPTX saved with layout preservation ({completed} items translated)")


def translate_xlsx_inplace(input_file, output_file, source_lang, target_lang,
                           glossary_store=None, progress_callback=None):
    """
    Translate an XLSX file by iterating all cells in-place.
    Preserves ALL formatting by modifying cell values directly.
    """
    from openpyxl import load_workbook

    src_code = LANGUAGES[source_lang]
    tgt_code = LANGUAGES[target_lang]

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

                print(f"  Translating XLSX cell '{text[:40]}...' ({completed+1}/{total_cells})", end="\r", flush=True)
                translated_text = _translate_single(text, src_code, tgt_code, block_type="table_cell")

                if glossary_store is not None:
                    translated_text = glossary_store.apply(translated_text)

                cell.value = translated_text

                completed += 1
                if progress_callback:
                    progress_callback(completed, total_cells)

    wb.save(output_file)
    wb.close()
    print(f"\n  [OK] XLSX saved with perfect layout preservation ({completed} cells translated)")


def write_docx(blocks, output_file, original_file=None):
    """Legacy DOCX writer for RTF/ODT fallback (creates new document from blocks)."""
    from docx import Document
    from docx.shared import RGBColor

    # ── Fallback: create new document from translated blocks ──────────────
    # This path is reached when the original input was RTF or ODT (no DOCX
    # to modify in-place).  Quality is inherently lower than in-place
    # translation, but this case is rare.
    new_doc = Document()
    para_blocks = [b for b in blocks if b.get("type") == "paragraph"]
    table_blocks = [b for b in blocks if b.get("type") == "table_cell"]

    available_styles = {s.name for s in new_doc.styles}

    for block in para_blocks:
        style_info = block.get("style") or {}
        resolved_style = Style_Mapper().resolve(style_info.get("style_name"), available_styles)
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

            # Track which grid positions have been consumed by a merge
            merged = set()

            for cell_block in cells:
                r, c = cell_block["row"], cell_block["col"]
                if (r, c) in merged:
                    continue

                col_span = cell_block.get("col_span", 1)
                row_span = cell_block.get("row_span", 1)

                # Merge cells if spanning
                if col_span > 1 or row_span > 1:
                    end_r = min(r + row_span - 1, max_row)
                    end_c = min(c + col_span - 1, max_col)
                    try:
                        table.cell(r, c).merge(table.cell(end_r, end_c))
                    except Exception:
                        pass
                    # Mark all spanned positions as merged
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
    Resolve PDF text overflow by trying, in order:
    1. Expand rect downward (if no collision with adjacent blocks)
    2. Reduce font size stepwise down to 6pt
    3. Create continuation box below the last block on the page

    Returns a dict with keys:
      resolved (bool)      — overflow fully resolved
      continuation (bool)  — continuation box was created
      expanded (bool)      — rect was expanded downward
      final_font (float)   — font size used for the final placement
      cont_rect (Rect|None) — the continuation box rect, if created
      clipped (bool)       — whether the continuation box was clipped to page
    """
    import fitz

    MIN_FONT = 6.0
    COLLISION_GAP = 2.0

    if text_color is None:
        text_color = (0, 0, 0)

    if initial_remaining >= 0:
        return {
            "resolved": True,
            "continuation": False,
            "expanded": False,
            "final_font": font_size,
            "cont_rect": None,
            "clipped": False,
        }

    result = {
        "resolved": False,
        "continuation": False,
        "expanded": False,
        "final_font": font_size,
        "cont_rect": None,
        "clipped": False,
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
            # Check both vertical AND horizontal overlap
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
                "resolved": True,
                "continuation": False,
                "expanded": True,
                "final_font": font_size,
                "cont_rect": None,
                "clipped": False,
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
                "resolved": True,
                "continuation": False,
                "expanded": False,
                "final_font": current_font,
                "cont_rect": None,
                "clipped": False,
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
        "resolved": remaining >= 0,
        "continuation": True,
        "expanded": False,
        "final_font": MIN_FONT,
        "cont_rect": cont_rect if remaining >= 0 else None,
        "clipped": clipped,
    }


def _is_libreoffice_available():
    """Return True if LibreOffice is installed and on PATH."""
    try:
        import subprocess
        result = subprocess.run(
            ["libreoffice", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


def translate_pdf_via_libreoffice(input_file, output_file, source_lang, target_lang,
                                   glossary_store=None, progress_callback=None):
    """
    Translate a PDF by round-tripping through DOCX via LibreOffice.

    Flow: PDF → (LibreOffice) → DOCX → translate_docx_inplace → (LibreOffice) → PDF

    This preserves original fonts, layout, images, and formatting perfectly
    because the translation happens on the DOCX, not the PDF.
    """
    import tempfile
    import subprocess
    import shutil

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
        translate_docx_inplace(
            docx_path, docx_path, source_lang, target_lang,
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

    Uses PDF redaction annotations to actually REMOVE original text glyphs from the
    content stream (not just cover them up), then inserts translated text with
    correct font, color, size, and alignment.

    Key improvements:
      - Redaction physically removes original text — no ghosting or double-text
      - All non-text elements (images, borders, lines, backgrounds) are preserved
      - Font, color, bold, italic are mapped to fitz built-in fonts
      - Character-length ratio for font sizing (more accurate than word count)
      - Overflow-first approach: calculate fit before inserting to avoid double-render
      - Text alignment preserved (centered, right-aligned detection)
      - Background color sampling for overflow areas
    """
    import fitz

    # Font mapper: common PDF font base names → fitz built-in font names
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
        """Resolve a fitz font name from style dict, handling bold and italic."""
        font_name = style.get("font", "helv")
        is_bold = style.get("bold", False)
        is_italic = style.get("italic", False)

        # Check exact match first (may include bold/italic in name)
        base_font = FONT_MAP.get(font_name)
        if base_font:
            # Already has bold/italic baked in from the map
            if "b" in base_font and is_bold:
                return base_font
            if "i" in base_font and is_italic:
                return base_font
            # Strip trailing style suffixes to get base, then rebuild
            for suffix in ("bi", "b", "i"):
                if base_font.endswith(suffix):
                    base_font = base_font[:-len(suffix)]
                    break
        else:
            # Try keyword matching via Font_Mapper
            base_font = Font_Mapper().resolve(font_name, set())

        if is_bold and is_italic and base_font in ("helv", "tiro", "cour"):
            return base_font + "bi"
        elif is_bold and base_font in ("helv", "tiro", "cour"):
            return base_font + "b"
        elif is_italic and base_font in ("helv", "tiro", "cour"):
            return base_font + "i"
        return base_font

    def _resolve_color(color_val):
        """Convert an int color (e.g. 0 = black) to an RGB tuple for fitz."""
        if isinstance(color_val, int) and color_val != 0:
            return fitz.sRGB_to_rgb(color_val)
        return (0, 0, 0)

    def _detect_alignment(block, page_width):
        """Detect text alignment based on block position relative to page center."""
        bbox = block.get("position", [0, 0, 0, 0])
        x0, y0, x1, y1 = bbox
        block_center = (x0 + x1) / 2.0
        page_center = page_width / 2.0
        block_width = x1 - x0
        # Block is centered if its center is near page center and it's not full-width
        if block_width < page_width * 0.85 and abs(block_center - page_center) < page_width * 0.05:
            return 1  # fitz align CENTER
        return 0  # fitz align LEFT (default; right-justify is rare and hard to detect)

    # Work on a copy of the original to keep original intact
    doc = fitz.open(original_pdf_path)

    # Group blocks by page
    pages_blocks = {}
    for block in blocks:
        p = block.get("page", 0)
        if p not in pages_blocks:
            pages_blocks[p] = []
        pages_blocks[p].append(block)

    # Phase 1: Add redaction annotations to remove original text
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
                print(f"  Redact annot error for block: {str(e)[:100]}")

    # Apply all redactions
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
                    "page": p_num,
                    "bbox": bbox,
                    "text": block["text"],
                })

    for page_num, page_blocks in pages_blocks.items():
        if page_num >= len(doc):
            continue
        page = doc[page_num]
        page_width = page.rect.width
        page_other_bboxes = [
            pb["bbox"] for pb in all_bboxes
            if pb["page"] == page_num
        ]

        for block in page_blocks:
            try:
                bbox = block.get("position", [50, 50, 500, 100])
                x0, y0, x1, y1 = bbox

                style = block.get("style", {})

                resolved_font = _resolve_font(style)
                text_color = _resolve_color(style.get("color", 0))

                # Font size: use original size, no pre-shrink
                font_size = float(style.get("font_size", 11) or 11)
                font_size = max(6.0, min(font_size, 72.0))

                # Detect alignment
                alignment = _detect_alignment(block, page_width)

                # Sample background color for overflow areas
                bg_color = Background_Sampler.sample(page, (x0, y0, x1, y1))

                # Overflow-first approach: try original size first, then strategies
                text_rect = fitz.Rect(x0, y0, x1, y1)
                remaining = page.insert_textbox(
                    text_rect, block["text"],
                    fontsize=font_size, fontname=resolved_font,
                    color=text_color, align=alignment,
                )

                if remaining < 0:
                    # Text didn't fit — try overflow resolution
                    overflow_result = _resolve_overflow(
                        page=page,
                        block_text=block["text"],
                        x0=x0, y0=y0, x1=x1, y1=y1,
                        font_size=font_size,
                        resolved_font=resolved_font,
                        other_bboxes=page_other_bboxes,
                        page_height=page.rect.height,
                        original_doc=doc,
                        page_num=page_num,
                        bg_color=bg_color,
                        initial_remaining=remaining,
                        text_color=text_color,
                        alignment=alignment,
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

    # Save to output path as a copy, preserving original
    doc.save(output_file, incremental=False)
    doc.close()
    print("  [OK] PDF saved with redaction-based text replacement (font, color, bold, italic, alignment preserved)")


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

        # Build a lookup: (slide, shape_id, para_idx) -> block
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
                        # Distribute across runs, preserving per-run formatting
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
        # Fallback: create new workbook
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Translated"

        cell_blocks = [b for b in blocks if b.get("type") == "cell"]
        for block in cell_blocks:
            ws.cell(row=block.get("row", 1), column=block.get("col", 1)).value = block["text"]

        wb.save(output_file)
        wb.close()
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


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(input_file, source_lang, target_lang,
                 output_file=None, pdf_column_mode="auto", glossary=None,
                 reference_file=None, progress_callback=None):
    """
    Run the complete translation pipeline using Mistral AI.
    
    progress_callback: optional callable(completed, total) for frontend progress.
    """
    if output_file is None:
        output_file = choose_output_path(input_file)

    # Build glossary store
    glossary_store = Glossary_Store(glossary) if glossary is not None else None

    ext = os.path.splitext(input_file)[1].lower()

    # ── In-place translation for DOCX, PPTX, XLSX (bypasses extract→translate→reconstruct) ──
    if ext == ".docx":
        print("[INPUT] Translating DOCX in-place...")
        translate_docx_inplace(
            input_file, output_file, source_lang, target_lang,
            glossary_store=glossary_store,
            progress_callback=progress_callback,
        )
        print("[DONE] Done!")
        return {
            "output_file": output_file,
            "translated_blocks": [],
            "bleu_score": None,
        }

    if ext == ".pptx":
        print("[INPUT] Translating PPTX in-place...")
        translate_pptx_inplace(
            input_file, output_file, source_lang, target_lang,
            glossary_store=glossary_store,
            progress_callback=progress_callback,
        )
        print("[DONE] Done!")
        return {
            "output_file": output_file,
            "translated_blocks": [],
            "bleu_score": None,
        }

    if ext == ".xlsx":
        print("[INPUT] Translating XLSX in-place...")
        translate_xlsx_inplace(
            input_file, output_file, source_lang, target_lang,
            glossary_store=glossary_store,
            progress_callback=progress_callback,
        )
        print("[DONE] Done!")
        return {
            "output_file": output_file,
            "translated_blocks": [],
            "bleu_score": None,
        }

    # ── PDF: try LibreOffice pipeline first (perfect layout preservation) ─
    if ext == ".pdf":
        if _is_libreoffice_available():
            print("[INPUT] Translating PDF via LibreOffice (DOCX round-trip)...")
            try:
                translate_pdf_via_libreoffice(
                    input_file, output_file, source_lang, target_lang,
                    glossary_store=glossary_store,
                    progress_callback=progress_callback,
                )
                print("[DONE] Done!")
                return {
                    "output_file": output_file,
                    "translated_blocks": [],
                    "bleu_score": None,
                }
            except Exception as e:
                print(f"  ⚠️  LibreOffice PDF translation failed: {e}")
                print("  Falling back to PyMuPDF direct translation...")
        else:
            print("[INPUT] LibreOffice not available, using PyMuPDF for PDF...")

    print("[INPUT] Reading document...")
    data, ext = analyze_document(input_file, pdf_column_mode=pdf_column_mode)

    if ext == ".csv":
        csv_data = data
        print(f"  Found {len(csv_data.get('data', []))} rows in CSV.")
        print("[TRANSLATE] Translating...")
        translated_rows = []
        for row_idx, row in enumerate(csv_data["data"]):
            translated_row = []
            for col_idx, cell in enumerate(row):
                if cell.strip() and len(cell.split()) >= 1:
                    print(f"  Translating cell [{row_idx+1},{col_idx+1}]...", end="\r")
                    translated_row.append(
                        _translate_single(cell, LANGUAGES[source_lang], LANGUAGES[target_lang])
                    )
                else:
                    translated_row.append(cell)
            translated_rows.append(translated_row)
        print("\n[OUTPUT] Rebuilding CSV ->", output_file)
        write_csv(translated_rows, output_file)
        print("[DONE] Done!")
        return {
            "output_file": output_file,
            "translated_blocks": [{"data": translated_rows}],
            "bleu_score": None,
        }

    blocks = data
    print(f"  Found {len(blocks)} text block(s) after filtering.")

    if not blocks:
        raise ValueError(
            "No translatable text extracted. "
            "If this is a scanned PDF, OCR is required. "
            "For bilingual PDFs, try pdf_column_mode='left' or 'right'."
        )

    print("[TRANSLATE] Translating...")
    ctx_buffer = Context_Buffer()
    ctx_buffer.clear()

    translated_blocks = batch_translate_blocks(
        blocks, source_lang, target_lang,
        glossary_store=glossary_store,
        context_buffer=ctx_buffer,
        progress_callback=progress_callback,
    )

    print(f"[OUTPUT] Rebuilding document -> {output_file}")
    reconstruct_document(translated_blocks, output_file, input_file, ext)

    # BLEU scoring (optional)
    bleu_score = None
    if reference_file is not None:
        try:
            from bleu_reporter import BLEU_Reporter
            bleu_reporter = BLEU_Reporter()
            bleu_score = bleu_reporter.compute(translated_blocks, reference_file)
            if bleu_score is not None:
                print(f"  [BLEU] Score: {bleu_score:.2f}")
        except ImportError:
            pass

    print("[DONE] Done!")
    return {
        "output_file": output_file,
        "translated_blocks": translated_blocks,
        "bleu_score": bleu_score,
    }