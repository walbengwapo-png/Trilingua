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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable


@contextmanager
def _nullcontext():
    """No-op context manager for conditional profiling."""
    yield

from dto.requests import TranslationRequest, LANGUAGES, CODE_TO_LANG
from dto.responses import TranslationResponse, ChunkResult
from providers.base import TranslationProvider
from document.chunker import ChunkSplitter
from document.semantic_chunker import SemanticChunker, SemanticChunk
from document.document_analyzer import DocumentProfile
from memory.terminology import ContextBuffer
from memory.glossary import GlossaryStore
from memory.document_memory import DocumentMemory
from cache.sqlite_cache import SQLiteTranslationCache
from validators.hallucination_detector import sanitize_translation, detect_hallucination
from validators.translation_validator import BLEUReporter
from validators.ai_quality_reviewer import AIQualityReviewer
from config.processing_modes import ProcessingMode
from .phase_profiler import llm_call_profile

# OPTIMIZATION: Env var defaults (Tasks 1, 3, 4)
# gptoss: 8 parallel calls (matches GPTOSSProvider._POOL_SIZE=8). Batching now
# packs many blocks into few requests, so parallelism overlaps the remaining
# long-block calls. Mistral is still capped at 4 (see executor setup below) —
# it rate-limits harder on Ollama Cloud.
# Tunable per environment via TRANSLATION_CONCURRENCY.
_TRANSLATION_CONCURRENCY = int(os.environ.get("TRANSLATION_CONCURRENCY", "8"))
_TRANSLATION_BATCH_ENABLED = os.environ.get("TRANSLATION_BATCH_ENABLED", "true").lower() == "true"
_TRANSLATION_CACHE_ENABLED = os.environ.get("TRANSLATION_CACHE_ENABLED", "true").lower() == "true"
_TRANSLATION_CACHE_TTL_DAYS = int(os.environ.get("TRANSLATION_CACHE_TTL_DAYS", "30"))
_TRANSLATION_PROMPT_VERSION = os.environ.get("TRANSLATION_PROMPT_VERSION", "2026-09-balanced-v1")

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
# mistral: 4000/12 -> 6000/16 (larger context window + relaxed rate limits).
_PROVIDER_BATCH_LIMITS = {
    "gptoss": {"max_batch_chars": 4000, "max_batch_items": 12},
    "mistral": {"max_batch_chars": 6000, "max_batch_items": 16},
}
_DEFAULT_BATCH_LIMITS = {"max_batch_chars": 1500, "max_batch_items": 5}


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


def _has_translatable_content(text: str) -> bool:
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
    # Require at least two tokens that start lowercase — real sentence words.
    # Title-Case proper nouns ("Dr. Santos", "National Gallery"), all-caps
    # acronyms ("AI"), and mixed proper-noun phrases contribute no lowercase-
    # initial tokens and are therefore NOT flagged as echo output.
    content_tokens = [t for t in tokens if t[0].islower()]
    return len(content_tokens) >= 2


def _is_echo_output(source_text: str, translated_text: str) -> bool:
    """True when the 'translation' is effectively the source, unchanged.

    Only flagged for text with real translatable content; proper nouns,
    numbers, acronyms, and very short strings legitimately translate to
    themselves and are excluded.
    """
    return (
        _has_translatable_content(source_text)
        and _normalize_for_compare(source_text) == _normalize_for_compare(translated_text)
    )


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

    limit = _PROVIDER_BATCH_LIMITS.get(provider_name, _DEFAULT_BATCH_LIMITS)
    max_chars = limit["max_batch_chars"]

    return (
        f"Translate each entry from {source_lang} to {target_lang} independently. "
        f"Return ONLY valid JSON, no preamble, no explanation.\n"
        f"{{\"1\": \"...\", \"2\": \"...\"}}\n\n"
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
        response = self.provider.translate(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            block_type=block_type,
            context_hint=context_hint,
            document_type=document_type,
        )

        if response.success and _is_echo_output(text, response.translated_text):
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
            if retry_response.success and not _is_echo_output(text, retry_response.translated_text):
                response = retry_response
            elif retry_response.success:
                # Still echoing — treat as a real failure, never cache it.
                print(f"  ⚠️  Provider echoed source unchanged after retry ({target_lang})")
                return TranslationResponse(
                    translated_text=text,
                    provider=self.provider.name,
                    model=self.provider.model_name,
                    token_usage={},
                    execution_time_ms=0.0,
                    success=False,
                    error_message=(
                        f"Translation failed: the provider returned the source "
                        f"text unchanged for target language {target_lang}."
                    ),
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
            if cached is not None:
                return TranslationResponse(
                    translated_text=cached,
                    provider=self.provider.name,
                    model=self.provider.model_name,
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
            if cache:
                cache.put(
                    request.text, request.target_lang,
                    self.provider.name, response.translated_text,
                    source_lang=request.source_lang,
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
                if cached is not None:
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
                            warnings.append(f"Chunk {i + 1} retranslated (score: {review.score:.1f})")

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
        if mode and mode.semantic_chunking and semantic_chunker and document_profile:
            semantic_chunks = semantic_chunker.chunk_blocks(blocks, document_profile)
            block_chunks: dict[int, list[tuple[str, list[int]]]] = {}
            for chunk in semantic_chunks:
                for bi in chunk.block_indices:
                    if bi not in block_chunks:
                        block_chunks[bi] = []
                    block_chunks[bi].append((chunk.text, chunk.block_indices))
        else:
            block_chunks = None

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
                if cached is not None:
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
            # Provider-aware batch limits
            provider_limits = _PROVIDER_BATCH_LIMITS.get(
                self.provider.name, _DEFAULT_BATCH_LIMITS
            )
            max_batch_items = provider_limits["max_batch_items"]
            max_batch_chars = provider_limits["max_batch_chars"]
            # Leave headroom for the JSON wrapper + "max N chars" instruction
            content_budget = int(max_batch_chars * 0.9)

            current_batch: list[tuple[int, str, str]] = []
            current_batch_chars = 0
            for item in work_items:
                idx, text, btype = item
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
                if not fits_alone and current_batch and len(current_batch) == 1:
                    # Oversized block — flush it as its own single-item batch
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

        # OPTIMIZATION: Phase 5 — Concurrent translation with ThreadPoolExecutor (Task 1)
        # FIX: Using ThreadPoolExecutor instead of asyncio to avoid nested event loop
        # errors in FastAPI's async context. The provider calls are synchronous HTTP
        # requests (blocking I/O), so thread pools are the correct mechanism.
        results: dict[int, str] = {}

        # Phase D Tier 3a: When batched review is enabled, skip per-chunk review in workers
        worker_quality_reviewer = None if _TRANSLATION_BATCHED_REVIEW else quality_reviewer

        if work_items:
            concurrency = max(1, _TRANSLATION_CONCURRENCY)
            if self.provider.name == "mistral":
                concurrency = min(concurrency, 4)
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                # Submit all batch work items to the thread pool
                future_to_batch = {}
                for batch_idx, batch in enumerate(batches):
                    future = executor.submit(
                        self._translate_batch_worker,
                        batch, source_lang, target_lang,
                        document_memory, translation_cache, worker_quality_reviewer,
                        document_profile, context_preamble, ctx,
                    )
                    future_to_batch[future] = batch_idx

                # Collect results as they complete
                for future in as_completed(future_to_batch):
                    try:
                        batch_results = future.result()
                        results.update(batch_results)
                        # Update ctx.blocks_translated count
                        if ctx:
                            ctx.blocks_translated += len(batch_results)
                    except Exception as e:
                        batch_idx = future_to_batch[future]
                        batch = batches[batch_idx]
                        print(f"  Warning: Batch {batch_idx} failed: {e}")
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
                                results[idx] = text  # Passthrough on total failure

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
                batch_reviews = quality_reviewer.batch_review(
                    review_entries,
                    document_type=document_profile.document_type if document_profile else "",
                )

                retranslated_count = 0
                for idx, source_text, rev_text in review_entries:
                    review = batch_reviews.get(idx)
                    if ctx and review is not None:
                        ctx.record_block_quality(idx, review.score, review.issues)
                    if review and quality_reviewer.needs_retranslation(review):
                        context = ""
                        if document_memory:
                            context = document_memory.get_context_for_block(
                                {"text": source_text, "type": ""}, idx
                            )
                        with llm_call_profile(ctx) if ctx else _nullcontext():
                            retry_response = self.provider.translate(
                                text=source_text,
                                source_lang=source_lang,
                                target_lang=target_lang,
                                block_type="paragraph",
                                context_hint=f"{context}\nPrevious issues: {review.summary}",
                                document_type=document_profile.document_type if document_profile else "",
                            )
                        if retry_response.success and retry_response.translated_text:
                            results[idx] = retry_response.translated_text
                            retranslated_count += 1
                            if translation_cache and not _is_echo_output(
                                source_text, retry_response.translated_text
                            ):
                                translation_cache.put(
                                    source_text, target_lang,
                                    self.provider.name, retry_response.translated_text,
                                    source_lang=source_lang,
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

                # Cache the result
                if translation_cache and not _is_echo_output(
                    block.get("text", ""), translated_text
                ):
                    translation_cache.put(
                        block.get("text", ""), target_lang,
                        self.provider.name, translated_text,
                        source_lang=source_lang,
                    )

                # Build new block preserving metadata
                new_block = {
                    "type": block["type"],
                    "text": translated_text,
                    "style": block.get("style", {}),
                }

                # Preserve position metadata for PDF
                for key in ("position", "page", "slide", "shape_id", "para_idx",
                            "sheet", "row", "col", "table_index",
                            "alignment", "lines", "links"):
                    if key in block:
                        new_block[key] = block[key]

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
                provider_name=self.provider.name,
            )

            with llm_call_profile(ctx) if ctx else _nullcontext():
                response = self.provider.translate(
                    text=batch_text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    block_type="paragraph",
                    context_hint="",
                    document_type=document_profile.document_type if document_profile else "",
                )

            if response.success and response.translated_text:
                parsed = _parse_batch_response(
                    response.translated_text,
                    [idx for idx, _, _ in batch],
                )
                if parsed:
                    batch_results.update(parsed)
                else:
                    # Fall back to individual translation
                    for idx, text, btype in batch:
                        translated = self._translate_single_worker(
                            text, source_lang, target_lang, btype,
                            document_memory, translation_cache,
                            quality_reviewer, document_profile, idx,
                            context_preamble, ctx,
                        )
                        batch_results[idx] = translated
            else:
                # Fall back to individual translation
                for idx, text, btype in batch:
                    translated = self._translate_single_worker(
                        text, source_lang, target_lang, btype,
                        document_memory, translation_cache,
                        quality_reviewer, document_profile, idx,
                        context_preamble, ctx,
                    )
                    batch_results[idx] = translated

        return batch_results

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
            if cached is not None:
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

        # Translate via provider (synchronous call — runs in thread pool)
        with llm_call_profile(ctx) if ctx else _nullcontext():
            response = self._translate_with_echo_guard(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                block_type=block_type,
                context_hint=context,
                document_type=document_profile.document_type if document_profile else "",
                ctx=ctx,
            )

        if not response.success:
            # Echo/other failure — do NOT cache; the reassembly path falls
            # back to the source text so the document still builds.
            return response.translated_text if response.translated_text else text

        translated = response.translated_text

        # AI Quality Review (Phase 5)
        if quality_reviewer and response.success:
            with llm_call_profile(ctx) if ctx else _nullcontext():
                review = quality_reviewer.review(
                    source=text,
                    translation=translated,
                    document_type=document_profile.document_type if document_profile else "",
                )
            if ctx and review is not None:
                ctx.record_block_quality(block_index, review.score, review.issues)
            if quality_reviewer.needs_retranslation(review):
                with llm_call_profile(ctx) if ctx else _nullcontext():
                    retry_response = self.provider.translate(
                        text=text,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        block_type=block_type,
                        context_hint=f"{context}\nPrevious issues: {review.summary}",
                        document_type=document_profile.document_type if document_profile else "",
                    )
                if retry_response.success:
                    translated = retry_response.translated_text

        # Cache the result
        if translation_cache and not _is_echo_output(text, translated):
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
