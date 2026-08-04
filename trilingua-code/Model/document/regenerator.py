# -*- coding: utf-8 -*-
"""
Document regeneration sidecar.

Enables admin "Save & Regenerate" for document translations WITHOUT re-running
extraction, analysis, prepass, memory, or translation. The full block set
(including the structural metadata the reconstructor needs) is captured at
translate time into a JSON "sidecar". At regeneration time we overlay admin
edits onto the blocks and call only the pure-reconstruction code paths.

This module contains NO translation logic and NO provider calls.
"""

import json
import os

# Structural metadata keys the reconstructor may need.
_STRUCT_KEYS = (
    "type", "text", "position", "page", "lines", "links",
    "slide", "shape_id", "para_idx", "table_index",
    "row", "col", "row_span", "col_span", "sheet",
    "alignment", "passthrough",
)


# ── Sidecar builders ─────────────────────────────────────────────────────────

def _review_fields(block_index, block_type, source_text, tb):
    """A review-purpose block dict: what Laravel persists to translation_blocks.

    `tb` is a translated block (may already carry quality_score/issues).
    """
    entry = {
        "block_index": block_index,
        "block_type": tb.get("block_type") or tb.get("type", "paragraph"),
        "source_text": source_text,
        "ai_translated_text": tb.get("text", ""),
        "current_text": tb.get("text", ""),
        "quality_score": tb.get("quality_score"),
        "quality_issues": tb.get("quality_issues"),
    }
    if tb.get("passthrough"):
        entry["passthrough"] = True
    return entry


def rich_block_entry(block_index, tb, source_text):
    """Index-metadata + structural block for reconstruction (blocks path)."""
    entry = _review_fields(block_index, None, source_text, tb)
    entry["block_type"] = tb.get("type", "paragraph")
    for key in _STRUCT_KEYS:
        if key in tb:
            entry[key] = tb[key]
    # ensure 'text' reflects the translated text (for reconstruction)
    if "text" in tb:
        entry["text"] = tb["text"]
    return entry


def inplace_block_entry(block_index, block_type, source_text, translated_text):
    """A review-purpose block entry for in-place (DOCX/PPTX/XLSX) translations.

    No structural metadata is needed — the ORIGINAL file is the template for
    in-place regeneration.
    """
    return {
        "block_index": block_index,
        "block_type": block_type,
        "source_text": source_text,
        "ai_translated_text": translated_text,
        "current_text": translated_text,
    }


def finalize_sidecar(entries, request, ext, ctx=None, extra=None):
    """Version a list of block entries into a full regeneration sidecar.

    Args:
        entries: List of per-block dicts (review + structural fields).
        request: DocumentTranslationRequest (source/target/mode info).
        ext: Output format extension, e.g. ".pdf", ".docx" (lowercased).
        ctx: Optional DocumentContext (for layout plan / document type).
        extra: Optional extra top-level keys (e.g. CSV row grid).

    Returns:
        dict sidecar, JSON-serializable.
    """
    sidecar = {
        "version": 2,
        "format": (ext or "").lower(),
        "source_lang": getattr(request, "source_lang", ""),
        "target_lang": getattr(request, "target_lang", ""),
        "pdf_column_mode": getattr(request, "pdf_column_mode", "auto"),
        "mode": (ctx.mode.name if ctx and ctx.mode else ""),
        "document_type": (ctx.document_profile.document_type
                          if ctx and ctx.document_profile else ""),
        "layout_plan": _layout_to_dict(ctx.layout_plan) if ctx and ctx.layout_plan else None,
        "blocks": entries,
    }
    if extra:
        sidecar.update(extra)
    return sidecar


# ---------------------------------------------------------------------------
# Layout plan (de)serialization
# ---------------------------------------------------------------------------

def _layout_to_dict(plan):
    def _adj(a):
        return {
            "block_index": a.block_index,
            "estimated_expansion_ratio": a.estimated_expansion_ratio,
            "recommended_font_scale": a.recommended_font_scale,
            "overflow_risk": a.overflow_risk,
            "suggested_height_extra": a.suggested_height_extra,
            "continuation_needed": a.continuation_needed,
            "alignment_override": a.alignment_override,
            "indent_override": a.indent_override,
            "font_override": a.font_override,
            "paragraph_spacing": a.paragraph_spacing,
        }
    return {
        "adjustments": [_adj(a) for a in plan.adjustments],
        "page_breaks": [{"page_number": p.page_number,
                         "expected_overflow": p.expected_overflow}
                        for p in plan.page_breaks],
        "warnings": list(plan.warnings),
        "estimated_total_expansion": plan.estimated_total_expansion,
        "high_risk_blocks": plan.high_risk_blocks,
        "medium_risk_blocks": plan.medium_risk_blocks,
        "generated_by": plan.generated_by,
    }


def layout_from_dict(d):
    """Rebuild a LayoutPlan from a sidecar dict (or None)."""
    if not d:
        return None
    try:
        from document.layout_planner import LayoutPlan, BlockAdjustment, PageBreak
    except ImportError:
        return None
    return LayoutPlan(
        adjustments=[BlockAdjustment(**a) for a in d.get("adjustments", [])],
        page_breaks=[PageBreak(**p) for p in d.get("page_breaks", [])],
        warnings=list(d.get("warnings", [])),
        estimated_total_expansion=d.get("estimated_total_expansion", 0.0),
        high_risk_blocks=d.get("high_risk_blocks", 0),
        medium_risk_blocks=d.get("medium_risk_blocks", 0),
        generated_by=d.get("generated_by", "heuristic"),
    )


# ---------------------------------------------------------------------------
# Override application + reconstruction
# ---------------------------------------------------------------------------

def apply_overrides(blocks, overrides):
    """Return a NEW list of block dicts with edits overlaid onto 'text'.

    `overrides` is a mapping {block_index -> edited_text} (keys may be int or str).
    """
    if not overrides:
        return [dict(b) for b in blocks]
    norm = {str(k): v for k, v in overrides.items()}
    out = []
    for b in blocks:
        nb = dict(b)
        idx = b.get("block_index")
        if idx is not None and str(idx) in norm:
            nb["text"] = norm[str(idx)]
            nb["current_text"] = norm[str(idx)]
        out.append(nb)
    return out


def _make_inplace_translate_fn(lookup):
    """Build a translate_fn that replays stored/edited block text in call order.

    The in-place translators (DOCX/PPTX/XLSX) call translate_fn(text, block_type)
    in a deterministic order; the call counter aligns with `block_index` captured
    at translate time. Edits are applied only to the matching block.
    """
    counter = {"i": -1}

    def fn(text, block_type="paragraph"):
        counter["i"] += 1
        return lookup.get(counter["i"], text)

    return fn


def reconstruct_from_sidecar(sidecar, overrides, original_file, output_file,
                             source_lang="", target_lang="", pdf_column_mode="auto"):
    """Reconstruct an edited document from a sidecar. Reconstruction-only.

    Args:
        sidecar: Decoded sidecar dict.
        overrides: {block_index: edited_text} or None.
        original_file: Path to the ORIGINAL source file when required (.pdf,
            and the in-place .docx/.pptx/.xlsx need the real original; for text
            formats it may be None).
        output_file: Destination path for the regenerated file.
        source_lang: Source language name (for PDF expansion heuristics).
        target_lang: Target language name (for PDF expansion heuristics).
        pdf_column_mode: Passed through to reconstruction where relevant.

    Returns:
        output_file on success.

    No extraction, analysis, prepass, or translation runs here.
    """
    fmt = (sidecar.get("format") or "").lower()
    blocks = sidecar.get("blocks", [])
    layout_plan = layout_from_dict(sidecar.get("layout_plan"))

    # In-place formats reproduce the template from the ORIGINAL file by replaying
    # the store/edited texts. No block metadata is needed in the sidecar.
    if fmt in (".docx", ".pptx", ".xlsx"):
        if not original_file or not os.path.exists(original_file):
            raise FileNotFoundError(
                f"In-place regeneration ({fmt}) requires the original file."
            )
        lookup = {b.get("block_index"): b.get("text", "") for b in blocks}
        _reconstruct_inplace(fmt, original_file, output_file, lookup)
        return output_file

    # Blocks-based reconstruction (PDF, TXT, MD, RTF->DOCX, ODT->DOCX, CSV).
    edited_blocks = apply_overrides(blocks, overrides)

    if fmt == ".csv":
        _reconstruct_csv(edited_blocks, sidecar, output_file)
        return output_file

    from document.reconstructor import reconstruct_document
    reconstruct_document(
        edited_blocks,
        output_file,
        original_file=original_file if os.path.exists(original_file or "") else None,
        source_lang=source_lang,
        target_lang=target_lang,
        layout_plan=layout_plan,
    )
    return output_file


def _reconstruct_inplace(fmt, original_file, output_file, lookup):
    translate_fn = _make_inplace_translate_fn(lookup)
    if fmt == ".docx":
        from document.reconstructor import _translate_docx_inplace_with_translator
        _translate_docx_inplace_with_translator(
            original_file, output_file, translate_fn, glossary_store=None
        )
    elif fmt == ".pptx":
        from document.reconstructor import translate_pptx_inplace
        translate_pptx_inplace(original_file, output_file, translate_fn, glossary_store=None)
    elif fmt == ".xlsx":
        from document.reconstructor import translate_xlsx_inplace
        translate_xlsx_inplace(original_file, output_file, translate_fn, glossary_store=None)


def _reconstruct_csv(blocks, sidecar, output_file):
    """Rewrite a CSV from edited cell blocks, preserving the original grid."""
    rows = sidecar.get("rows")
    if not rows:
        rows = [[]]
    cell_map = {}
    for b in blocks:
        key = (b.get("row") or 0, b.get("col") or 0)
        cell_map[key] = b.get("text", "")
    grid = []
    for r_idx, row in enumerate(rows):
        new_row = []
        for c_idx, _ in enumerate(row):
            new_row.append(cell_map.get((r_idx, c_idx), row[c_idx]))
        grid.append(new_row)
    from document.reconstructor import write_csv
    write_csv(grid, output_file)