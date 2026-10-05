# -*- coding: utf-8 -*-
"""
Translation pipeline.

Orchestrates the translation flow:
1. Language detection
2. Metadata extraction
3. Semantic chunking (Phase 3 — when enabled)
4. Context building from DocumentMemory (Phase 2 — when enabled)
5. Terminology lookup
6. Translation via provider
7. Translation validation (regex + AI review Phase 5)
8. Translation Cache (Phase 6 — when enabled)
9. Consistency check

The provider is only one step in this pipeline.
The pipeline controls everything.

Backward compatible: all new parameters default to None/False,
preserving original behavior when not used.

OPTIMIZATIONS (Tasks 1-4):
- Task 1: Concurrent block translation with ThreadPoolExecutor
- Task 2: Persistent SQLite cache integration
- Task 3: Short block batching (group <80 token blocks into batches of 5)
- Task 4: Pre-filter untranslatable blocks (numbers, URLs, etc.)

FIX: Replaced asyncio with ThreadPoolExecutor to avoid nested event loop
errors in FastAPI's async context. ThreadPoolExecutor is the correct tool
for parallelizing synchronous HTTP calls (blocking I/O). (Task 1 fix)
"""

import json
import os
import re
import time
from contextlib import contextmanager
from provider_usage import submit_with_usage
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable


@contextmanager
def _nullcontext():
    """No-op context manager for conditional profiling."""
    yield

from dto.requests import TranslationRequest, LANGUAGES, CODE_TO_LANG
from dto.responses import TranslationResponse, ChunkResult
from providers.base import TranslationProvider
from .fair_scheduler import document_batch_scheduler
from document.chunker import ChunkSplitter
from document.semantic_chunker import SemanticChunker, SemanticChunk
from document.document_analyzer import DocumentProfile
from memory.terminology import ContextBuffer
from memory.glossary import GlossaryStore
from memory.document_memory import DocumentMemory
from cache.sqlite_cache import SQLiteTranslationCache
from validators.hallucination_detector import (sanitize_translation, detect_hallucination,
                                               translation_content_issue)
from validators.translation_validator import BLEUReporter
from validators.ai_quality_reviewer import AIQualityReviewer
from config.processing_modes import ProcessingMode
from .phase_profiler import llm_call_profile
from .unit_adapters import (build_provider_hint, to_unit_list, unit_to_block,
                            translate_many_units)
from dto.pipeline import TranslationUnitResult
from document.map import build_document_map
from document.protected_spans import restore_protected_spans
from document.layout_preflight import preflight_units

# OPTIMIZATION: Env var defaults (Tasks 1, 3, 4)
# gptoss: 8 parallel calls (matches GPTOSSProvider._POOL_SIZE=8). Batching now
# packs many blocks into few requests, so parallelism overlaps the remaining
# long-block calls. Gemini has its own conservative concurrency cap below to
# reduce 429 responses on shared API quotas.
# Tunable per environment via TRANSLATION_CONCURRENCY.
_TRANSLATION_CONCURRENCY = int(os.environ.get("TRANSLATION_CONCURRENCY", "8"))
_TRANSLATION_BATCH_ENABLED = os.environ.get("TRANSLATION_BATCH_ENABLED", "true").lower() == "true"
_TRANSLATION_CACHE_ENABLED = os.environ.get("TRANSLATION_CACHE_ENABLED", "true").lower() == "true"
_TRANSLATION_CACHE_TTL_DAYS = int(os.environ.get("TRANSLATION_CACHE_TTL_DAYS", "30"))
_TRANSLATION_PROMPT_VERSION = os.environ.get(
    "TRANSLATION_PROMPT_VERSION", "2026-09-reference-gemini-v2"
)

# Phase D Tier 3a: Batched AI quality review (default on)
# All translations complete first, then quality review runs
# in a single AI call instead of one per chunk. ~58% faster than per-chunk
# review with identical detection quality (verified empirically).
_TRANSLATION_BATCHED_REVIEW = os.environ.get(
    "TRANSLATION_BATCHED_REVIEW", "true"
).lower() == "true"

# Phase D Tier 3b: Chunk size for text splitting (tokens per chunk)
# Default 400. Larger chunks = fewer LLM calls but more context per call.
_TRANSLATION_MAX_TOKENS = int(os.environ.get("TRANSLATION_MAX_TOKENS", "400"))

# OPTIMIZATION: Provider-aware batching limits (Tier 2b)
# gptoss: 2000/8 -> 4000/12 (larger batches = fewer LLM calls per document;
# the batch is one HTTP request, so bigger batches cut round-trip overhead).
# gemini: 4000/12 -> 6000/16 (large context window and fewer round trips).
_PROVIDER_BATCH_LIMITS = {
    "gptoss": {"max_batch_chars": 4000, "max_batch_items": 12},
    "gemini": {"max_batch_chars": 6000, "max_batch_items": 16},
}
_DEFAULT_BATCH_LIMITS = {"max_batch_chars": 1500, "max_batch_items": 5}

# Provider-neutral unit pipeline (Phases 1-4). Default OFF: the legacy dict
# pipeline remains the production path for one release. When enabled, the
# extractor dict is converted once to TranslationUnit DTOs, the core
# translation/review/layout-preflight stages run DTO-only, and results are
# converted back to legacy-shaped dicts exactly once at the boundary.
#
# IMPORTANT: The flag is read ONCE at process startup (module import time).
# Changing TRANSLATION_UNIT_PIPELINE requires a service restart; it is never
# consulted per document at runtime. Tests that flip it must reload the module
# (or monkeypatch unit_pipeline_enabled) to simulate a restart.
_TRANSLATION_UNIT_PIPELINE = os.environ.get(
    "TRANSLATION_UNIT_PIPELINE", "false"
).lower() == "true"


def unit_pipeline_enabled() -> bool:
    """Return whether the DTO unit pipeline is enabled.

    Captures ``TRANSLATION_UNIT_PIPELINE`` at process startup (module import);
    it is not read from the environment at call time, so enabling it requires
    a service restart. Tests may monkeypatch this function or reload the
    module to exercise the unit route.
    """
    return _TRANSLATION_UNIT_PIPELINE


# OPTIMIZATION: Passthrough filter for untranslatable blocks (Task 4)
# Short words that should always be translated (includes common Cebuano/Filipino particles)
_SHORT_WORD_ALLOWLIST = frozenset({
    "ug", "ang", "sa", "ka", "na", "pa", "ba", "ni", "si", "ng",
    "ma", "da", "ja", "ne", "se", "to", "in", "on", "at", "or",
    "an", "is", "it", "as", "be", "by", "he", "my", "no", "of",
    "ok", "so", "up", "us", "we", "do", "go",
})


def _is_passthrough_block(text: str) -> tuple[bool, str]:
    """Check if a block should skip translation entirely.

    Returns (should_skip: bool, reason: str).
    Blocks matching any criterion are passed through untranslated.
    """
    stripped = text.strip()

    if stripped.lower() in {"english", "cebuano", "filipino", "tagalog"}:
        return True, "language_name"

    # Under 2 characters — always skip (single char can't be meaningful alone)
    if len(stripped) < 2:
        return True, "too_short"

    # Exactly 2 characters — allowlist check OR contains at least one letter
    # (Relaxed: allow 2-char text with letters like "Oh", "Hi", "No" for story books)
    if len(stripped) < 3:
        if stripped.lower() in _SHORT_WORD_ALLOWLIST:
            return False, ""
        # Allow if it contains at least one letter (catches "Oh!", "Hi", "No", etc.)
        if re.search(r'[a-zA-Z]', stripped):
            return False, ""
        return True, "too_short"

    # Entirely punctuation or whitespace
    if re.fullmatch(r'[\s\W]+', stripped):
        return True, "punctuation_only"

    # Pure numbers (with optional separators)
    if re.fullmatch(r'\d+[\s.,/]*\d*', stripped):
        return True, "pure_number"

    # Date patterns (common formats)
    date_patterns = [
        r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$',  # 01/15/2024, 01-15-24
        r'^\d{4}[/-]\d{1,2}[/-]\d{1,2}$',     # 2024-01-15
        r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}$',
        r'^\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}$',
    ]
    for pat in date_patterns:
        if re.match(pat, stripped, re.IGNORECASE):
            return True, "date"

    # URLs
    if stripped.lower().startswith(('http://', 'https://', 'www.')):
        return True, "url"

    # Email addresses
    if re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', stripped):
        return True, "email"

    # File paths (Windows or Unix)
    if re.match(r'^[a-zA-Z]:\\', stripped) or stripped.startswith('/'):
        if re.search(r'\\|/', stripped) and '.' in stripped:
            return True, "file_path"

    return False, ""


# ── Echo-output detection ─────────────────────────────────────────────────
# A provider "succeeds" with the source text unchanged (echo output). If such
# output is cached it gets pinned for the cache TTL, so it must be detected
# before caching and retried instead.

def _normalize_for_compare(text: str) -> str:
    """Collapse whitespace + lowercase for echo comparison."""
    return re.sub(r"\s+", " ", text.strip()).lower()


def _has_translatable_content(text: str, block_type: str = "") -> bool:
    """Best-effort: would this source text actually change when translated?

    Returns False (i.e. "nothing to flag") for content that legitimately
    maps to itself: numbers, dates, URLs, emails, file paths, punctuation,
    single tokens, and proper-noun/acronym-like strings (no/one lowercase
    token). This prevents false-positive echo flags on correct output such
    as a proper noun the model kept identical.
    """
    stripped = text.strip()
    if not stripped or len(stripped) < 3:
        return False
    if re.fullmatch(r"[\s\W]+", stripped):
        return False
    if re.fullmatch(r"\d+[\s.,/]*\d*", stripped):
        return False
    if stripped.lower().startswith(("http://", "https://", "www.")):
        return False
    if re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", stripped):
        return False
    tokens = stripped.split()
    if len(tokens) < 2:
        return False
    # Generic multi-word Title Case headings are commonly echoed as if they
    # were names. Give them one explicit retry. Two-token names and honorific
    # forms such as "Dr. Santos" remain protected.
    if block_type in {"heading", "header", "title"} and len(tokens) >= 3:
        words = [re.sub(r"^[^A-Za-z]+|[^A-Za-z]+$", "", token) for token in tokens]
        if words and all(word and word[0].isupper() for word in words):
            return True
    # Require at least two tokens that start lowercase — real sentence words.
    # Title-Case proper nouns ("Dr. Santos", "National Gallery"), all-caps
    # acronyms ("AI"), and mixed proper-noun phrases contribute no lowercase-
    # initial tokens and are therefore NOT flagged as echo output.
    content_tokens = [t for t in tokens if t[0].islower()]
    return len(content_tokens) >= 2


def _is_echo_output(source_text: str, translated_text: str,
                    block_type: str = "", source_lang: str = "",
                    target_lang: str = "") -> bool:
    """True when the 'translation' is effectively the source, unchanged.

    Only flagged for text with real translatable content; proper nouns,
    numbers, acronyms, and very short strings legitimately translate to
    themselves and are excluded. When the source and target language are the
    same, identity is the correct outcome and is never flagged.
    """
    if source_lang and target_lang and source_lang.lower() == target_lang.lower():
        return False
    return (
        _has_translatable_content(source_text, block_type)
        and _normalize_for_compare(source_text) == _normalize_for_compare(translated_text)
    )


def _partition_units_by_group(work_units, semantic_units) -> list:
    """Partition work units into translate_many batches by semantic group.

    Semantic chunks are used ONLY as context and batch boundaries — they never
    combine multiple units into one output block. Units without a semantic
    group form a trailing batch. Batches are ordered by their first member's
    block index so the provider also receives the units in reading order.
    ``semantic_units`` maps source_block_id -> SemanticChunk.
    """
    buckets: dict = {}
    ungrouped = []
    for unit in work_units:
        chunk = semantic_units.get(unit.source_block_id)
        if chunk is None:
            ungrouped.append(unit)
        else:
            buckets.setdefault(id(chunk), []).append(unit)
    keyed = [(min(u.source_block_id for u in group), group)
             for group in buckets.values()]
    if ungrouped:
        keyed.append((min(u.source_block_id for u in ungrouped), ungrouped))
    keyed.sort(key=lambda item: item[0])
    return [group for _, group in keyed]


# Mirrors the legacy worker's provider_outage markers. A provider-wide outage
# (rate limit, timeout, connection, 5xx) must surface as a hard failure — never
# as quietly-retained source text. Returns the message when the exception looks
# systemic, otherwise "".
_PROVIDER_OUTAGE_MARKERS = (
    "rate limit", "timed out", "cannot connect",
    "connection", "provider failed", "unavailable",
)


def _systemic_failure_message(exc: Exception) -> str:
    message = str(exc)
    if any(marker in message.lower() for marker in _PROVIDER_OUTAGE_MARKERS):
        return message
    return ""


# OPTIMIZATION: Batch prompt builder (Task 3)
def _build_batch_prompt(entries: list[tuple[int, str]],
                        source_lang: str, target_lang: str,
                        provider_name: str = "") -> str:
    """Build a batched translation prompt for multiple short blocks.

    Uses [BLOCK_N] prefix to avoid collision with numbered-list content
    that may contain bare [N] patterns.

    Args:
        entries: List of (index, text) tuples to translate.
        source_lang: Source language name.
        target_lang: Target language name.
        provider_name: Provider name for provider-aware limits.

    Returns:
        A prompt string that requests JSON output.
    """
    lines = []
    for idx, text in entries:
        lines.append(f"[BLOCK_{idx}] {text}")

    example = ", ".join(f'"{idx}": "..."' for idx, _ in entries[:3])

    limit = _PROVIDER_BATCH_LIMITS.get(provider_name, _DEFAULT_BATCH_LIMITS)
    max_chars = limit["max_batch_chars"]

    return (
        f"Translate each entry from {source_lang} to {target_lang} independently. "
        f"Return ONLY one valid JSON object, no preamble, no explanation. "
        f"Use every exact BLOCK number as a key and omit none.\n"
        f"{{{example}}}\n\n"
        f"Entries (max {max_chars} chars total):\n" + "\n".join(lines)
    )


def _parse_batch_response(response_text: str,
                          expected_indices: list[int]) -> dict[int, str]:
    """Parse a batched response back into individual translations.

    Tries in order:
    1. Direct JSON parse (keys are string indices)
    2. JSON inside markdown code block
    3. Newline-delimited [BLOCK_N] format (fallback for non-JSON responses)

    Args:
        response_text: The raw response text from the provider.
        expected_indices: The list of expected entry indices.

    Returns:
        Dict mapping index -> translated_text.
        On failure, returns empty dict (caller falls back to individual).
    """
    result = {}

    # 1. Try direct JSON parse
    try:
        data = json.loads(response_text)
        if isinstance(data, dict):
            for idx in expected_indices:
                key = str(idx)
                if key in data and isinstance(data[key], str):
                    result[idx] = data[key]
            if len(result) == len(expected_indices):
                return result
    except (json.JSONDecodeError, TypeError):
        result = {}

    # 2. Try extracting JSON from markdown code block
    json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if isinstance(data, dict):
                result = {}
                for idx in expected_indices:
                    key = str(idx)
                    if key in data and isinstance(data[key], str):
                        result[idx] = data[key]
                if len(result) == len(expected_indices):
                    return result
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. Try newline-delimited [BLOCK_N] format
    # Pattern matches: [BLOCK_123] translated text here
    # Each block entry is on its own line
    block_patterns = re.findall(
        r'\[BLOCK_(\d+)\]\s*(.+?)(?=\n\[BLOCK_|\Z)',
        response_text, re.DOTALL
    )
    if block_patterns:
        parsed = {}
        for idx_str, text in block_patterns:
            idx = int(idx_str)
            text = text.strip()
            # Remove trailing artifacts
            text = re.sub(r'\n+', ' ', text)
            if text:
                parsed[idx] = text

        if len(parsed) >= len(expected_indices):
            return parsed
        # Partial match still usable
        if parsed:
            result.update(parsed)

    return result


# ── Paragraph-aware chunking + rejoin (Phase 4: coherence) ────────────────
# Chunking on sentence boundaries alone destroys paragraph structure: every
# chunk is rejoined with a single space, so blank lines between paragraphs
# collapse. For Cebuano/Filipino this matters — pronoun and verb-focus flow
# read across paragraph boundaries. These helpers split on blank lines first
# and rejoin with real paragraph breaks.

_PARA_SEP_RE = re.compile(r"\n[ \t]*\n")


def _paragraph_boundaries(text: str) -> list[str]:
    """Split text into paragraphs on blank lines (interior newlines kept)."""
    return [p.strip("\n") for p in _PARA_SEP_RE.split(text) if p.strip("\n")]


def _chunk_preserving_paragraphs(text: str, max_tokens: int,
                                 splitter) -> list[tuple[int, str]]:
    """Chunk *text* so no chunk mixes paragraphs.

    Returns a list of (paragraph_id, chunk_text) tuples. Paragraphs longer
    than *max_tokens* are sub-split by *splitter* at sentence boundaries and
    keep the same paragraph_id.
    """
    paragraphs = _paragraph_boundaries(text)
    if len(paragraphs) <= 1:
        return [(0, c) for c in splitter.split(text, max_tokens=max_tokens)]
    chunks: list[tuple[int, str]] = []
    for pid, paragraph in enumerate(paragraphs):
        if len(paragraph.split()) > max_tokens:
            for sub in splitter.split(paragraph, max_tokens=max_tokens):
                chunks.append((pid, sub))
        else:
            chunks.append((pid, paragraph))
    return chunks


def _rejoin_paragraph_aware(translated_chunks: list[tuple[int, str]]) -> str:
    """Rejoin translated chunks, restoring a blank line where the chunk
    boundary fell between paragraphs and a single space within a paragraph."""
    parts = []
    last_pid = None
    for pid, text in translated_chunks:
        t = text.strip()
        if not t:
            continue
        if parts:
            parts.append(("\n\n" if pid != last_pid else " ") + t)
        else:
            parts.append(t)
        last_pid = pid
    return "".join(parts).strip()


class TranslationPipeline:
    """Orchestrates the complete translation process."""

    def __init__(self, provider: TranslationProvider):
        self.provider = provider
        self.chunk_splitter = ChunkSplitter()  # Kept for fallback
        self.bleu_reporter = BLEUReporter()

        # OPTIMIZATION: Shared SQLite cache instance (Task 2)
        self._shared_cache: SQLiteTranslationCache | None = None

    def concurrency_limit(self) -> int:
        """Return the actual per-document provider worker limit."""
        concurrency = max(1, _TRANSLATION_CONCURRENCY)
        provider_cap = getattr(self.provider, "max_concurrency", None)
        return min(concurrency, provider_cap) if provider_cap else concurrency

    @staticmethod
    def _record_provider_response(ctx, response: TranslationResponse) -> None:
        if ctx and response:
            ctx.record_provider(response.provider, response.model)

    def _get_cache(self) -> SQLiteTranslationCache | None:
        """Get or create the shared SQLite cache."""
        if self._shared_cache is None and _TRANSLATION_CACHE_ENABLED:
            namespace = "|".join((
                _TRANSLATION_PROMPT_VERSION,
                self.provider.name,
                self.provider.model_name,
            ))
            self._shared_cache = SQLiteTranslationCache(
                ttl_days=_TRANSLATION_CACHE_TTL_DAYS,
                enabled=_TRANSLATION_CACHE_ENABLED,
                namespace=namespace,
            )
        return self._shared_cache

    def store_translation(self, source_text: str, source_lang: str,
                          target_lang: str, translated_text: str,
                          block_type: str = "paragraph") -> None:
        """Replace the cached value with a reviewed/repaired translation."""
        cache = self._get_cache()
        if cache and translated_text and not translation_content_issue(source_text, translated_text) and not _is_echo_output(
            source_text, translated_text, block_type, source_lang, target_lang
        ):
            cache.put(
                source_text, target_lang, self.provider.name, translated_text,
                source_lang=source_lang,
            )

    def _translate_with_echo_guard(self, *, text: str, source_lang: str,
                                   target_lang: str, block_type: str,
                                   context_hint: str, document_type: str,
                                   ctx=None) -> TranslationResponse:
        """Call the provider, retrying once if the output merely echoes input.

        A provider can return success=True with the source text unchanged
        (echo output). Caching that would pin a bad translation for the cache
        TTL, so we detect it here: retry once with an explicit anti-echo
        instruction, and if the retry still echoes, return a failure response
        (the caller must not cache it).

        Content with no translatable material (proper nouns, numbers, URLs,
        etc.) is excluded by _is_echo_output, so correct identity translations
        are never retried or failed.
        """
        # Reject invalid content on every provider route, including repairs.
        # Existing echo handling below remains separate: identity can be valid.
        def checked_call(call, hint):
            result = call(text=text, source_lang=source_lang, target_lang=target_lang,
                          block_type=block_type, context_hint=hint,
                          document_type=document_type)
            self._record_provider_response(ctx, result)
            if result.success:
                issue = translation_content_issue(text, result.translated_text)
                if issue:
                    result.success = False
                    result.error_message = issue
                    result.translated_text = ""
            return result

        response = checked_call(self.provider.translate, context_hint)
        if not response.success and response.error_message.startswith(
                ("Conversational response", "Missing protected content", "Empty translation")):
            hint = (f"{context_hint}\nPrevious output was invalid: {response.error_message}. "
                    "Return only the translated document text; preserve every URL, number, "
                    "and placeholder exactly. Do not ask for input or add commentary.")
            with llm_call_profile(ctx) if ctx else _nullcontext():
                response = checked_call(self.provider.translate, hint)
            if not response.success:
                secondary = getattr(self.provider, "translate_secondary", None)
                if callable(secondary):
                    with llm_call_profile(ctx) if ctx else _nullcontext():
                        response = checked_call(secondary, hint)
            return response

        if response.success and _is_echo_output(
            text, response.translated_text, block_type, source_lang, target_lang
        ):
            if ctx:
                ctx.echo_retries += 1
            with llm_call_profile(ctx) if ctx else _nullcontext():
                retry_hint = (
                    f"{context_hint}\n"
                    f"Previous attempt did not translate — do NOT echo the "
                    f"input back. Translate the text into {target_lang}."
                ).strip()
                retry_response = self.provider.translate(
                    text=text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    block_type=block_type,
                    context_hint=retry_hint,
                    document_type=document_type,
                )
            self._record_provider_response(ctx, retry_response)
            if retry_response.success and translation_content_issue(text, retry_response.translated_text):
                retry_response.success = False
                retry_response.error_message = translation_content_issue(text, retry_response.translated_text)
                retry_response.translated_text = ""
            if retry_response.success and not _is_echo_output(
                text, retry_response.translated_text, block_type,
                source_lang, target_lang,
            ):
                response = retry_response
            elif retry_response.success:
                if block_type in {"heading", "header", "title"}:
                    retry_response.warnings.append(
                        "Title Case heading remained unchanged after retry; "
                        "quality review will determine whether it is a proper name."
                    )
                    response = retry_response
                else:
                    # An echo is semantically invalid but does not mean the
                    # primary is unavailable. Route this one block directly
                    # to the serialized backup without opening its cooldown.
                    secondary = getattr(self.provider, "translate_secondary", None)
                    if callable(secondary):
                        if ctx:
                            ctx.semantic_fallbacks += 1
                        with llm_call_profile(ctx) if ctx else _nullcontext():
                            fallback_response = secondary(
                                text=text, source_lang=source_lang,
                                target_lang=target_lang, block_type=block_type,
                                context_hint=retry_hint, document_type=document_type,
                            )
                        self._record_provider_response(ctx, fallback_response)
                        if fallback_response.success and translation_content_issue(text, fallback_response.translated_text):
                            fallback_response.success = False
                            fallback_response.error_message = translation_content_issue(text, fallback_response.translated_text)
                            fallback_response.translated_text = ""
                        if (fallback_response.success and not _is_echo_output(
                                text, fallback_response.translated_text, block_type,
                                source_lang, target_lang)):
                            fallback_response.warnings.append(
                                "Primary echoed source after retry; semantic fallback succeeded."
                            )
                            return fallback_response
                        if not fallback_response.success:
                            return fallback_response

                    # Both the primary (after retry) and the semantic fallback
                    # returned the source unchanged. For a handful of blocks this
                    # is normally correct — the text is already in the target
                    # language or contains nothing translatable. Keep the source
                    # and surface a warning instead of failing the whole doc.
                    warning = (
                        "Source echoed unchanged after primary retry and semantic "
                        f"fallback; kept as-is (likely already in {target_lang} "
                        "or untranslatable). Verify output."
                    )
                    print(f"  ⚠️  Provider echoed source unchanged after retry; "
                          f"keeping text as-is ({target_lang})")
                    if ctx:
                        ctx.add_warning(warning)
                    return TranslationResponse(
                        translated_text=text, provider=self.provider.name,
                        model=self.provider.model_name, token_usage={},
                        execution_time_ms=0.0, success=True, warnings=[warning],
                    )
            else:
                return retry_response

        return response

    def translate(self, request: TranslationRequest,
                  context_buffer: ContextBuffer | None = None) -> TranslationResponse:
        """Translate a single text block through the full pipeline.

        The context buffer is scoped PER REQUEST: when none is supplied a fresh
        one is created, so concurrent requests can never leak context into each
        other through the shared pipeline singleton. Callers that want
        within-document context (e.g. translate_chunks) create one buffer and
        thread it through their own translate() calls.

        Args:
            request: The translation request.
            context_buffer: Optional caller-owned ContextBuffer for cross-call
                context hints within a single document/request.

        Returns:
            A normalized TranslationResponse.
        """
        start_time = time.time()

        # 1. Estimate tokens
        estimated_tokens = self.provider.estimate_tokens(request.text)

        # OPTIMIZATION: Persistent cache lookup (mirrors the document/batch
        # paths). Repeated phrases / reviewed-and-fixed blocks are served
        # instantly instead of re-hitting the LLM.
        cache = self._get_cache()
        if cache and request.text and request.text.strip():
            cached = cache.get(
                request.text, request.target_lang, self.provider.name,
                source_lang=request.source_lang,
            )
            if cached is not None and not translation_content_issue(request.text, cached):
                return TranslationResponse(
                    translated_text=cached,
                    provider="cache",
                    model=self.provider.model_name,
                    warnings=["Translation served from the configured provider-chain cache."],
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

        if context_buffer is None:
            context_buffer = ContextBuffer()

        # 2. Build context hint
        context_hint = request.context_hint
        if not context_hint:
            context_hint = context_buffer.get_hint()

        # 3. Translate via provider (pass document_type for specialized prompts)
        response = self._translate_with_echo_guard(
            text=request.text,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            block_type=request.block_type,
            context_hint=context_hint,
            document_type=request.document_type,
        )

        # 4. Push to context buffer on success (for fast mode) and persist
        if response.success and response.translated_text:
            context_buffer.push(response.translated_text)
            self.store_translation(
                request.text, request.source_lang, request.target_lang,
                response.translated_text, request.block_type,
            )

        # 5. Update execution time
        response.execution_time_ms = (time.time() - start_time) * 1000

        return response

    def translate_chunks(self, text: str, source_lang: str, target_lang: str,
                         block_type: str = "paragraph", max_tokens: int = _TRANSLATION_MAX_TOKENS,
                         document_memory: DocumentMemory | None = None,
                         mode: ProcessingMode | None = None,
                         translation_cache: SQLiteTranslationCache | None = None,
                         quality_reviewer: AIQualityReviewer | None = None,
                         document_profile: DocumentProfile | None = None) -> TranslationResponse:
        """Split text into chunks, translate each, and rejoin.

        Supports both naive chunking (fallback) and semantic chunking (Phase 3).

        Args:
            text: Source text.
            source_lang: Source language name.
            target_lang: Target language name.
            block_type: Type of text block.
            max_tokens: Maximum tokens per chunk.
            document_memory: Optional DocumentMemory for context.
            mode: Processing mode configuration.
            translation_cache: Optional SQLiteTranslationCache.
            quality_reviewer: Optional AIQualityReviewer.
            document_profile: Optional DocumentProfile for semantic chunking.

        Returns:
            A combined TranslationResponse.
        """
        # Per-request context buffer (NOT the shared pipeline singleton):
        # threaded into every translate() call so concurrent requests cannot
        # cross-contaminate each other's context.
        buffer = ContextBuffer()

        # Split into chunks preserving paragraph boundaries so the rejoin can
        # restore blank lines between paragraphs (Phase 4: coherence).
        # Each element is (paragraph_id, chunk_text); chunks with the same
        # paragraph_id are sub-pieces of one over-long paragraph.
        chunks: list[tuple[int, str]]

        if mode and mode.semantic_chunking and document_profile and document_profile.is_reliable():
            from document.semantic_chunker import SemanticChunker
            chunker = SemanticChunker(max_tokens=max_tokens)
            # Wrap text as a single block for the chunker
            blocks = [{"text": text, "type": block_type}]
            semantic_chunks = chunker.chunk_blocks(blocks, document_profile)
            chunks = [(i, c.text) for i, c in enumerate(semantic_chunks) if not c.is_code]
        else:
            chunks = _chunk_preserving_paragraphs(text, max_tokens, self.chunk_splitter)

        if len(chunks) <= 1:
            # No splitting needed
            request = TranslationRequest(
                text=text, source_lang=source_lang, target_lang=target_lang,
                block_type=block_type,
                document_type=document_profile.document_type if document_profile else "",
            )
            return self.translate(request, context_buffer=buffer)

        # Translate each chunk
        translated_chunks = []
        total_tokens = {"input": 0, "output": 0}
        total_time = 0.0
        warnings = []
        retranslated_count = 0

        for i, (chunk_pid, chunk_text) in enumerate(chunks):
            # Check cache first
            if translation_cache:
                cached = translation_cache.get(
                    chunk_text, target_lang, self.provider.name,
                    source_lang=source_lang,
                )
                if cached is not None and not translation_content_issue(text, cached):
                    translated_chunks.append((chunk_pid, cached))
                    continue

            # Build context from document memory
            context = ""
            if document_memory:
                context = document_memory.get_context_for_block(
                    {"text": chunk_text, "type": block_type}, i
                )

            request = TranslationRequest(
                text=chunk_text, source_lang=source_lang, target_lang=target_lang,
                block_type=block_type,
                context_hint=context,
                document_type=document_profile.document_type if document_profile else "",
            )

            response = self.translate(request, context_buffer=buffer)

            if response.success:
                translated = response.translated_text

                # AI Quality Review (Phase 5)
                if quality_reviewer and mode and mode.ai_quality_review:
                    review = quality_reviewer.review(
                        source=chunk_text,
                        translation=translated,
                        document_type=document_profile.document_type if document_profile else "",
                    )

                    if quality_reviewer.needs_retranslation(review):
                        # Single retry with review feedback
                        retry_request = TranslationRequest(
                            text=chunk_text, source_lang=source_lang,
                            target_lang=target_lang,
                            block_type=block_type,
                            context_hint=f"{context}\nPrevious issues: {review.summary}",
                            document_type=document_profile.document_type if document_profile else "",
                        )
                        retry_response = self.translate(retry_request, context_buffer=buffer)
                        if retry_response.success:
                            translated = retry_response.translated_text
                            retranslated_count += 1
                            score_note = f"score: {review.score:.1f}" if review.score is not None else "review unavailable"
                            warnings.append(f"Chunk {i + 1} retranslated ({score_note})")

                # Cache the result
                if translation_cache:
                    translation_cache.put(
                        chunk_text, target_lang, self.provider.name,
                        translated, source_lang=source_lang,
                    )

                translated_chunks.append((chunk_pid, translated))
                total_tokens["input"] += response.token_usage.get("input", 0)
                total_tokens["output"] += response.token_usage.get("output", 0)
                total_time += response.execution_time_ms

                # Record in document memory
                if document_memory:
                    document_memory.record_translation(chunk_text, translated, i)
                    document_memory.extract_terms(chunk_text, translated)
                    document_memory.update_abbreviations(chunk_text)
            else:
                warnings.append(f"Chunk {i + 1} failed: {response.error_message}")
                translated_chunks.append((chunk_pid, ""))

        combined_text = _rejoin_paragraph_aware(translated_chunks)

        if retranslated_count > 0:
            print(f"  [Quality] {retranslated_count} chunk(s) retranslated due to low quality scores")

        return TranslationResponse(
            translated_text=combined_text,
            provider=self.provider.name,
            model=self.provider.model_name,
            token_usage=total_tokens,
            execution_time_ms=total_time,
            warnings=warnings,
            success=len(warnings) == 0,
        )

    # OPTIMIZATION: Concurrent block translation with ThreadPoolExecutor (Task 1 fix)
    def batch_translate_blocks(self, blocks: list[dict], source_lang: str, target_lang: str,
                                glossary_store: GlossaryStore | None = None,
                                progress_callback=None,
                                document_memory: DocumentMemory | None = None,
                                mode: ProcessingMode | None = None,
                                translation_cache: SQLiteTranslationCache | None = None,
                                quality_reviewer: AIQualityReviewer | None = None,
                                semantic_chunker: Any | None = None,
                                document_profile: DocumentProfile | None = None,
                                context_preamble: str = "",
                                ctx=None) -> list[dict]:
        """Translate a list of document blocks with concurrent execution, batching, and caching.

        Supports semantic chunking (Phase 3), document memory (Phase 2),
        specialized prompts (Phase 4), AI quality review (Phase 5),
        and translation cache (Phase 6).

        OPTIMIZATIONS:
        - Task 1: Concurrent translation with ThreadPoolExecutor
                 (FIX: uses ThreadPoolExecutor instead of asyncio to avoid
                  nested event loop errors in FastAPI's async context)
        - Task 2: Persistent SQLite cache integration
        - Task 3: Short block batching (group <80 token blocks into batches of 5)
        - Task 4: Pre-filter untranslatable blocks

        Args:
            blocks: List of block dicts with 'text', 'type', 'style' keys.
            source_lang: Source language name.
            target_lang: Target language name.
            glossary_store: Optional glossary for post-processing.
            progress_callback: Optional callable(completed, total).
            document_memory: Optional DocumentMemory.
            mode: Processing mode configuration.
            translation_cache: Optional SQLiteTranslationCache.
            quality_reviewer: Optional AIQualityReviewer.
            semantic_chunker: Optional SemanticChunker.
            document_profile: Optional DocumentProfile.
            context_preamble: Optional extra context (e.g. prepass summary) that is
                prepended to the memory context for single-block translation calls.
            ctx: Optional DocumentContext for stats tracking.

        Returns:
            List of translated block dicts.
        """
        # NOTE: workers use DocumentMemory (not ContextBuffer) for context, so
        # there is no shared buffer to clear here — the pipeline's context
        # buffer is per-request and never mutated from this path.
        total = len(blocks)

        # Phase 3: Semantic chunking
        semantic_groups: list[list[int]] | None = None
        if (mode and mode.semantic_chunking and semantic_chunker
                and document_profile and document_profile.is_reliable()):
            semantic_chunks = semantic_chunker.chunk_blocks(blocks, document_profile)
            semantic_groups = []
            for chunk in semantic_chunks:
                ordered = list(dict.fromkeys(chunk.block_indices))
                if ordered:
                    semantic_groups.append(ordered)

        # OPTIMIZATION: Phase 1 — Pre-filter passthrough blocks (Task 4)
        passthrough_indices: set[int] = set()
        for i, block in enumerate(blocks):
            text = block.get("text", "")
            should_skip, reason = _is_passthrough_block(text)
            if should_skip:
                passthrough_indices.add(i)
                if ctx:
                    ctx.blocks_passthrough += 1

        # OPTIMIZATION: Phase 2 — Check cache for all blocks (Task 2)
        cached_results: dict[int, str] = {}
        if translation_cache:
            for i, block in enumerate(blocks):
                if i in passthrough_indices:
                    continue
                text = block.get("text", "")
                if not text.strip():
                    continue
                cached = translation_cache.get(
                    text, target_lang, self.provider.name,
                    source_lang=source_lang,
                )
                if cached is not None and not translation_content_issue(text, cached):
                    cached_results[i] = cached
                    if ctx:
                        ctx.blocks_cached += 1
                        ctx.cache_stat(hit=True)

        # OPTIMIZATION: Phase 3 — Build work items (blocks that need translation)
        # Work items are (block_index, text, block_type) tuples
        work_items: list[tuple[int, str, str]] = []
        for i, block in enumerate(blocks):
            if i in passthrough_indices or i in cached_results:
                continue
            text = block.get("text", "")
            if not text.strip():
                continue
            work_items.append((i, text, block.get("type", "paragraph")))

        # OPTIMIZATION: Phase 4 — Build batches (Task 3)
        # A batch is a list of (block_index, text, block_type) tuples.
        # Packing is char-budget driven (provider-aware limits) so blocks of
        # ANY length — including long paragraphs — travel together in one
        # request when they fit. A block that alone exceeds the budget still
        # becomes its own single-item batch (unchanged behavior).
        batches: list[list[tuple[int, str, str]]] = []
        batched_indices: set[int] = set()

        if _TRANSLATION_BATCH_ENABLED:
            # The chain advertises limits that every provider in it can honor.
            provider_limits = getattr(self.provider, "batch_limits", None)
            if not provider_limits:
                batch_provider_name = getattr(
                    self.provider, "batch_provider_name", self.provider.name
                )
                provider_limits = _PROVIDER_BATCH_LIMITS.get(
                    batch_provider_name, _DEFAULT_BATCH_LIMITS
                )
            max_batch_items = provider_limits["max_batch_items"]
            max_batch_chars = provider_limits["max_batch_chars"]
            content_budget = max_batch_chars

            by_index = {item[0]: item for item in work_items}
            packing_groups: list[list[tuple[int, str, str]]] = []
            grouped: set[int] = set()
            if semantic_groups:
                for group in semantic_groups:
                    items = [by_index[idx] for idx in group
                             if idx in by_index and idx not in grouped]
                    if items:
                        packing_groups.append(items)
                        grouped.update(item[0] for item in items)
                ungrouped = [item for item in work_items if item[0] not in grouped]
                if ungrouped:
                    packing_groups.append(ungrouped)
            else:
                packing_groups = [work_items]

            # Never merge across a semantic boundary. Each boundary may still
            # split into smaller ID-keyed batches when provider limits require.
            for group_items in packing_groups:
                current_batch: list[tuple[int, str, str]] = []
                current_batch_chars = 0
                for item in group_items:
                    _, text, _ = item
                    char_count = len(text)
                    within_batch_size = len(current_batch) < max_batch_items
                    within_char_limit = current_batch_chars + char_count <= content_budget
                    fits_alone = char_count <= content_budget

                    if within_batch_size and within_char_limit:
                        current_batch.append(item)
                        current_batch_chars += char_count
                    else:
                        if current_batch:
                            batches.append(current_batch)
                        current_batch = [item]
                        current_batch_chars = char_count
                    if not fits_alone and len(current_batch) == 1:
                        batches.append(current_batch)
                        current_batch = []
                        current_batch_chars = 0
                if current_batch:
                    batches.append(current_batch)

            # Track which indices are in batches
            for batch in batches:
                if len(batch) > 1:
                    for idx, _, _ in batch:
                        batched_indices.add(idx)
        else:
            # No batching — each item is its own batch
            for item in work_items:
                batches.append([item])

        if ctx:
            ctx.blocks_batched = len(batched_indices)

        # Document GPT-OSS batches use one process-wide fair scheduler.  This
        # prevents two simultaneous documents from each creating an eight-call
        # burst while retaining the fast eight-slot total capacity.
        results: dict[int, str] = {}

        # Phase D Tier 3a: When batched review is enabled, skip per-chunk review in workers
        worker_quality_reviewer = None if _TRANSLATION_BATCHED_REVIEW else quality_reviewer
        failed_blocks: dict[int, str] = {}
        systemic_failure = False

        if work_items:
            primary_name = getattr(self.provider, "provider_names", (self.provider.name,))[0]
            use_fair_scheduler = primary_name == "gptoss"
            executor = None if use_fair_scheduler else ThreadPoolExecutor(
                max_workers=self.concurrency_limit()
            )
            try:
                future_to_batch = {}
                for batch_idx, batch in enumerate(batches):
                    callback = lambda batch=batch: self._translate_batch_worker(
                        batch, source_lang, target_lang, document_memory,
                        translation_cache, worker_quality_reviewer,
                        document_profile, context_preamble, ctx,
                    )
                    future = (
                        document_batch_scheduler.submit(str(id(ctx)), callback)
                        if use_fair_scheduler else submit_with_usage(executor, callback)
                    )
                    future_to_batch[future] = batch_idx

                for future in as_completed(future_to_batch):
                    try:
                        batch_results = future.result()
                        results.update(batch_results)
                        if ctx:
                            ctx.blocks_translated += len(batch_results)
                            if use_fair_scheduler:
                                ctx.scheduler_batches += 1
                                ctx.scheduler_slots = document_batch_scheduler.slots
                            ctx.scheduler_wait_ms = getattr(ctx, "scheduler_wait_ms", 0.0) + getattr(
                                future, "scheduler_wait_ms", 0.0
                            )
                    except Exception as e:
                        batch_idx = future_to_batch[future]
                        batch = batches[batch_idx]
                        print(f"  Warning: Batch {batch_idx} failed: {e}")
                        provider_failure = any(marker in str(e).lower() for marker in (
                            "rate limit", "timed out", "cannot connect",
                            "connection", "provider failed", "unavailable",
                        ))
                        if provider_failure:
                            # Cancel queued work and fail once. Retrying every
                            # block would multiply one provider outage into a
                            # request storm that survives the web timeout.
                            systemic_failure = True
                            for pending in future_to_batch:
                                pending.cancel()
                            for failed_idx, _, _ in work_items:
                                if failed_idx not in results:
                                    failed_blocks[failed_idx] = str(e)
                            break
                        # Fall back to individual translation for failed batch
                        for idx, text, btype in batch:
                            try:
                                translated = self._translate_single_worker(
                                    text, source_lang, target_lang, btype,
                                    document_memory, translation_cache,
                                    worker_quality_reviewer, document_profile, idx,
                                    context_preamble, ctx,
                                )
                                results[idx] = translated
                                if ctx:
                                    ctx.blocks_translated += 1
                            except Exception as e2:
                                print(f"  Warning: Fallback translation failed for block {idx}: {e2}")
                                failed_blocks[idx] = str(e2)
            finally:
                if executor is not None:
                    executor.shutdown(wait=True)

        if failed_blocks:
            content_failure = any(message.startswith(("Conversational response", "Missing protected content",
                                                       "Empty translation")) for message in failed_blocks.values())
            if systemic_failure or content_failure:
                # A provider-wide outage (rate limit, timeout, connection)
                # marked every outstanding block as failed. Returning the
                # document with the source text intact would silently mask the
                # outage, so surface it and let the queue retry.
                sample = "; ".join(
                    f"block {idx}: {message}" for idx, message in list(failed_blocks.items())[:3]
                )
                raise RuntimeError(
                    f"Translation failed for {len(failed_blocks)} block(s). {sample}. "
                    "The source document was not returned as a false successful translation."
                )
            # A small number of isolated block failures (echoed/untranslatable
            # content, per-block provider errors) should not destroy the whole
            # document. Keep the source text for those blocks and warn; the
            # failed indices fall out of `results` and reassembly below marks
            # them as passthrough.
            for idx, message in failed_blocks.items():
                if ctx:
                    ctx.add_warning(
                        f"Block {idx} could not be translated and was kept in "
                        f"source: {message[:200]}"
                    )
            print(
                f"  ⚠️  {len(failed_blocks)} block(s) could not be translated; "
                f"source text kept so the document can still be produced."
            )

        # Phase D Tier 3a: Batched AI quality review (single AI call for all blocks)
        if _TRANSLATION_BATCHED_REVIEW and quality_reviewer and results:
            print(f"\n  [QualityReview] Running batched review on {len(results)} blocks...")
            review_entries: list[tuple[int, str, str]] = []
            for idx in results:
                source_text = ""
                for orig_idx, block in enumerate(blocks):
                    if orig_idx == idx:
                        source_text = block.get("text", "")
                        break
                if source_text:
                    review_entries.append((idx, source_text, results[idx]))

            if review_entries:
                try:
                    batch_reviews = quality_reviewer.batch_review(
                        review_entries,
                        document_type=document_profile.document_type if document_profile else "",
                        block_types={
                            idx: blocks[idx].get("type", "paragraph")
                            for idx, _, _ in review_entries
                        },
                    )
                except TypeError as error:
                    if "block_types" not in str(error):
                        raise
                    batch_reviews = quality_reviewer.batch_review(
                        review_entries,
                        document_type=document_profile.document_type if document_profile else "",
                    )
                if ctx and any(
                    "unavailable" in review.summary.lower()
                    for review in batch_reviews.values()
                ):
                    ctx.add_warning(
                        "Quality review was unavailable for one or more blocks; "
                        "deterministic checks were used."
                    )

                retranslated_count = 0
                for idx, source_text, rev_text in review_entries:
                    review = batch_reviews.get(idx)
                    if ctx and review is not None:
                        ctx.record_block_quality(idx, review.score, review.issues)
                    if review and quality_reviewer.needs_retranslation(review):
                        context = ""
                        retry_block_type = blocks[idx].get("type", "paragraph")
                        if document_memory:
                            context = document_memory.get_context_for_block(
                                {"text": source_text, "type": retry_block_type}, idx
                            )
                        with llm_call_profile(ctx) if ctx else _nullcontext():
                            retry_response = self._translate_with_echo_guard(
                                text=source_text,
                                source_lang=source_lang,
                                target_lang=target_lang,
                                block_type=retry_block_type,
                                context_hint=f"{context}\nPrevious issues: {review.summary}",
                                document_type=document_profile.document_type if document_profile else "",
                                ctx=ctx,
                            )
                        if retry_response.success and retry_response.translated_text:
                            results[idx] = retry_response.translated_text
                            retranslated_count += 1
                            if translation_cache and not _is_echo_output(
                                source_text, retry_response.translated_text,
                                retry_block_type, source_lang, target_lang,
                            ):
                                translation_cache.put(
                                    source_text, target_lang,
                                    self.provider.name, retry_response.translated_text,
                                    source_lang=source_lang,
                                )
                        elif ctx:
                            ctx.add_warning(
                                f"Quality repair failed for block {idx}; "
                                "the valid initial translation was retained."
                            )

                if retranslated_count > 0:
                    print(f"  [QualityReview] {retranslated_count} block(s) retranslated via batched review")

                if ctx:
                    ctx.retranslated_chunks += retranslated_count

        # OPTIMIZATION: Phase 6 — Reassemble blocks in document order (Task 1)
        translated_blocks = []
        for i, block in enumerate(blocks):
            if i in passthrough_indices:
                # Passthrough — copy source text directly, flag for reconstructor
                translated_blocks.append(dict(block, text=block.get("text", ""), passthrough=True))
            elif i in cached_results:
                # From cache
                translated_blocks.append(dict(block, text=cached_results[i]))
            elif i in results:
                # From translation
                translated_text = results[i]

                # Apply glossary
                if glossary_store is not None:
                    translated_text = glossary_store.apply(translated_text)

                issue = translation_content_issue(block.get("text", ""), translated_text)
                if issue:
                    raise RuntimeError(f"Invalid translation for block {i}: {issue}")

                # Cache the result
                if translation_cache and not _is_echo_output(
                    block.get("text", ""), translated_text,
                    block.get("type", "paragraph"), source_lang, target_lang,
                ):
                    translation_cache.put(
                        block.get("text", ""), target_lang,
                        self.provider.name, translated_text,
                        source_lang=source_lang,
                    )

                # Replace only text. Every extractor-provided identity, style,
                # coordinate, table, slide, link, and source metadata field
                # remains one-to-one for reconstruction.
                new_block = dict(block)
                new_block["text"] = translated_text

                # Preserve original text for PDF expansion ratio
                if "position" in block:
                    new_block["_original_text"] = block["text"]

                # Surface the AI quality review (score + issues) on the block.
                # The reviewer's output already exists in-memory — this only
                # copies it onto the block for the regeneration sidecar.
                if ctx:
                    q = ctx.block_quality.get(i)
                    if q:
                        new_block["quality_score"] = q.get("score")
                        new_block["quality_issues"] = q.get("issues")

                translated_blocks.append(new_block)
            else:
                # Fallback — should not happen, but just in case
                translated_blocks.append(dict(block, text=block.get("text", ""), passthrough=True))

            if progress_callback:
                progress_callback(i + 1, total)

        print(f"\n  [OK] Translation complete! ({total} blocks)")
        return translated_blocks

    # Provider-neutral unit pipeline (Phases 1-4).
    #
    # Same responsibilities as batch_translate_blocks, but the core
    # (context enrichment, provider execution, quality review/repair and
    # layout preflight) operates on TranslationUnit/TranslationUnitResult
    # DTOs instead of loose dicts. Conversion happens once per boundary:
    # dict -> unit via unit_adapters.to_unit_list, unit -> dict via
    # unit_adapters.unit_to_block. The legacy dict shape (passthrough flag,
    # _original_text, quality_score/quality_issues) is reproduced exactly so
    # the reconstruction/sidecar/Laravel layers are untouched.
    #
    # Phase 4.1 stabilization: every unit's structural metadata (role, table
    # headers, furniture status, previous/next context, protected-span
    # instructions) plus the document preamble, document memory and semantic
    # group context is rendered into unit.context_hint before dispatch and
    # delivered to the provider verbatim. Semantic chunking is wired in as
    # context + translate_many batch boundaries ONLY — no unit is ever merged
    # into another output block. Layout preflight findings are persisted (as
    # advisory data) on the context and serialized into the regeneration
    # sidecar, never applied to geometry.
    def batch_translate_units(self, blocks: list[dict], source_lang: str, target_lang: str,
                              glossary_store: GlossaryStore | None = None,
                              progress_callback=None,
                              document_memory: DocumentMemory | None = None,
                              mode: ProcessingMode | None = None,
                              translation_cache: SQLiteTranslationCache | None = None,
                              quality_reviewer: AIQualityReviewer | None = None,
                              semantic_chunker: Any | None = None,
                              document_profile: DocumentProfile | None = None,
                              context_preamble: str = "",
                              ctx=None) -> list[dict]:
        total = len(blocks)
        document_map = build_document_map(blocks)
        units = to_unit_list(blocks, document_map)
        by_block_id = {unit.source_block_id: unit for unit in units}

        # Phase 1 — Passthrough prefilter
        passthrough_ids: set[int] = set()
        for unit in units:
            should_skip, _ = _is_passthrough_block(unit.source_text)
            if should_skip or not unit.source_text.strip():
                passthrough_ids.add(unit.source_block_id)
                if ctx:
                    ctx.blocks_passthrough += 1

        # Phase 2 — Cache lookups
        cached_texts: dict[int, str] = {}
        if translation_cache:
            for unit in units:
                if unit.source_block_id in passthrough_ids:
                    continue
                cached = translation_cache.get(
                    unit.source_text, target_lang, self.provider.name,
                    source_lang=source_lang,
                )
                if cached is not None and not translation_content_issue(unit.source_text, cached):
                    cached_texts[unit.source_block_id] = cached
                    if ctx:
                        ctx.blocks_cached += 1
                        ctx.cache_stat(hit=True)

        # Phase 3 — Work units (non-empty, not passthrough, not cached)
        work_units = [
            unit for unit in units
            if (unit.source_block_id not in passthrough_ids
                and unit.source_block_id not in cached_texts
                and unit.source_text.strip())
        ]

        document_type = document_profile.document_type if document_profile else ""

        # Semantic chunking: build semantic groups up-front. They are used
        # ONLY as per-unit context and as translate_many batch boundaries; a
        # single unit is NEVER merged into another output block. Reading order
        # and source_block_id stay untouched (reassembly iterates the original
        # block list).
        semantic_units: dict = {}
        semantic_groups: list = []
        if semantic_chunker:
            semantic_groups = list(semantic_chunker.chunk_blocks(blocks, document_profile) or [])
            for chunk in semantic_groups:
                for block_index in chunk.block_indices:
                    semantic_units[block_index] = chunk

        # Enrich per-unit context: assemble the FULL provider-facing hint from
        # document preamble, document memory, semantic-group context and every
        # structural unit field (role, furniture, table headers, neighbors,
        # protected-span instructions). The result is stored on
        # unit.context_hint so both translate_many and the legacy fallback
        # path deliver identical context to the provider.
        for unit in work_units:
            memory_ctx = ""
            if document_memory:
                memory_ctx = document_memory.get_context_for_block(
                    {"text": unit.source_text, "type": unit.role},
                    unit.source_block_id,
                )
            semantic_ctx = ""
            chunk = semantic_units.get(unit.source_block_id)
            if chunk is not None and len(chunk.block_indices) > 1:
                others = [blocks[j].get("text", "") for j in chunk.block_indices
                          if j != unit.source_block_id]
                others = [o for o in others if o and o != unit.source_text]
                if others:
                    joined = " ".join(others)
                    semantic_ctx = (
                        "Related passages in this section (translate consistently, "
                        "keep terminology aligned):\n" + joined[:1500]
                    )
            unit.context_hint = build_provider_hint(
                unit, context_preamble=context_preamble, memory_context=memory_ctx,
                semantic_context=semantic_ctx,
            )

        # Phase 4 — Execute via translate_many (duck-typed dispatch).
        # When semantic chunking is active, each semantic group becomes one
        # translate_many batch; otherwise all work units go in one call.
        # GPT-OSS work is dispatched through the process-wide fair scheduler
        # (no thread pool is created here); every other provider runs inline
        # exactly as before. The provider must RAISE on systemic failures
        # (rate limit / timeout / connection / 5xx) so the document fails fast
        # instead of returning source text as a false successful translation.
        results_by_id: dict[int, TranslationUnitResult] = {}
        if work_units:
            batches = _partition_units_by_group(work_units, semantic_units) \
                if semantic_groups else [work_units]
            primary_name = getattr(self.provider, "provider_names", (self.provider.name,))[0]
            use_fair_scheduler = primary_name == "gptoss"

            def _unit_batch_callback(batch):
                return translate_many_units(
                    self.provider, batch,
                    source_lang=source_lang, target_lang=target_lang,
                    context_hint=context_preamble or "",
                    document_type=document_type, ctx=ctx,
                )

            if use_fair_scheduler:
                future_to_batch = {}
                for batch in batches:
                    future = document_batch_scheduler.submit(
                        str(id(ctx)), lambda b=batch: _unit_batch_callback(b)
                    )
                    future_to_batch[future] = batch

                systemic_error = ""
                for future in as_completed(future_to_batch):
                    batch = future_to_batch[future]
                    try:
                        unit_results = future.result()
                    except Exception as e:
                        systemic_error = _systemic_failure_message(e)
                        if systemic_error:
                            print(f"  Warning: Unit batch failed systemically: {e}")
                            for pending in future_to_batch:
                                pending.cancel()
                            break
                        # Isolated batch failure — keep the source text for the
                        # affected units and let the caller see the warning.
                        print(f"  Warning: Unit batch failed: {e}")
                        for unit in batch:
                            results_by_id[unit.unit_id] = TranslationUnitResult(
                                unit_id=unit.unit_id,
                                status="failed",
                                translated_text=unit.source_text,
                                provider=self.provider.name,
                                model=getattr(self.provider, "model_name", ""),
                                error=str(e),
                            )
                        continue
                    for result in unit_results:
                        results_by_id[result.unit_id] = result
                    if ctx:
                        ctx.blocks_translated += len(unit_results)
                        ctx.blocks_batched += len(unit_results) if len(batch) > 1 else 0
                        ctx.scheduler_batches += 1
                        ctx.scheduler_slots = document_batch_scheduler.slots
                        ctx.scheduler_wait_ms = ctx.scheduler_wait_ms + getattr(
                            future, "scheduler_wait_ms", 0.0
                        )

                if systemic_error:
                    raise RuntimeError(
                        f"Translation failed for {len(work_units)} unit(s): "
                        f"{systemic_error}. The source document was not returned "
                        "as a false successful translation."
                    )
            else:
                for batch in batches:
                    with llm_call_profile(ctx) if ctx else _nullcontext():
                        unit_results = _unit_batch_callback(batch)
                    for result in unit_results:
                        results_by_id[result.unit_id] = result
                    if ctx:
                        ctx.blocks_translated += len(unit_results)
                        ctx.blocks_batched += len(unit_results) if len(batch) > 1 else 0

        # Phase 5 — Per-unit echo guard, quality review/repair, protected-span
        # restoration, glossary, cache store.
        final_texts: dict[int, str] = {}
        for unit in work_units:
            result = results_by_id.get(unit.unit_id)
            if result is None or result.status == "failed":
                reason = result.error if result else "no provider result"
                final_texts[unit.source_block_id] = unit.source_text
                if ctx:
                    ctx.add_warning(
                        f"Unit {unit.source_block_id} could not be translated; "
                        f"source retained. ({reason})"
                    )
                continue

            text = result.translated_text

            # Echo guard — retry exactly like the legacy single-block worker.
            if translation_content_issue(unit.source_text, text) or _is_echo_output(
                    unit.source_text, text, unit.role, source_lang, target_lang):
                if ctx:
                    ctx.echo_retries += 1
                with llm_call_profile(ctx) if ctx else _nullcontext():
                    retry_response = self._translate_with_echo_guard(
                        text=unit.source_text,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        block_type=unit.role,
                        context_hint=unit.context_hint or unit.previous_context or "",
                        document_type=document_type,
                        ctx=ctx,
                    )
                if retry_response.success and retry_response.translated_text and not _is_echo_output(
                    unit.source_text, retry_response.translated_text,
                    unit.role, source_lang, target_lang,
                ):
                    text = retry_response.translated_text
                    result.translated_text = text

            issue = translation_content_issue(unit.source_text, text)
            if issue:
                raise RuntimeError(f"Invalid translation for block {unit.source_block_id}: {issue}")

            # AI quality review + repair.
            if quality_reviewer:
                with llm_call_profile(ctx) if ctx else _nullcontext():
                    review = quality_reviewer.review(
                        source=unit.source_text,
                        translation=text,
                        document_type=document_type,
                        block_type=unit.role,
                    )
                if ctx:
                    ctx.record_block_quality(unit.source_block_id, review.score, review.issues)
                if review.retry_required:
                    retry_hint = "\n".join(filter(None, [
                        unit.context_hint or unit.previous_context or "",
                        f"Previous issues: {review.summary}",
                    ]))
                    with llm_call_profile(ctx) if ctx else _nullcontext():
                        retry_response = self._translate_with_echo_guard(
                            text=unit.source_text,
                            source_lang=source_lang,
                            target_lang=target_lang,
                            block_type=unit.role,
                            context_hint=retry_hint,
                            document_type=document_type,
                            ctx=ctx,
                        )
                    if retry_response.success and retry_response.translated_text:
                        text = retry_response.translated_text
                        result.translated_text = text
                        result.status = "repaired"
                        if ctx:
                            ctx.retranslated_chunks += 1
                    elif ctx:
                        ctx.add_warning(
                            f"Quality repair failed for unit {unit.source_block_id}; "
                            "the valid initial translation was retained."
                        )

            # Protected-span restoration — numbers, URLs, emails, placeholders.
            text = restore_protected_spans(unit.source_text, text, unit.protected_spans)

            # Glossary post-processing.
            if glossary_store is not None:
                text = glossary_store.apply(text)

            issue = translation_content_issue(unit.source_text, text)
            if issue:
                raise RuntimeError(f"Invalid translation for block {unit.source_block_id}: {issue}")

            # Cache the result (skip echoes).
            if translation_cache and not _is_echo_output(
                unit.source_text, text, unit.role, source_lang, target_lang
            ):
                translation_cache.put(
                    unit.source_text, target_lang, self.provider.name, text,
                    source_lang=source_lang,
                )

            final_texts[unit.source_block_id] = text
            result.translated_text = text

        # Record in document memory for downstream chunks.
        if document_memory:
            for unit in work_units:
                text = final_texts.get(unit.source_block_id)
                if text:
                    document_memory.record_translation(
                        unit.source_text, text, unit.source_block_id
                    )
                    document_memory.extract_terms(unit.source_text, text)
                    document_memory.update_abbreviations(unit.source_text)

        # Phase 6 — Layout preflight (DTO-only; surfaced as warnings and
        # persisted on the context so the regeneration sidecar can report it).
        # Advisory only: it never alters fonts, positions or geometry — the
        # reconstruction/layout validator remains the layout authority.
        if work_units:
            preflight_units(tuple(work_units), results_by_id,
                            source_lang=source_lang, target_lang=target_lang)
            for unit in work_units:
                result = results_by_id.get(unit.unit_id)
                if result and result.layout:
                    layout = result.layout
                    if ctx:
                        ctx.record_block_layout(unit.source_block_id, layout)
                    if (layout.collision_state != "none"
                            or layout.clipping_state != "none"
                            or "overflow" in layout.fit_actions):
                        if ctx:
                            ctx.add_warning(
                                f"Layout: unit {unit.source_block_id} "
                                f"({layout.collision_state}/{layout.clipping_state})"
                            )

        # Phase 7 — Reassemble legacy-shaped blocks in document order.
        translated_blocks = []
        for i, block in enumerate(blocks):
            unit = by_block_id[i]
            if i in passthrough_ids:
                r = TranslationUnitResult(unit_id=unit.unit_id, status="passthrough",
                                          translated_text=block.get("text", ""))
                translated_blocks.append(unit_to_block(block, unit, r, ctx))
            elif i in cached_texts:
                r = TranslationUnitResult(unit_id=unit.unit_id, status="cached",
                                          translated_text=cached_texts[i])
                translated_blocks.append(unit_to_block(block, unit, r, ctx))
            elif i in final_texts:
                source_result = results_by_id.get(unit.unit_id)
                r = TranslationUnitResult(
                    unit_id=unit.unit_id,
                    status=source_result.status if source_result else "translated",
                    translated_text=final_texts[i],
                    provider=source_result.provider if source_result else "",
                    model=source_result.model if source_result else "",
                )
                if source_result:
                    r.quality = source_result.quality
                    r.layout = source_result.layout
                translated_blocks.append(unit_to_block(block, unit, r, ctx))
            else:
                translated_blocks.append(dict(block, text=block.get("text", ""), passthrough=True))

            if progress_callback:
                progress_callback(i + 1, total)

        print(f"\n  [OK] Unit translation complete! ({total} blocks)")
        return translated_blocks

    def _translate_batch_worker(
        self, batch: list[tuple[int, str, str]],
        source_lang: str, target_lang: str,
        document_memory, translation_cache,
        quality_reviewer, document_profile,
        context_preamble: str = "",
        ctx=None,
    ) -> dict[int, str]:
        """Translate a batch of blocks (single or multiple) in a worker thread.

        This runs inside a ThreadPoolExecutor worker. No asyncio usage.
        Returns dict mapping block_index -> translated_text.
        """
        batch_results: dict[int, str] = {}

        if len(batch) == 1:
            # Single block — translate directly
            idx, text, btype = batch[0]
            translated = self._translate_single_worker(
                text, source_lang, target_lang, btype,
                document_memory, translation_cache,
                quality_reviewer, document_profile, idx,
                context_preamble, ctx,
            )
            batch_results[idx] = translated
        else:
            # Batch of short blocks — send as one API call
            entries = [(idx, text) for idx, text, _ in batch]
            batch_text = _build_batch_prompt(
                entries, source_lang, target_lang,
                provider_name=getattr(
                    self.provider, "batch_provider_name", self.provider.name
                ),
            )

            with llm_call_profile(ctx) if ctx else _nullcontext():
                try:
                    response = self.provider.translate(
                        text=batch_text,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        block_type="batch",
                        context_hint=context_preamble or "",
                        document_type=document_profile.document_type if document_profile else "",
                        response_format="json",
                    )
                except TypeError as error:
                    # Compatibility for local/test providers implementing the
                    # pre-structured-output interface.
                    if "response_format" not in str(error):
                        raise
                    response = self.provider.translate(
                        text=batch_text,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        block_type="batch",
                        context_hint=context_preamble or "",
                        document_type=document_profile.document_type if document_profile else "",
                    )
            self._record_provider_response(ctx, response)
            if ctx:
                for warning in response.warnings:
                    ctx.add_warning(warning)

            if response.success and response.translated_text:
                parsed = _parse_batch_response(
                    response.translated_text,
                    [idx for idx, _, _ in batch],
                )
                # A batch is valid only when every item is present and each
                # translatable item actually changed. Send unresolved entries
                # to the backup as ONE JSON batch before individual repair.
                unresolved = []
                for idx, text, btype in batch:
                    candidate = parsed.get(idx)
                    if candidate and not translation_content_issue(text, candidate) and not _is_echo_output(
                        text, candidate, btype, source_lang, target_lang
                    ):
                        batch_results[idx] = candidate
                    else:
                        unresolved.append((idx, text, btype))

                secondary = getattr(self.provider, "translate_secondary", None)
                if unresolved and callable(secondary):
                    if ctx:
                        ctx.batch_fallbacks += 1
                    fallback_prompt = _build_batch_prompt(
                        [(idx, text) for idx, text, _ in unresolved],
                        source_lang, target_lang, provider_name="gemini",
                    )
                    try:
                        with llm_call_profile(ctx) if ctx else _nullcontext():
                            fallback_response = secondary(
                                text=fallback_prompt, source_lang=source_lang,
                                target_lang=target_lang, block_type="batch",
                                context_hint="\n".join(filter(None, [context_preamble,
                                    "Primary batch was malformed or contained untranslated "
                                    "entries. Return translated JSON only."])),
                                document_type=document_profile.document_type
                                if document_profile else "",
                                response_format="json",
                            )
                    except TypeError as error:
                        if "response_format" not in str(error):
                            raise
                        fallback_response = secondary(
                            text=fallback_prompt, source_lang=source_lang,
                            target_lang=target_lang, block_type="batch",
                            context_hint="\n".join(filter(None, [context_preamble,
                                "Primary batch contained untranslated entries."])),
                            document_type=document_profile.document_type
                            if document_profile else "",
                        )
                    self._record_provider_response(ctx, fallback_response)
                    fallback_parsed = _parse_batch_response(
                        fallback_response.translated_text,
                        [idx for idx, _, _ in unresolved],
                    ) if fallback_response.success else {}
                    remaining = []
                    for idx, text, btype in unresolved:
                        candidate = fallback_parsed.get(idx)
                        if candidate and not translation_content_issue(text, candidate) and not _is_echo_output(
                            text, candidate, btype, source_lang, target_lang
                        ):
                            batch_results[idx] = candidate
                        else:
                            remaining.append((idx, text, btype))
                    unresolved = remaining

                for idx, text, btype in unresolved:
                    translated = self._translate_single_worker(
                        text, source_lang, target_lang, btype,
                        document_memory, translation_cache,
                        quality_reviewer, document_profile, idx,
                        context_preamble, ctx,
                    )
                    batch_results[idx] = translated
            else:
                # A provider failure affects the entire request. The outer
                # coordinator decides whether recovery is safe; never fan a
                # 429 out into one request per block here.
                raise RuntimeError(
                    response.error_message or "Translation provider failed"
                )

        return batch_results

    def _translate_oversized_worker(
        self, text: str, source_lang: str, target_lang: str,
        block_type: str, context: str, document_type: str, ctx=None,
    ) -> TranslationResponse:
        """Translate one oversized block in paragraph/sentence-safe pieces."""
        chunks = _chunk_preserving_paragraphs(
            text, _TRANSLATION_MAX_TOKENS, self.chunk_splitter
        )
        if len(chunks) <= 1:
            with llm_call_profile(ctx) if ctx else _nullcontext():
                return self._translate_with_echo_guard(
                    text=text, source_lang=source_lang, target_lang=target_lang,
                    block_type=block_type, context_hint=context,
                    document_type=document_type, ctx=ctx,
                )

        translated_chunks: list[tuple[int, str]] = []
        providers: list[str] = []
        models: list[str] = []
        warnings: list[str] = []
        token_usage = {"input": 0, "output": 0}
        elapsed = 0.0
        rolling_context = context
        for paragraph_id, chunk_text in chunks:
            with llm_call_profile(ctx) if ctx else _nullcontext():
                response = self._translate_with_echo_guard(
                    text=chunk_text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    block_type=block_type,
                    context_hint=rolling_context,
                    document_type=document_type,
                    ctx=ctx,
                )
            if not response.success or not response.translated_text:
                return response
            translated_chunks.append((paragraph_id, response.translated_text))
            if response.provider and response.provider not in providers:
                providers.append(response.provider)
            if response.model and response.model not in models:
                models.append(response.model)
            warnings.extend(response.warnings)
            elapsed += response.execution_time_ms
            for key in token_usage:
                token_usage[key] += response.token_usage.get(key, 0)
            recent = [part for _, part in translated_chunks[-2:]]
            rolling_context = "\n\n".join(filter(None, [context, *recent]))

        return TranslationResponse(
            translated_text=_rejoin_paragraph_aware(translated_chunks),
            provider="|".join(providers) or self.provider.name,
            model="|".join(models) or self.provider.model_name,
            token_usage=token_usage,
            execution_time_ms=elapsed,
            warnings=warnings,
        )

    # OPTIMIZATION: Worker for single block translation (Task 1 fix)
    def _translate_single_worker(
        self, text: str, source_lang: str, target_lang: str,
        block_type: str, document_memory, translation_cache,
        quality_reviewer, document_profile, block_index: int,
        context_preamble: str = "",
        ctx=None,
    ) -> str:
        """Translate a single chunk in a worker thread.

        This runs inside a ThreadPoolExecutor worker. No asyncio usage.
        All logic is identical to the original _async_translate_single but
        without async/await, making it compatible with FastAPI's event loop.
        """
        # Check cache first
        if translation_cache:
            cached = translation_cache.get(
                text, target_lang, self.provider.name,
                source_lang=source_lang,
            )
            if cached is not None and not translation_content_issue(text, cached):
                return cached

        # Build context from document memory
        context = ""
        if document_memory:
            context = document_memory.get_context_for_block(
                {"text": text, "type": block_type}, block_index
            )

        # OPTIMIZATION: Inject shared context preamble (prepass summary/terms)
        if context_preamble:
            if context:
                context = context_preamble + "\n" + context
            else:
                context = context_preamble

        # Translate via provider. Oversized blocks are split at paragraph or
        # sentence boundaries and rejoined with intentional blank lines.
        document_type = document_profile.document_type if document_profile else ""
        if self.provider.estimate_tokens(text) > _TRANSLATION_MAX_TOKENS:
            response = self._translate_oversized_worker(
                text, source_lang, target_lang, block_type,
                context, document_type, ctx,
            )
        else:
            with llm_call_profile(ctx) if ctx else _nullcontext():
                response = self._translate_with_echo_guard(
                    text=text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    block_type=block_type,
                    context_hint=context,
                    document_type=document_type,
                    ctx=ctx,
                )

        if not response.success:
            # Do not silently return the source as a successful translation.
            # Raising lets the queue retry a transient outage and ensures a
            # terminal provider failure is visible to the user.
            raise RuntimeError(response.error_message or "Translation provider failed")

        if ctx:
            for warning in response.warnings:
                ctx.add_warning(warning)

        translated = response.translated_text

        # AI Quality Review (Phase 5)
        if quality_reviewer and response.success:
            with llm_call_profile(ctx) if ctx else _nullcontext():
                review = quality_reviewer.review(
                    source=text,
                    translation=translated,
                    document_type=document_profile.document_type if document_profile else "",
                    block_type=block_type,
                )
            if ctx and "unavailable" in review.summary.lower():
                ctx.add_warning(
                    f"Quality review was unavailable for block {block_index}; "
                    "the valid initial translation was retained."
                )
            if ctx and review is not None:
                ctx.record_block_quality(block_index, review.score, review.issues)
            if quality_reviewer.needs_retranslation(review):
                with llm_call_profile(ctx) if ctx else _nullcontext():
                    retry_response = self._translate_with_echo_guard(
                        text=text,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        block_type=block_type,
                        context_hint=f"{context}\nPrevious issues: {review.summary}",
                        document_type=document_type,
                        ctx=ctx,
                    )
                if retry_response.success:
                    translated = retry_response.translated_text
                elif ctx:
                    ctx.add_warning(
                        f"Quality repair failed for block {block_index}; "
                        "the valid initial translation was retained."
                    )

        # Cache the result
        if translation_cache and not _is_echo_output(
            text, translated, block_type, source_lang, target_lang
        ):
            translation_cache.put(
                text, target_lang, self.provider.name, translated,
                source_lang=source_lang,
            )

        # Record in document memory
        if document_memory:
            document_memory.record_translation(text, translated, block_index)
            document_memory.extract_terms(text, translated)
            document_memory.update_abbreviations(text)

        return translated
