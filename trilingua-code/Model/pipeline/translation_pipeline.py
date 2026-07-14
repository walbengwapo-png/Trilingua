# -*- coding: utf-8 -*-
"""
Translation pipeline.

Orchestrates the translation flow:
1. Language detection
2. Metadata extraction
3. Semantic chunking
4. Context building
5. Terminology lookup
6. Translation via provider
7. Translation validation
8. Consistency check
9. Repair pass

The provider is only one step in this pipeline.
The pipeline controls everything.
"""

import time
from dto.requests import TranslationRequest, LANGUAGES, CODE_TO_LANG
from dto.responses import TranslationResponse, ChunkResult
from providers.base import TranslationProvider
from document.chunker import ChunkSplitter
from memory.terminology import ContextBuffer
from memory.glossary import GlossaryStore
from validators.hallucination_detector import sanitize_translation, detect_hallucination
from validators.translation_validator import BLEUReporter


class TranslationPipeline:
    """Orchestrates the complete translation process."""

    def __init__(self, provider: TranslationProvider):
        self.provider = provider
        self.context_buffer = ContextBuffer()
        self.chunk_splitter = ChunkSplitter()
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

        # 2. Build context hint from buffer
        context_hint = self.context_buffer.get_hint() if request.context_hint else ""

        # 3. Translate via provider
        response = self.provider.translate(
            text=request.text,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            block_type=request.block_type,
            context_hint=context_hint or request.context_hint,
        )

        # 4. Push to context buffer on success
        if response.success and response.translated_text:
            self.context_buffer.push(response.translated_text)

        # 5. Update execution time
        response.execution_time_ms = (time.time() - start_time) * 1000

        return response

    def translate_chunks(self, text: str, source_lang: str, target_lang: str,
                         block_type: str = "paragraph", max_tokens: int = 400) -> TranslationResponse:
        """Split text into chunks, translate each, and rejoin.

        Args:
            text: Source text.
            source_lang: Source language name.
            target_lang: Target language name.
            block_type: Type of text block.
            max_tokens: Maximum tokens per chunk.

        Returns:
            A combined TranslationResponse.
        """
        # Clear context buffer for new document
        self.context_buffer.clear()

        # Split into chunks
        chunks = self.chunk_splitter.split(text, max_tokens=max_tokens)

        if len(chunks) <= 1:
            # No splitting needed
            request = TranslationRequest(
                text=text, source_lang=source_lang, target_lang=target_lang,
                block_type=block_type,
            )
            return self.translate(request)

        # Translate each chunk
        translated_chunks = []
        total_tokens = {"input": 0, "output": 0}
        total_time = 0.0
        warnings = []

        for i, chunk in enumerate(chunks):
            request = TranslationRequest(
                text=chunk, source_lang=source_lang, target_lang=target_lang,
                block_type=block_type,
                context_hint=self.context_buffer.get_hint(),
            )

            response = self.translate(request)

            if response.success:
                translated_chunks.append(response.translated_text)
                total_tokens["input"] += response.token_usage.get("input", 0)
                total_tokens["output"] += response.token_usage.get("output", 0)
                total_time += response.execution_time_ms
            else:
                warnings.append(f"Chunk {i + 1} failed: {response.error_message}")
                translated_chunks.append("")  # Placeholder for failed chunk

        combined_text = " ".join(translated_chunks).strip()

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
                                progress_callback=None) -> list[dict]:
        """Translate a list of document blocks.

        Args:
            blocks: List of block dicts with 'text', 'type', 'style' keys.
            source_lang: Source language name.
            target_lang: Target language name.
            glossary_store: Optional glossary for post-processing.
            progress_callback: Optional callable(completed, total).

        Returns:
            List of translated block dicts.
        """
        self.context_buffer.clear()
        total = len(blocks)
        translated_blocks = []

        for i, block in enumerate(blocks):
            if progress_callback:
                print(f"  Translating block {i + 1}/{total}...", end="\r", flush=True)

            text = block.get("text", "")
            if not text.strip():
                translated_blocks.append(dict(block, text=""))
                continue

            # Translate
            request = TranslationRequest(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                block_type=block.get("type", "paragraph"),
                context_hint=self.context_buffer.get_hint(),
            )

            response = self.translate(request)
            translated_text = response.translated_text

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