# -*- coding: utf-8 -*-
"""
Document Map.

Builds the structural identity of a document once (reading order, section
assignment, table header rows, recurring furniture such as running headers
and footers) so the unit pipeline can enrich every ``TranslationUnit``
without re-scanning the block list. This module performs NO AI calls and
makes NO mutating copies of block dicts.
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple

_HEADING_TYPES = ("heading", "title", "subtitle")
_SECTION_TYPES = ("heading", "title", "subtitle", "header")
_FURNITURE_TYPES = ("footer", "header")


@dataclass(slots=True)
class DocumentMap:
    """Per-block structural metadata keyed by block index into the source list."""
    blocks: List[dict] = field(default_factory=list)
    reading_order: Dict[int, int] = field(default_factory=dict)
    section_id: Dict[int, str] = field(default_factory=dict)
    section_titles: Dict[str, str] = field(default_factory=dict)
    table_headers: Dict[int, Tuple[str, ...]] = field(default_factory=dict)
    furniture: FrozenSet[int] = frozenset()


def _is_header_cell(block: dict) -> bool:
    return block.get("row") == 0


def _table_group_key(block: dict) -> Optional[Tuple]:
    """Return the table identity of a cell block, if present."""
    if block.get("type") != "table_cell":
        return None
    tidx = block.get("table_index")
    if tidx is None:
        return None
    return (tidx, block.get("page", 0))


def build_document_map(blocks: List[dict]) -> DocumentMap:
    """Compute structural metadata for every block by index.

    Reading order is simply the block order (aligned with detected columns;
    the extractor already emits blocks in document order). Sections are
    started by heading/title blocks. Recurring header/footer text is treated
    as document furniture. Table header rows are derived from
    ``table_index``/``row`` metadata when available.
    """
    document_map = DocumentMap(blocks=list(blocks))
    if not blocks:
        return document_map

    current_section = ""
    section_counter = 0
    header_text_counts: Dict[str, int] = {}
    furniture_indices: List[int] = []

    for idx, block in enumerate(blocks):
        block_type = block.get("type", "paragraph")
        text = block.get("text", "") or ""
        document_map.reading_order[idx] = idx

        if block_type in _SECTION_TYPES:
            stripped = text.strip()
            if stripped and stripped != document_map.section_titles.get(current_section, ""):
                section_counter += 1
                current_section = f"section_{section_counter}"
                document_map.section_titles[current_section] = stripped[:200]

        if block_type in _FURNITURE_TYPES and text.strip():
            header_text_counts[text.strip()] = header_text_counts.get(text.strip(), 0) + 1
            furniture_indices.append(idx)

        document_map.section_id[idx] = current_section

    for idx in furniture_indices:
        block_type = blocks[idx].get("type", "")
        text = blocks[idx].get("text", "") or ""
        if block_type == "footer" or header_text_counts.get(text.strip(), 0) > 1:
            document_map.furniture = frozenset(list(document_map.furniture) + [idx])

    table_headers: Dict[Tuple, List[str]] = {}
    for idx, block in enumerate(blocks):
        if block.get("type") != "table_cell":
            continue
        key = _table_group_key(block)
        if key is None:
            continue
        if _is_header_cell(block):
            text = block.get("text", "") or ""
            if text and text not in table_headers.setdefault(key, []):
                table_headers[key].append(text)

    document_map.table_headers = {idx: tuple(table_headers.get(key, ()))
                                  for idx, block in enumerate(blocks)
                                  if _table_group_key(block) is not None
                                  and (key := _table_group_key(block)) is not None}

    return document_map


def table_headers_for(document_map: DocumentMap, block_index: int) -> Tuple[str, ...]:
    """Resolve header-row context for a table cell block."""
    return document_map.table_headers.get(block_index, ())


def content_neighbors(blocks: List[dict], index: int,
                      max_chars: int = 200) -> Tuple[str, str]:
    """Return (previous_context, next_context) non-empty text around a block."""
    previous = ""
    for i in range(index - 1, -1, -1):
        text = blocks[i].get("text", "") or ""
        if text.strip():
            previous = text
            break
    following = ""
    for i in range(index + 1, len(blocks)):
        text = blocks[i].get("text", "") or ""
        if text.strip():
            following = text
            break
    return previous[:max_chars], following[:max_chars]