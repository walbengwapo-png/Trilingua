# -*- coding: utf-8 -*-
"""
Domain transfer objects for the provider-neutral translation pipeline.

These are lightweight, allocation-friendly records (``slots=True``) used ONLY
inside the core pipeline. Extraction, reconstruction, sidecar writing and the
rest of the Laravel-facing dict API keep using plain dicts; conversion happens
exactly once at each boundary (see ``pipeline/unit_adapters.py``).

Conventions in this file:
- No Pydantic models and no JSON serialization in the per-block hot path.
- ``style_reference`` is a reference to the original style dict (never a copy).
- Geometry/span fields are tuples.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple


@dataclass(slots=True)
class ProtectedSpan:
    """A character span inside a source block that must survive translation."""
    start: int
    end: int
    kind: str


@dataclass(slots=True)
class TranslationUnit:
    """A single, scheduled unit of translation work backed by one original block."""
    unit_id: int
    source_block_id: int
    page: int = -1
    reading_order: int = 0
    bbox: Tuple[float, float, float, float] = ()
    role: str = "paragraph"
    section_id: str = ""
    source_text: str = ""
    previous_context: str = ""
    next_context: str = ""
    table_headers: Tuple[str, ...] = ()
    protected_spans: Tuple[ProtectedSpan, ...] = ()
    style_reference: Any = None
    furniture: bool = False
    # Fully assembled provider-facing prompt/context for this unit (role,
    # table headers, furniture status, neighbor text, protected-span
    # instructions, document preamble, memory and semantic-group context).
    # Populated by batch_translate_units before dispatch; providers that
    # implement translate_many read it straight off each unit.
    context_hint: str = ""


@dataclass(slots=True)
class QualityResult:
    """Outcome of the AI quality review for a single translated unit."""
    score: float = 0.0
    issue: str = ""
    repair_eligible: bool = False
    snippets: Tuple[Tuple[str, str], ...] = ()
    reviewer: str = ""


@dataclass(slots=True)
class LayoutResult:
    """Fitted-geometry forecast for a translated unit before reconstruction."""
    fit_actions: Tuple[str, ...] = ()
    final_geometry: Tuple[float, float, float, float] = ()
    final_font: Any = None
    collision_state: str = "none"
    clipping_state: str = "none"


@dataclass(slots=True)
class TranslationUnitResult:
    """Outcome of translating one unit through the provider layer."""
    unit_id: int
    status: str = "translated"
    translated_text: str = ""
    error: str = ""
    provider: str = ""
    model: str = ""
    execution_time_ms: float = 0.0
    quality: Optional[QualityResult] = None
    layout: Optional[LayoutResult] = None


@dataclass(slots=True)
class ProviderCapabilities:
    """Static capabilities of a provider, read once and reused per document."""
    provider: str = ""
    batch_enabled: bool = False
    max_batch_items: int = 0
    max_batch_chars: int = 0
    max_concurrency: Optional[int] = None
    context_window: int = 0
    languages: Tuple[str, ...] = ()
    latency_profile: str = ""

    @classmethod
    def from_provider(cls, provider) -> "ProviderCapabilities":
        """Read capabilities off any provider duck-typed enough to have them."""
        batch_limits = getattr(provider, "batch_limits", None) or {}
        return cls(
            provider=str(getattr(provider, "name", "")),
            batch_enabled=bool(batch_limits.get("max_batch_items")),
            max_batch_items=int(batch_limits.get("max_batch_items", 0) or 0),
            max_batch_chars=int(batch_limits.get("max_batch_chars", 0) or 0),
            max_concurrency=getattr(provider, "max_concurrency", None),
            context_window=int(getattr(provider, "context_window", 0) or 0),
            languages=tuple(getattr(provider, "supported_languages", ()) or ()),
            latency_profile=getattr(provider, "latency_profile", "standard"),
        )