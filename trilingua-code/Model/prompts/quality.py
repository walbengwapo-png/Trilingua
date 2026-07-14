# -*- coding: utf-8 -*-
"""
Quality validation prompt builder.

Provides prompts for checking translation quality, consistency,
and accuracy. These are used by the validation pipeline.

Contains NO provider-specific code.
"""


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