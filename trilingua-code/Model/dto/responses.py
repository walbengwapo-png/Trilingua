# -*- coding: utf-8 -*-
"""
Translation response DTOs.

These models define the output contracts for all translation operations.
Every provider must return these exact DTOs — no provider-specific fields.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class TranslationResponse:
    """Normalized response from any translation provider."""
    translated_text: str
    provider: str = ""           # e.g. "gptoss", "mistral"
    model: str = ""              # e.g. "gpt-oss:20b-cloud", "mistral-small-latest"
    token_usage: dict = field(default_factory=dict)  # {"input": N, "output": N}
    execution_time_ms: float = 0.0
    warnings: list = field(default_factory=list)
    success: bool = True
    error_message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DocumentTranslationResponse:
    """Response from a full document translation."""
    output_path: str
    translated_blocks: list = field(default_factory=list)
    provider: str = ""
    model: str = ""
    total_chunks: int = 0
    total_execution_time_ms: float = 0.0
    token_usage: dict = field(default_factory=dict)
    bleu_score: Optional[float] = None
    warnings: list = field(default_factory=list)
    success: bool = True
    error_message: str = ""
    mode: str = "balanced"
    document_type: str = ""
    quality_score: Optional[float] = None
    cache_hits: int = 0
    # Admin review support: serialized block set + structural metadata that
    # allows reconstruction-only regeneration later. Populated only when the
    # document path produced per-block data.
    sidecar: Optional[dict] = None
    blocks: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HealthResponse:
    """Health check response."""
    status: str = "ok"
    engine: str = ""
    model: str = ""
    languages: list = field(default_factory=list)
    formats: list = field(default_factory=list)
    providers: list = field(default_factory=list)
    active_provider: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChunkResult:
    """Result of processing a single document chunk."""
    index: int
    original_text: str
    translated_text: str
    block_type: str = "paragraph"
    token_count: int = 0
    execution_time_ms: float = 0.0
    warnings: list = field(default_factory=list)