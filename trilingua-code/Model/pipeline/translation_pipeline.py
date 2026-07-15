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
"""

import time
from typing import Any

from dto.requests import TranslationRequest, LANGUAGES, CODE_TO_LANG
from dto.responses import TranslationResponse, ChunkResult
from providers.base import TranslationProvider
from document.chunker import ChunkSplitter
from document.semantic_chunker import SemanticChunker, SemanticChunk
from document.document_analyzer import DocumentProfile
from memory.terminology import ContextBuffer
from memory.glossary import GlossaryStore
from memory.document_memory import DocumentMemory
from memory.translation_cache import TranslationCache
from validators.hallucination_detector import sanitize_translation, detect_hallucination
from validators.translation_validator import BLEUReporter
from validators.ai_quality_reviewer import AIQualityReviewer
from config.processing_modes import ProcessingMode


class TranslationPipeline:
    """Orchestrates the complete translation process."""

    def __init__(self, provider: TranslationProvider):
        self.provider = provider
        self.context_buffer = ContextBuffer()  # Kept for fast mode fallback
        self.chunk_splitter = ChunkSplitter()  # Kept for fallback
        self.bleu_reporter = BLEUReporter()

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        """Translate a single text block through the full pipeline.

        Args:
            request: The translation request.

        Returns:
            A normalized TranslationResponse.
        """
        start_time = time.time()

        # 1. Estimate tokens
        estimated_tokens = self.provider.estimate_tokens(request.text)

        # 2. Build context hint
        context_hint = request.context_hint
        if not context_hint:
            context_hint = self.context_buffer.get_hint()

        # 3. Translate via provider (pass document_type for specialized prompts)
        response = self.provider.translate(
            text=request.text,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            block_type=request.block_type,
            context_hint=context_hint,
            document_type=request.document_type,
        )

        # 4. Push to context buffer on success (for fast mode)
        if response.success and response.translated_text:
            self.context_buffer.push(response.translated_text)

        # 5. Update execution time
        response.execution_time_ms = (time.time() - start_time) * 1000

        return response

    def translate_chunks(self, text: str, source_lang: str, target_lang: str,
                         block_type: str = "paragraph", max_tokens: int = 400,
                         document_memory: DocumentMemory | None = None,
                         mode: ProcessingMode | None = None,
                         translation_cache: TranslationCache | None = None,
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
            translation_cache: Optional TranslationCache.
            quality_reviewer: Optional AIQualityReviewer.
            document_profile: Optional DocumentProfile for semantic chunking.

        Returns:
            A combined TranslationResponse.
        """
        # Clear context buffer for new document
        self.context_buffer.clear()

        # Split into chunks using semantic chunker or fallback
        chunks: list[SemanticChunk] | list[tuple[int, str]]

        if mode and mode.semantic_chunking and document_profile and document_profile.is_reliable():
            from document.semantic_chunker import SemanticChunker
            chunker = SemanticChunker(max_tokens=max_tokens)
            # Wrap text as a single block for the chunker
            blocks = [{"text": text, "type": block_type}]
            semantic_chunks = chunker.chunk_blocks(blocks, document_profile)
            chunks = [(c.block_indices[0] if c.block_indices else 0, c.text)
                      for c in semantic_chunks if not c.is_code]
        else:
            # Fallback to naive chunking
            chunks = [(0, c) for c in self.chunk_splitter.split(text, max_tokens=max_tokens)]

        if len(chunks) <= 1:
            # No splitting needed
            request = TranslationRequest(
                text=text, source_lang=source_lang, target_lang=target_lang,
                block_type=block_type,
                document_type=document_profile.document_type if document_profile else "",
            )
            return self.translate(request)

        # Translate each chunk
        translated_chunks = []
        total_tokens = {"input": 0, "output": 0}
        total_time = 0.0
        warnings = []
        retranslated_count = 0

        for i, (block_idx, chunk_text) in enumerate(chunks):
            # Check cache first
            if translation_cache:
                cached = translation_cache.get(chunk_text, source_lang, target_lang)
                if cached is not None:
                    translated_chunks.append(cached)
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

            response = self.translate(request)

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
                        retry_response = self.translate(retry_request)
                        if retry_response.success:
                            translated = retry_response.translated_text
                            retranslated_count += 1
                            warnings.append(f"Chunk {i + 1} retranslated (score: {review.score:.1f})")

                # Cache the result
                if translation_cache:
                    translation_cache.put(chunk_text, source_lang, target_lang, translated)

                translated_chunks.append(translated)
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
                translated_chunks.append("")

        combined_text = " ".join(translated_chunks).strip()

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

    def batch_translate_blocks(self, blocks: list[dict], source_lang: str, target_lang: str,
                                glossary_store: GlossaryStore | None = None,
                                progress_callback=None,
                                document_memory: DocumentMemory | None = None,
                                mode: ProcessingMode | None = None,
                                translation_cache: TranslationCache | None = None,
                                quality_reviewer: AIQualityReviewer | None = None,
                                semantic_chunker: Any | None = None,
                                document_profile: DocumentProfile | None = None) -> list[dict]:
        """Translate a list of document blocks.

        Supports semantic chunking (Phase 3), document memory (Phase 2),
        specialized prompts (Phase 4), AI quality review (Phase 5),
        and translation cache (Phase 6).

        Args:
            blocks: List of block dicts with 'text', 'type', 'style' keys.
            source_lang: Source language name.
            target_lang: Target language name.
            glossary_store: Optional glossary for post-processing.
            progress_callback: Optional callable(completed, total).
            document_memory: Optional DocumentMemory.
            mode: Processing mode configuration.
            translation_cache: Optional TranslationCache.
            quality_reviewer: Optional AIQualityReviewer.
            semantic_chunker: Optional SemanticChunker.
            document_profile: Optional DocumentProfile.

        Returns:
            List of translated block dicts.
        """
        self.context_buffer.clear()
        total = len(blocks)

        # Phase 3: Semantic chunking
        if mode and mode.semantic_chunking and semantic_chunker and document_profile:
            semantic_chunks = semantic_chunker.chunk_blocks(blocks, document_profile)
            # Build flat mapping: block_index -> [(chunk_text, block_indices)]
            block_chunks: dict[int, list[tuple[str, list[int]]]] = {}
            for chunk in semantic_chunks:
                for bi in chunk.block_indices:
                    if bi not in block_chunks:
                        block_chunks[bi] = []
                    block_chunks[bi].append((chunk.text, chunk.block_indices))
        else:
            # Fallback: each block translated independently
            block_chunks = None

        translated_blocks = []
        total_items = total

        for i, block in enumerate(blocks):
            if progress_callback:
                print(f"  Translating block {i + 1}/{total}...", end="\r", flush=True)

            text = block.get("text", "")
            if not text.strip():
                translated_blocks.append(dict(block, text=""))
                continue

            # Get chunks for this block
            if block_chunks and i in block_chunks:
                chunk_list = block_chunks[i]
                combined_translated_parts = []
                for chunk_text, chunk_indices in chunk_list:
                    translated = self._translate_single_chunk(
                        chunk_text, source_lang, target_lang, block,
                        document_memory, translation_cache, quality_reviewer,
                        document_profile, i,
                    )
                    combined_translated_parts.append(translated)
                translated_text = " ".join(combined_translated_parts)
            else:
                # Translate the entire block text
                translated_text = self._translate_single_chunk(
                    text, source_lang, target_lang, block,
                    document_memory, translation_cache, quality_reviewer,
                    document_profile, i,
                )

            # Apply glossary
            if glossary_store is not None:
                translated_text = glossary_store.apply(translated_text)

            # Build new block preserving metadata
            new_block = {
                "type": block["type"],
                "text": translated_text,
                "style": block.get("style", {}),
            }

            # Preserve position metadata for PDF
            for key in ("position", "page", "slide", "shape_id", "para_idx",
                        "sheet", "row", "col", "table_index"):
                if key in block:
                    new_block[key] = block[key]

            # Preserve original text for PDF expansion ratio
            if "position" in block:
                new_block["_original_text"] = block["text"]

            translated_blocks.append(new_block)

            if progress_callback:
                progress_callback(i + 1, total)

        print(f"\n  [OK] Translation complete! ({total} blocks)")
        return translated_blocks

    def _translate_single_chunk(self, text: str, source_lang: str, target_lang: str,
                                 block: dict, document_memory, translation_cache,
                                 quality_reviewer, document_profile, block_index: int) -> str:
        """Translate a single chunk with caching, memory, and quality review.

        Args:
            text: The chunk text to translate.
            source_lang: Source language.
            target_lang: Target language.
            block: Original block dict.
            document_memory: Optional DocumentMemory.
            translation_cache: Optional TranslationCache.
            quality_reviewer: Optional AIQualityReviewer.
            document_profile: Optional DocumentProfile.
            block_index: Block index in the document.

        Returns:
            Translated text.
        """
        # Check cache first
        if translation_cache:
            cached = translation_cache.get(text, source_lang, target_lang)
            if cached is not None:
                return cached

        # Build context from document memory
        context = ""
        if document_memory:
            context = document_memory.get_context_for_block(block, block_index)

        # Translate
        request = TranslationRequest(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            block_type=block.get("type", "paragraph"),
            context_hint=context,
            document_type=document_profile.document_type if document_profile else "",
        )
        response = self.translate(request)
        translated = response.translated_text

        # AI Quality Review (Phase 5)
        if quality_reviewer and response.success:
            review = quality_reviewer.review(
                source=text,
                translation=translated,
                document_type=document_profile.document_type if document_profile else "",
            )
            if quality_reviewer.needs_retranslation(review):
                retry_request = TranslationRequest(
                    text=text, source_lang=source_lang, target_lang=target_lang,
                    block_type=block.get("type", "paragraph"),
                    context_hint=f"{context}\nPrevious issues: {review.summary}",
                    document_type=document_profile.document_type if document_profile else "",
                )
                retry_response = self.translate(retry_request)
                if retry_response.success:
                    translated = retry_response.translated_text

        # Cache the result
        if translation_cache:
            translation_cache.put(text, source_lang, target_lang, translated)

        # Record in document memory
        if document_memory:
            document_memory.record_translation(text, translated, block_index)
            document_memory.extract_terms(text, translated)
            document_memory.update_abbreviations(text)

        return translated
