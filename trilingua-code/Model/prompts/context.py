# -*- coding: utf-8 -*-
"""
Context prompt builder.

Builds context-aware prompts that help maintain translation consistency
across chunks of large documents. Keeps terminology, names, and
abbreviations consistent throughout the document.

Contains NO provider-specific code.
"""


def build_context_window(previous_chunks: list[str], window_size: int = 3) -> str:
    """Build a context window from previously translated chunks.

    Args:
        previous_chunks: List of previously translated text strings.
        window_size: Maximum number of previous chunks to include.

    Returns:
        A context string to prepend to the translation prompt, or empty string.
    """
    if not previous_chunks:
        return ""

    recent = previous_chunks[-window_size:]
    context = " | ".join(recent)
    return f"Previous context: {context}"


def build_context_hint(terminology: dict) -> str:
    """Build a context hint from known terminology mappings.

    Args:
        terminology: Dict mapping source terms to target terms.

    Returns:
        A string with terminology instructions, or empty string.
    """
    if not terminology:
        return ""

    pairs = [f'"{src}" → "{tgt}"' for src, tgt in terminology.items()]
    return "Use these term translations: " + ", ".join(pairs)