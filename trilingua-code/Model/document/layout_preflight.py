# -*- coding: utf-8 -*-
"""
Layout Preflight.

Forecasts whether a translated unit will still fit inside its original
geometry BEFORE reconstruction, so layout stressors (overflow into the next
block, clipping past the page, outside-page placement) can be surfaced as
warnings instead of silently corrupting the output.

This module performs NO rendering and NO AI calls. It uses the same font-math
conventions as ``reconstructor`` (language expansion coefficient, per-line
estimate from font size, and the "never merge into the next block" rule).
``LayoutResult`` DTOs are attached to each ``TranslationUnitResult`` so the
sidecar/API can report them without the dict path knowing anything about them.
"""

import math
from typing import Optional, Tuple

from dto.pipeline import LayoutResult, TranslationUnit

_MAX_LINE_RATIO = 2.0          # generous per-line ratio of font size
_DEFAULT_FONT_SIZE = 12.0       # points, when style lacks font_size
_AVG_CHAR_WIDTH_FACTOR = 0.5    # avg char ~ 0.5em
_LINE_HEIGHT_FACTOR = 1.2       # leading
_FIT_PADDING = 1.0              # pt tolerance


def _lang_expansion(source_lang: str = "", target_lang: str = "") -> float:
    coeffs = {
        "English-Cebuano": 1.25,
        "English-Filipino": 1.35,
        "Cebuano-English": 0.85,
        "Cebuano-Filipino": 1.10,
        "Filipino-English": 0.80,
        "Filipino-Cebuano": 0.95,
    }
    return coeffs.get(f"{source_lang}-{target_lang}", 1.0)


def _font_size_of(unit: TranslationUnit) -> float:
    style = unit.style_reference
    if isinstance(style, dict):
        size = style.get("font_size") or style.get("size")
        if size:
            try:
                return float(size)
            except (TypeError, ValueError):
                pass
    return _DEFAULT_FONT_SIZE


def _estimate_lines(text: str, font_size: float, available_width: float) -> int:
    """Estimate wrapped line count for a block of text with a fixed-width em."""
    if not text or available_width <= 0:
        return 0
    avg_char_width = max(_AVG_CHAR_WIDTH_FACTOR, 1.0) * font_size
    # Use min space-and-char width so CJK-ish wide chars degrade gracefully.
    effective = max(avg_char_width, font_size * 0.75)
    chars_per_line = max(1, int(available_width / effective))
    return max(1, math.ceil(len(text) / chars_per_line))


def _expected_expansion(unit: TranslationUnit, reference_length: int) -> float:
    if reference_length <= 0:
        return 1.0
    expansion = 1.0
    if unit.style_reference is None:
        return expansion
    # Deterministic per-document style hint is not available at unit level;
    # rely on translation length server-side only. Keep DTO-light.
    return expansion


def preflight_unit(unit: TranslationUnit, translated_text: str,
                   source_lang: str = "", target_lang: str = "",
                   next_bbox: Optional[Tuple[float, float, float, float]] = None,
                   page_height: Optional[float] = None) -> LayoutResult:
    """Forecast fit/collision/clipping for one translated unit.

    Uses the unit bbox (extractor geometry) and the predictor that the
    reconstruction layer will apply later. Never touches the next block —
    it only READS the next bbox for collision detection.
    """
    bbox = unit.bbox
    if not bbox or len(bbox) < 4:
        return LayoutResult(
            fit_actions=("no_geometry",),
            final_geometry=(),
            final_font=unit.style_reference,
            collision_state="none",
            clipping_state="none",
        )

    x0, y0, x1, y1 = (float(v) for v in bbox[:4])
    width = max(x1 - x0, 1.0)
    height = max(y1 - y0, 0.0)
    font_size = _font_size_of(unit)
    line_height = max(font_size * _LINE_HEIGHT_FACTOR, 1.0)

    expansion = _lang_expansion(source_lang, target_lang)
    projected_chars = int(len(translated_text) * expansion)

    lines = _estimate_lines(translated_text, font_size, width)
    projected_lines = _estimate_lines("x" * projected_chars, font_size, width)
    required_height = max(lines, projected_lines) * line_height

    final_bottom = y1
    fit_actions = []
    overflow_state = "fits"

    if not translated_text:
        fit_actions.append("empty")
        final_bottom = y1
    else:
        if required_height > height + _FIT_PADDING:
            overflow_state = "overflow"
            fit_actions.append("overflow")
            ratio = required_height / height if height > 0 else 1.0
            if ratio >= 1.5:
                fit_actions.append("severe_overflow")
            # Predict the reconstructed bottom WITHOUT wrapping into neighbor.
            final_bottom = y0 + required_height
        else:
            fit_actions.append("fits")
            final_bottom = max(y1, y0 + required_height)

    collision_state = "none"
    if next_bbox and len(next_bbox) >= 4:
        next_top = float(next_bbox[1])
        if final_bottom > next_top + _FIT_PADDING:
            collision_state = "collision"
            if "collides_downstream" not in fit_actions:
                fit_actions.append("collides_downstream")

    clipping_state = "none"
    if page_height is not None:
        if final_bottom > float(page_height) + _FIT_PADDING:
            clipping_state = "clipped"
            if "overflows_page" not in fit_actions:
                fit_actions.append("overflows_page")
        if y0 >= float(page_height) or x1 <= 0 or x0 < 0:
            clipping_state = "outside_page"
            if "outside_page" not in fit_actions:
                fit_actions.append("outside_page")

    if "fits" in fit_actions and overflow_state == "fits":
        final_font = font_size
    else:
        # Reconstruction may shrink the font toward a 70% floor; record the
        # planner's likely target so the sidecar can see the intent.
        final_font = max(font_size * 0.7, 4.0) if overflow_state == "overflow" else font_size

    final_geometry = (x0, y0, x1, max(final_bottom, y1))

    return LayoutResult(
        fit_actions=tuple(fit_actions),
        final_geometry=final_geometry,
        final_font=final_font,
        collision_state=collision_state,
        clipping_state=clipping_state,
    )


def preflight_units(units: Tuple[TranslationUnit, ...],
                    results: dict,
                    source_lang: str = "", target_lang: str = "",
                    page_height: Optional[float] = None) -> None:
    """Attach a LayoutResult to every unit result that has geometry.

    ``results`` maps unit_id -> TranslationUnitResult; results are mutated
    in place with their ``layout`` field populated.
    """
    by_unit = {unit.unit_id: unit for unit in units}
    ordered = sorted(units, key=lambda u: (u.page, u.reading_order))
    for u in ordered:
        result = results.get(u.unit_id)
        if result is None or result.status in ("passthrough", "failed"):
            continue
        next_unit = _next_on_page(ordered, u)
        next_bbox = next_unit.bbox if next_unit else None
        result.layout = preflight_unit(
            u, result.translated_text,
            source_lang=source_lang, target_lang=target_lang,
            next_bbox=next_bbox, page_height=page_height,
        )


def _next_on_page(ordered: list, unit: TranslationUnit):
    """Return the next unit on the same page by reading order."""
    for u in ordered:
        if u.page == unit.page and u.reading_order > unit.reading_order:
            return u
    return None