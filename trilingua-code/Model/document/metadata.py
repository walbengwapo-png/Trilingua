# -*- coding: utf-8 -*-
"""
Document metadata extraction.

Responsible for extracting and managing metadata about document elements
that are needed for layout preservation during reconstruction.

Contains NO translation logic.
"""


def extract_block_metadata(block: dict) -> dict:
    """Extract metadata from a document block for reconstruction.

    Args:
        block: A block dict from the document extractor.

    Returns:
        A metadata dict with layout-relevant information.
    """
    metadata = {
        "type": block.get("type", "paragraph"),
        "text_length": len(block.get("text", "")),
        "word_count": len(block.get("text", "").split()),
    }

    # Position metadata for PDF
    if "position" in block:
        metadata["position"] = block["position"]
        metadata["page"] = block.get("page", 0)
        bbox = block["position"]
        if len(bbox) >= 4:
            metadata["width"] = bbox[2] - bbox[0]
            metadata["height"] = bbox[3] - bbox[1]

    # Style metadata
    style = block.get("style", {})
    if style:
        metadata["font_size"] = style.get("font_size")
        metadata["bold"] = style.get("bold")
        metadata["alignment"] = style.get("alignment")

    # Table metadata
    if block.get("type") == "table_cell":
        metadata["table_index"] = block.get("table_index")
        metadata["row"] = block.get("row")
        metadata["col"] = block.get("col")
        metadata["col_span"] = block.get("col_span", 1)
        metadata["row_span"] = block.get("row_span", 1)

    # Slide metadata
    if "slide" in block:
        metadata["slide"] = block["slide"]
        metadata["shape_id"] = block.get("shape_id")
        metadata["para_idx"] = block.get("para_idx")

    # Sheet metadata
    if "sheet" in block:
        metadata["sheet"] = block["sheet"]

    return metadata


def count_document_elements(blocks: list[dict]) -> dict:
    """Count element types in a document.

    Args:
        blocks: List of extracted blocks.

    Returns:
        Dict with counts by element type.
    """
    counts = {}
    for block in blocks:
        block_type = block.get("type", "unknown")
        counts[block_type] = counts.get(block_type, 0) + 1
    return counts