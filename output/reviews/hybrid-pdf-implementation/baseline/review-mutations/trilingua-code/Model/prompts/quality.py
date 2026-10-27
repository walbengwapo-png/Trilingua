# -*- coding: utf-8 -*-
"""
Quality validation prompt builder.

Provides prompts for checking translation quality, consistency,
and accuracy. These are used by the validation pipeline.

Contains NO provider-specific code.
"""


def build_batch_quality_review_prompt(
    entries: list[tuple[int, str, str]],
    document_type: str = "",
) -> str:
    """Build a prompt for batched AI quality review of multiple translations.

    Each entry is (block_index, source_text, translation_text).
    The prompt requests JSON output with per-block score, issues, and summary.

    Args:
        entries: List of (block_index, source, translation) tuples.
        document_type: Optional document type for context.

    Returns:
        A prompt string for batched quality review.
    """
    parts = [
        "Review each (source, translation) pair for quality issues.\n",
        "Return a JSON object where each key is the block index. "
        "Each value is a quality assessment:\n",
        '  {"0": {"score": 85.0, "issues": [...], "summary": "..."}, '
        '"1": {"score": 95.0, "issues": [], "summary": "..."}}\n\n',
        "Score is 0-100 where 100 is a perfect translation.\n"
        "Each issue has: severity (critical/major/minor), "
        "category, description.\n\n",
        "Check for: missing content (compare clause by clause), hallucinations, "
        "terminology errors, number/date/entity errors (cross-check each value "
        "against the source), untranslated text, formatting issues.\n\n",
        "Return ONLY valid JSON. No explanations.\n",
    ]

    if document_type:
        parts.append(f"Document type: {document_type}\n\n")

    for idx, source, translation in entries:
        parts.append(
            f"[{idx}]\n"
            f"SOURCE:\n{source}\n\n"
            f"TRANSLATION:\n{translation}\n"
        )

    return "".join(parts)


def build_consistency_check_prompt(chunks: list[tuple[str, str]]) -> str:
    """Build a prompt to check consistency across multiple translated chunks.

    Args:
        chunks: List of (source_text, translated_text) tuples.

    Returns:
        A prompt string for consistency checking.
    """
    prompt_parts = [
        "Check these translated chunks for terminology consistency:\n"
    ]
    for i, (src, tgt) in enumerate(chunks):
        prompt_parts.append(f"\nChunk {i + 1}:\n  Source: {src}\n  Translation: {tgt}")

    prompt_parts.append(
        "\n\nAre there any terms that are translated inconsistently across chunks? "
        "Respond with 'CONSISTENT' or 'INCONSISTENT: <term> appears as X in chunk A but Y in chunk B'."
    )

    return "\n".join(prompt_parts)


def build_reconstruction_validation_prompt(original_blocks: list[dict],
                                           translated_blocks: list[dict]) -> str:
    """Build a prompt to validate document reconstruction.

    Args:
        original_blocks: Original extracted blocks with metadata.
        translated_blocks: Translated blocks with metadata.

    Returns:
        A prompt string for reconstruction validation.
    """
    return (
        f"Original had {len(original_blocks)} blocks. "
        f"Translated has {len(translated_blocks)} blocks.\n"
        "Check: Are block counts the same? Are all block types preserved? "
        "Are table structures intact? Are text positions preserved?"
    )