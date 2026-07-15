# -*- coding: utf-8 -*-
"""
Processing mode definitions for TriLingua v2.

Each mode enables progressively more AI-assisted features while keeping
the deterministic document engineering pipeline intact.

Fast:      Minimal AI — same as the current pipeline.
Balanced:  Recommended default — enables the most valuable AI enhancements.
Thorough:  Full AI pipeline — maximum quality for complex documents.
Auto:      Automatically selects mode based on document characteristics.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessingMode:
    """Configuration flags for the translation pipeline.

    Each flag controls whether a specific AI-assisted phase is active.
    Setting all flags to False reproduces the original pipeline behavior.
    """

    name: str

    # Phase 1 — AI Document Analyzer
    document_analyzer: bool = False

    # Phase 2 — Document Memory (replaces tiny ContextBuffer)
    document_memory: bool = False

    # Phase 3 — Semantic Chunking (algorithmic, no extra AI call)
    semantic_chunking: bool = False

    # Phase 4 — Specialized Translation Prompts
    specialized_prompts: bool = False

    # Phase 5 — AI Quality Review
    ai_quality_review: bool = False

    # Phase 6 — Translation Cache (hash-based dedup within document)
    translation_cache: bool = False

    # Phase 8 — AI Layout Planner (PDF only)
    layout_planner: bool = False


# ── Preset Modes ──────────────────────────────────────────────────────────────

FAST = ProcessingMode(
    name="fast",
    document_analyzer=False,
    document_memory=False,
    semantic_chunking=False,
    specialized_prompts=False,
    ai_quality_review=False,
    translation_cache=False,
    layout_planner=False,
)

BALANCED = ProcessingMode(
    name="balanced",
    document_analyzer=True,
    document_memory=True,
    semantic_chunking=True,
    specialized_prompts=True,
    ai_quality_review=True,
    translation_cache=True,
    layout_planner=False,
)

THOROUGH = ProcessingMode(
    name="thorough",
    document_analyzer=True,
    document_memory=True,
    semantic_chunking=True,
    specialized_prompts=True,
    ai_quality_review=True,
    translation_cache=True,
    layout_planner=True,
)

# ── Mode Registry ─────────────────────────────────────────────────────────────

MODES: dict[str, ProcessingMode] = {
    "fast": FAST,
    "balanced": BALANCED,
    "thorough": THOROUGH,
}

VALID_MODES = set(MODES.keys()) | {"auto"}


def get_mode(name: str) -> ProcessingMode:
    """Get a ProcessingMode by name.

    Args:
        name: One of 'fast', 'balanced', 'thorough'.

    Returns:
        The corresponding ProcessingMode.

    Raises:
        ValueError: If name is unknown.
    """
    mode = MODES.get(name)
    if mode is None:
        raise ValueError(
            f"Unknown processing mode '{name}'. "
            f"Valid modes: {', '.join(MODES.keys())} + 'auto'"
        )
    return mode