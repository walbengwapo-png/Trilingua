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

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from config.processing_modes import ProcessingMode
from document.document_analyzer import DocumentProfile
from memory.document_memory import DocumentMemory
from cache.sqlite_cache import SQLiteTranslationCache


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
    translation_cache: SQLiteTranslationCache | None = None

    # ── Layout ────────────────────────────────────────────────────────────
    layout_plan: Any | None = None  # LayoutPlan (Phase 8)

    # ── Prepass Result (Task 5) ───────────────────────────────────────────
    prepass_summary: str = ""
    prepass_domain: str = ""
    prepass_terms: list[tuple[str, str]] = field(default_factory=list)

    # ── Statistics ────────────────────────────────────────────────────────
    total_blocks: int = 0
    total_chunks: int = 0
    translated_chunks: int = 0
    retranslated_chunks: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    # OPTIMIZATION: New stats for async/batching/passthrough (Tasks 1, 3, 4)
    blocks_translated: int = 0       # Blocks actually sent to provider
    blocks_cached: int = 0           # Blocks served from cache
    blocks_batched: int = 0          # Blocks in batches
    blocks_passthrough: int = 0      # Untranslatable blocks skipped
    concurrency_level: int = 1       # Concurrency used (from env var)

    # Phase D Tier 3a: Deferred reviews for batched AI quality review
    # List of (block_index, source_text, translated_text, context_hint, document_type)
    deferred_reviews: list[tuple[int, str, str, str, str]] = field(default_factory=list)

    # Admin review support: per-block AI quality review results.
    # Mapping block_index -> {"score": float, "issues": [QualityIssue-dict]}.
    # Surfaced from the AI quality reviewer's in-memory output — never recomputed.
    block_quality: dict[int, dict] = field(default_factory=dict)

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

    # ── Profiling ─────────────────────────────────────────────────────────
    llm_calls: int = 0                    # Total LLM API calls
    llm_total_time_ms: float = 0.0        # Total time spent in LLM calls
    phase_times: dict[str, float] = field(default_factory=dict)   # phase_name → elapsed ms
    phase_llm_calls: dict[str, int] = field(default_factory=dict) # phase_name → LLM call count
    _current_phase: str = ""              # Active phase name for call counting

    # ── Provider Info ─────────────────────────────────────────────────────
    provider_name: str = ""
    provider_model: str = ""

    # ── Internal State ────────────────────────────────────────────────────
    _start_time: float = 0.0       # time.perf_counter() at creation
    _llm_lock: threading.Lock = field(default_factory=threading.Lock)

    def start_timer(self) -> None:
        """Start the overall document timer."""
        import time
        self._start_time = time.perf_counter()

    def stop_timer(self) -> float:
        """Stop the overall document timer and return elapsed ms."""
        import time
        if self._start_time > 0:
            elapsed = (time.perf_counter() - self._start_time) * 1000
            self.total_time_ms = elapsed
            return elapsed
        return 0.0

    def enter_phase(self, name: str) -> None:
        """Mark the start of a pipeline phase for profiling.

        Thread-safe — uses the same internal lock as record_llm_call.
        """
        with self._llm_lock:
            self._current_phase = name
            if name not in self.phase_times:
                self.phase_times[name] = 0.0
            if name not in self.phase_llm_calls:
                self.phase_llm_calls[name] = 0

    def defer_review(self, block_index: int, source: str, translation: str,
                     context_hint: str = "", document_type: str = "") -> None:
        """Defer a quality review for batched processing.

        Thread-safe — uses the same internal lock as record_llm_call.
        """
        with self._llm_lock:
            self.deferred_reviews.append(
                (block_index, source, translation, context_hint, document_type)
            )

    @staticmethod
    def _issue_to_dict(i) -> dict:
        """Normalize a QualityIssue dataclass (or dict) to a plain dict.

        Branch on type instead of relying on ``getattr(..., default)`` —
        Python evaluates the default argument eagerly, so calling
        ``getattr(i, "severity", i.get("severity"))`` would crash on a
        dataclass (which has no ``.get`` method).
        """
        fields = ("severity", "category", "description",
                  "source_snippet", "translation_snippet")
        if isinstance(i, dict):
            return {f: i.get(f, "") for f in fields}
        return {f: getattr(i, f, "") for f in fields}

    def record_block_quality(self, block_index: int, score: float,
                             issues: list) -> None:
        """Record the AI quality review for a single block.

        Thread-safe — uses the same internal lock as record_llm_call.
        Stores a plain-dict snapshot so it can be serialized into the
        regeneration sidecar and persisted by Laravel.

        Args:
            block_index: Index of the block within the document.
            score: Quality score (0.0 - 100.0).
            issues: Iterable of QualityIssue dataclasses (or dicts).
        """
        with self._llm_lock:
            self.block_quality[block_index] = {
                "score": round(float(score), 1),
                "issues": [self._issue_to_dict(i) for i in (issues or [])],
            }

    def record_llm_call(self, elapsed_ms: float) -> None:
        """Record an LLM API call and its duration.

        Thread-safe — uses an internal lock to protect counters.

        Args:
            elapsed_ms: Wall-clock time spent in the LLM call.
        """
        with self._llm_lock:
            self.llm_calls += 1
            self.llm_total_time_ms += elapsed_ms
            phase = self._current_phase or "uncategorized"
            self.phase_llm_calls[phase] = self.phase_llm_calls.get(phase, 0) + 1

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
            # OPTIMIZATION: New stats in summary (Tasks 1, 3, 4)
            "blocks_translated": self.blocks_translated,
            "blocks_cached": self.blocks_cached,
            "blocks_batched": self.blocks_batched,
            "blocks_passthrough": self.blocks_passthrough,
            "concurrency_level": self.concurrency_level,
            # PROFILING
            "llm_calls": self.llm_calls,
            "llm_total_time_ms": round(self.llm_total_time_ms, 1),
            "phase_times": {k: round(v, 1) for k, v in sorted(self.phase_times.items())},
            "phase_llm_calls": dict(sorted(self.phase_llm_calls.items())),
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
        # OPTIMIZATION: New stats in log (Tasks 1, 3, 4)
        print(f"  Translated:     {s['blocks_translated']} blocks to API")
        print(f"  Cached:         {s['blocks_cached']} blocks from cache")
        print(f"  Batched:        {s['blocks_batched']} blocks in batches")
        print(f"  Passthrough:    {s['blocks_passthrough']} blocks skipped")
        print(f"  Concurrency:    {s['concurrency_level']}")
        print(f"  Warnings:       {s['warnings']}")
        # PROFILING
        print(f"  LLM Calls:      {s['llm_calls']} ({s['llm_total_time_ms']:.0f}ms)")
        if s['phase_times']:
            print(f"  ── Phase Times ──")
            for phase, elapsed_ms in s['phase_times'].items():
                phase_calls = s['phase_llm_calls'].get(phase, 0)
                marker = f"  [{phase_calls} LLM]" if phase_calls else ""
                print(f"  {phase:16s} {elapsed_ms:>8.0f}ms  {marker}")
        print(f"  ── Timing ──")
        print(f"  Extraction:     {s['extraction_time_ms']:.0f}ms")
        print(f"  Analysis:       {s['analysis_time_ms']:.0f}ms")
        print(f"  Translation:    {s['translation_time_ms']:.0f}ms")
        print(f"  Reconstruction: {s['reconstruction_time_ms']:.0f}ms")
        print(f"  Total:          {s['total_time_ms']:.0f}ms")
        print(f"{'='*60}\n")