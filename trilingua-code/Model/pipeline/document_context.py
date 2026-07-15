# -*- coding: utf-8 -*-
"""
Document Context.

A shared context object that flows through the entire translation pipeline.
Every pipeline stage receives and can contribute to the same context.

Consolidates what was previously scattered global state:
- Processing mode configuration
- Document profile (from analyzer)
- Document memory (terminology, entities, abbreviations)
- Translation cache
- Layout plan
- Statistics and warnings
- Performance metrics

This avoids passing multiple separate objects through the pipeline
and provides a single source of truth for pipeline state.
"""

from dataclasses import dataclass, field
from typing import Any

from config.processing_modes import ProcessingMode
from document.document_analyzer import DocumentProfile
from memory.document_memory import DocumentMemory
from memory.translation_cache import TranslationCache


@dataclass
class DocumentContext:
    """Shared context for a single document translation.

    Created at the start of DocumentPipeline.translate() and passed
    through all pipeline stages. Cleared after the document is complete.

    All fields are optional — the pipeline works correctly even if
    some AI-assisted features are disabled.
    """

    # ── Configuration ─────────────────────────────────────────────────────
    mode: ProcessingMode = field(default_factory=lambda: None)  # type: ignore

    # ── Analysis Results ──────────────────────────────────────────────────
    document_profile: DocumentProfile | None = None

    # ── Memory ────────────────────────────────────────────────────────────
    document_memory: DocumentMemory | None = None
    translation_cache: TranslationCache | None = None

    # ── Layout ────────────────────────────────────────────────────────────
    layout_plan: Any | None = None  # LayoutPlan (Phase 8)

    # ── Statistics ────────────────────────────────────────────────────────
    total_blocks: int = 0
    total_chunks: int = 0
    translated_chunks: int = 0
    retranslated_chunks: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    # ── Warnings ──────────────────────────────────────────────────────────
    warnings: list[str] = field(default_factory=list)

    # ── Performance ───────────────────────────────────────────────────────
    extraction_time_ms: float = 0.0
    analysis_time_ms: float = 0.0
    translation_time_ms: float = 0.0
    reconstruction_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # ── Source Info ───────────────────────────────────────────────────────
    source_file: str = ""
    source_format: str = ""
    source_lang: str = ""
    target_lang: str = ""

    # ── Provider Info ─────────────────────────────────────────────────────
    provider_name: str = ""
    provider_model: str = ""

    # ── Internal State ────────────────────────────────────────────────────
    _start_time: float = 0.0  # time.monotonic() at creation

    def start_timer(self) -> None:
        """Start the overall document timer."""
        import time
        self._start_time = time.monotonic()

    def stop_timer(self) -> float:
        """Stop the overall document timer and return elapsed ms."""
        import time
        if self._start_time > 0:
            elapsed = (time.monotonic() - self._start_time) * 1000
            self.total_time_ms = elapsed
            return elapsed
        return 0.0

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)

    def add_chunk_stat(self, translated: bool = True, retranslated: bool = False) -> None:
        """Record a chunk translation statistic."""
        self.total_chunks += 1
        if translated:
            self.translated_chunks += 1
        if retranslated:
            self.retranslated_chunks += 1

    def cache_stat(self, hit: bool) -> None:
        """Record a cache hit or miss."""
        if hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

    def summary(self) -> dict[str, Any]:
        """Return a summary dict for logging and API responses."""
        return {
            "mode": self.mode.name if self.mode else "fast",
            "document_type": self.document_profile.document_type
                            if self.document_profile else "unknown",
            "total_blocks": self.total_blocks,
            "total_chunks": self.total_chunks,
            "translated_chunks": self.translated_chunks,
            "retranslated_chunks": self.retranslated_chunks,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "warnings": len(self.warnings),
            "extraction_time_ms": round(self.extraction_time_ms, 1),
            "analysis_time_ms": round(self.analysis_time_ms, 1),
            "translation_time_ms": round(self.translation_time_ms, 1),
            "reconstruction_time_ms": round(self.reconstruction_time_ms, 1),
            "total_time_ms": round(self.total_time_ms, 1),
            "provider": self.provider_name,
            "model": self.provider_model,
        }

    def log_summary(self) -> None:
        """Print a formatted summary to stdout."""
        s = self.summary()
        print(f"\n{'='*60}")
        print(f"  Document Translation Summary")
        print(f"{'='*60}")
        print(f"  Mode:           {s['mode']}")
        print(f"  Type:           {s['document_type']}")
        print(f"  Format:         {self.source_format}")
        print(f"  Language:       {self.source_lang} → {self.target_lang}")
        print(f"  Provider:       {s['provider']} ({s['model']})")
        print(f"  Blocks:         {s['total_blocks']}")
        print(f"  Chunks:         {s['total_chunks']}")
        print(f"  Retranslations: {s['retranslated_chunks']}")
        print(f"  Cache:          {s['cache_hits']} hits / {s['cache_misses']} misses")
        print(f"  Warnings:       {s['warnings']}")
        print(f"  ── Timing ──")
        print(f"  Extraction:     {s['extraction_time_ms']:.0f}ms")
        print(f"  Analysis:       {s['analysis_time_ms']:.0f}ms")
        print(f"  Translation:    {s['translation_time_ms']:.0f}ms")
        print(f"  Reconstruction: {s['reconstruction_time_ms']:.0f}ms")
        print(f"  Total:          {s['total_time_ms']:.0f}ms")
        print(f"{'='*60}\n")