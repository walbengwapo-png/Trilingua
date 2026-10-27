# -*- coding: utf-8 -*-
"""
Unit adapters (dict <-> TranslationUnit boundary).

The extraction layer, reconstruction layer, regeneration sidecar and the
Laravel-facing dict API all speak plain dicts. The core translation pipeline
speaks DTOs. These two functions are the ONLY places those representations
meet:

- ``to_unit``      : one dict  -> TranslationUnit (read-only, no deep copies)
- ``unit_to_block``: one unit + result -> dict, reproducing the exact dict
                     shape the legacy pipeline emits (passthrough flag,
                     ``_original_text`` for positioned PDF blocks, and the
                     admin quality score/issues surfaced from the context).

``default_translate_many`` is the duck-typed fallback used when a provider
implements only the legacy single-block ``translate()`` method.
"""

import time
from typing import List, Optional, Sequence

from dto.pipeline import TranslationUnit, TranslationUnitResult
from dto.responses import TranslationResponse
from document.map import (DocumentMap, build_document_map, content_neighbors,
                          table_headers_for)
from document.protected_spans import detect_protected_spans

_ROLE_TYPES = {
    "paragraph": "paragraph",
    "heading": "heading",
    "title": "title",
    "subtitle": "heading",
    "header": "header",
    "footer": "footer",
    "table_cell": "table_cell",
    "cell": "table_cell",
    "caption": "caption",
    "list_item": "list_item",
    "code": "code",
    "text_box": "text_box",
    "shape": "text_box",
    "image": "image",
    "img": "image",
    "page_number": "page_number",
}


def _role_for(block: dict) -> str:
    return _ROLE_TYPES.get(block.get("type", ""), "paragraph")


def to_unit(block: dict, block_id: int, document_map: Optional[DocumentMap] = None) -> TranslationUnit:
    """Convert one extractor block dict into a TranslationUnit (no copies)."""
    text = block.get("text", "") or ""
    previous, following = "", ""
    if document_map is not None:
        previous, following = content_neighbors(document_map.blocks, block_id)
    return TranslationUnit(
        unit_id=block_id,
        source_block_id=block_id,
        page=block.get("page", 0),
        reading_order=document_map.reading_order.get(block_id, block_id) if document_map else block_id,
        bbox=tuple(block.get("bbox", ())) or tuple(block.get("position", ())),
        role=_role_for(block),
        section_id=document_map.section_id.get(block_id, "") if document_map else "",
        source_text=text,
        previous_context=previous,
        next_context=following,
        table_headers=table_headers_for(document_map, block_id) if document_map else (),
        protected_spans=tuple(detect_protected_spans(text)),
        style_reference=block.get("style"),
        furniture=bool(document_map and block_id in document_map.furniture),
    )


def to_unit_list(blocks: List[dict],
                 document_map: Optional[DocumentMap] = None) -> List[TranslationUnit]:
    """Convert a block list into unit DTOs, rebuilding the map if needed."""
    if document_map is None:
        document_map = build_document_map(blocks)
    return [to_unit(block, idx, document_map) for idx, block in enumerate(blocks)]


def unit_to_block(block: dict, unit: TranslationUnit, result: TranslationUnitResult,
                  ctx=None) -> dict:
    """Reconstruct one legacy-style block dict from a unit + result.

    Mirrors the legacy reassembly loop exactly:
    - passthrough blocks: ``dict(block, text=source, passthrough=True)``
    - translated blocks: ``dict(block)`` with ``text`` replaced, optional
      ``_original_text`` (positioned PDF blocks) and admin quality fields.
    Every identity/style/coordinate field survives untouched.
    """
    if result.status in ("passthrough", "failed"):
        return dict(block, text=block.get("text", ""), passthrough=True)

    new_block = dict(block)
    new_block["text"] = result.translated_text

    if "position" in block:
        new_block["_original_text"] = block.get("text", "")

    if ctx is not None and result.status in ("translated", "cached", "repaired"):
        q = ctx.block_quality.get(unit.source_block_id)
        if q:
            new_block["quality_score"] = q.get("score")
            new_block["quality_issues"] = q.get("issues")

    return new_block


def build_provider_hint(unit: TranslationUnit, context_preamble: str = "",
                        memory_context: str = "",
                        semantic_context: str = "") -> str:
    """Assemble the full per-unit provider context as a single prompt block.

    Renders every unit field that matters for translation quality into one
    ordered hint: document preamble, document-memory context, semantic-group
    context, role, furniture status, table headers, neighbor text and
    protected-span instructions. Called by the pipeline before dispatch so
    both ``translate_many`` providers (read ``unit.context_hint``) and the
    legacy single-block fallback path receive identical context.
    """
    parts = [part for part in (context_preamble, memory_context, semantic_context) if part]
    parts.append(f"Block role: {unit.role}.")
    if unit.furniture:
        parts.append(
            "This is recurring running header/footer text; keep the translation "
            "concise and consistent with its repeated use."
        )
    if unit.table_headers:
        parts.append(
            "Table column headers for context: " + " | ".join(unit.table_headers) + "."
        )
    if unit.previous_context:
        parts.append(f"Preceding text: {unit.previous_context}")
    if unit.next_context:
        parts.append(f"Following text: {unit.next_context}")
    if unit.protected_spans:
        kinds = ", ".join(sorted({s.kind for s in unit.protected_spans}))
        parts.append(
            "Do not translate, reorder or alter these kinds of spans "
            f"(keep character-for-character identical): {kinds}."
        )
    return "\n".join(parts)


def default_translate_many(provider, units: Sequence[TranslationUnit],
                           source_lang: str, target_lang: str,
                           context_hint: str = "", document_type: str = "",
                           ctx=None, translation_cache=None) -> List[TranslationUnitResult]:
    """Translate units through a legacy single-block provider.

    This is the compatibility path for duck-typed providers that do not
    implement ``translate_many`` (tests/mock_providers.MockTranslationProvider
    included). It is intentionally sequential and allocation-light.

    The prompt for each unit prefers the pipeline-assembled
    ``unit.context_hint``; when absent (direct callers) it falls back to the
    document-level context hint plus the unit's structural neighbors and
    protected-span instructions.
    """
    results: List[TranslationUnitResult] = []
    for unit in units:
        if unit.context_hint:
            hint = unit.context_hint
        else:
            parts = [part for part in (context_hint, unit.previous_context, unit.next_context) if part]
            if unit.protected_spans:
                kinds = ", ".join(sorted({s.kind for s in unit.protected_spans}))
                parts.append(
                    "Do not translate, reorder or alter these kinds of spans "
                    f"(keep character-for-character identical): {kinds}. End of instruction."
                )
            hint = "\n".join(parts)
        started = time.time()
        response: TranslationResponse = provider.translate(
            text=unit.source_text,
            source_lang=source_lang,
            target_lang=target_lang,
            block_type=unit.role,
            context_hint=hint,
            document_type=document_type,
        )
        elapsed_ms = (time.time() - started) * 1000.0
        results.append(TranslationUnitResult(
            unit_id=unit.unit_id,
            status="translated" if response.success else "failed",
            translated_text=response.translated_text if response.success else "",
            error=response.error_message if not response.success else "",
            provider=response.provider or getattr(provider, "name", ""),
            model=response.model or getattr(provider, "model_name", ""),
            execution_time_ms=elapsed_ms,
        ))
    return results


def translate_many_units(provider, units: Sequence[TranslationUnit],
                         source_lang: str, target_lang: str,
                         context_hint: str = "", document_type: str = "",
                         ctx=None, translation_cache=None) -> List[TranslationUnitResult]:
    """Dispatch unit translation to ``translate_many`` when available.

    Falls back to the sequential compatibility path for providers that only
    implement ``translate()``.
    """
    method = getattr(provider, "translate_many", None)
    if callable(method):
        results = method(
            units, source_lang=source_lang, target_lang=target_lang,
            context_hint=context_hint, document_type=document_type, ctx=ctx,
        )
        if ctx is not None:
            for r in results:
                ctx.record_provider(r.provider, r.model)
        return list(results)
    return default_translate_many(
        provider, units, source_lang=source_lang, target_lang=target_lang,
        context_hint=context_hint, document_type=document_type, ctx=ctx,
        translation_cache=translation_cache,
    )