# -*- coding: utf-8 -*-
"""
Smart Translation Engine — translates objects using role-specific pipelines.
Handles TM lookups, LLM calls, pre/post-processing per role.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable

from intelligence.graph.document_graph import (
    DocumentObject,
    DocumentObjectGraph,
    SemanticRole,
)
from intelligence.context.context_engine import ContextEngine
from translation.registry import PipelineRegistry
from exceptions import TranslationError

logger = logging.getLogger(__name__)


class TranslationEngine:
    """Smart Translation Engine with role-specific pipelines and TM integration."""

    def __init__(
        self,
        llm_provider=None,
        max_workers: int = 3,
    ):
        """
        Args:
            llm_provider: Translation provider instance (e.g., GPTOSSProvider).
                          Must have a `translate(text, source_lang, target_lang, ...)` method.
            max_workers: Max concurrent page translations.
        """
        self._llm = llm_provider
        self._pipeline_registry = PipelineRegistry()
        self._max_workers = max_workers

    # ── Main Entry Point ──────────────────────────────────────────

    def translate_graph(
        self,
        graph: DocumentObjectGraph,
        context: ContextEngine,
        source_lang: str = "",
        target_lang: str = "",
        progress_callback: Optional[Callable] = None,
    ) -> DocumentObjectGraph:
        """Translate all objects in the graph using role-specific pipelines.

        Args:
            graph: Document object graph with semantic roles assigned.
            context: Initialized ContextEngine.
            source_lang: Source language code/name.
            target_lang: Target language code/name.
            progress_callback: Optional callable(completed, total, message).

        Returns:
            Graph with translated_text populated on each object.
        """
        pages = list(graph.pages.values())
        total_objects = len(graph.all_objects)
        completed = 0

        # Translate page by page (sequential within page, parallel across pages)
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_page = {}
            for page in pages:
                future = executor.submit(
                    self._translate_page,
                    page,
                    graph,
                    context,
                    source_lang,
                    target_lang,
                )
                future_to_page[future] = page.number

            for future in as_completed(future_to_page):
                page_num = future_to_page[future]
                try:
                    page_results = future.result()
                    completed += len(page_results)
                    if progress_callback:
                        progress_callback(
                            completed, total_objects,
                            f"Translated page {page_num}"
                        )
                except Exception as e:
                    logger.error(f"Page {page_num} translation failed: {e}")
                    if progress_callback:
                        progress_callback(
                            completed, total_objects,
                            f"Page {page_num} failed: {str(e)[:50]}"
                        )

        logger.info(
            f"Translation complete: "
            f"{completed}/{total_objects} objects translated"
        )
        return graph

    def _translate_page(
        self,
        page,
        graph: DocumentObjectGraph,
        context: ContextEngine,
        source_lang: str,
        target_lang: str,
    ) -> list[str]:
        """Translate all objects on a single page (sequential for context)."""
        translated_ids = []
        for obj in page.get_reading_order():
            if not obj.original_text.strip():
                continue

            try:
                translated_text = self._translate_object(
                    obj, context, source_lang, target_lang
                )
                obj.translated_text = translated_text
                translated_ids.append(obj.id)

                # Record in context engine for within-document reuse
                context.record_translation(
                    obj.original_text,
                    translated_text,
                    role=obj.semantic_role.name,
                    source_lang=source_lang,
                    target_lang=target_lang,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to translate object {obj.id}: {e}. Keeping original."
                )
                obj.translated_text = obj.original_text
                translated_ids.append(obj.id)

        return translated_ids

    def _translate_object(
        self,
        obj: DocumentObject,
        context: ContextEngine,
        source_lang: str,
        target_lang: str,
    ) -> str:
        """Translate a single object using its role-specific pipeline.

        Steps:
        1. Check TM → if hit, return
        2. Get role-specific pipeline config
        3. If skip_llm → return original (for answer blanks, etc.)
        4. Pre-process text
        5. Check TM again (after pre-processing)
        6. Build augmented prompt via ContextEngine
        7. Call LLM
        8. Post-process translation
        9. Return
        """
        text = obj.original_text.strip()
        if not text:
            return text

        # Step 1: TM check
        tm_result = context.get_translation(text, source_lang, target_lang)
        if tm_result:
            return tm_result

        # Step 2: Get pipeline config
        pipeline = self._pipeline_registry.get_pipeline(obj.semantic_role)

        # Step 3: Skip LLM if configured
        if pipeline.get("skip_llm", False):
            return text

        # Step 4: Pre-process
        preprocess_fn = pipeline.get("preprocess_fn")
        if preprocess_fn:
            processed_text = preprocess_fn(text)
        else:
            processed_text = text

        # Step 5: TM check again (after pre-processing)
        if processed_text != text:
            tm_result = context.get_translation(
                processed_text, source_lang, target_lang
            )
            if tm_result:
                return tm_result

        # Step 6: Build prompt via ContextEngine
        augmented_prompt = context.build_augmented_prompt(obj)

        # Step 7: Call LLM
        if self._llm:
            try:
                system_prompt = pipeline.get("system_prompt", "")
                temperature = pipeline.get("temperature", 0.5)
                max_tokens = pipeline.get("max_tokens", 500)

                translated = self._llm.translate(
                    text=processed_text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    block_type=obj.semantic_role.name.lower(),
                    context_hint=augmented_prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                translated_text = translated
            except Exception as e:
                raise TranslationError(
                    f"LLM translation failed: {e}",
                    can_retry=True,
                    context={"object_id": obj.id, "role": obj.semantic_role.name},
                )
        else:
            # No LLM configured — return original text
            translated_text = processed_text

        # Step 8: Post-process
        postprocess_fn = pipeline.get("postprocess_fn")
        if postprocess_fn:
            translated_text = postprocess_fn(text, translated_text)

        return translated_text

    # ── Batch Translation (for simple text, not graph-based) ─────

    def translate_text(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        role: SemanticRole = SemanticRole.PARAGRAPH,
        context: Optional[ContextEngine] = None,
    ) -> str:
        """Translate a single text block (for non-graph translation)."""
        pipeline = self._pipeline_registry.get_pipeline(role)

        if pipeline.get("skip_llm", False):
            return text

        preprocess_fn = pipeline.get("preprocess_fn")
        if preprocess_fn:
            processed_text = preprocess_fn(text)
        else:
            processed_text = text

        if self._llm:
            try:
                translated = self._llm.translate(
                    text=processed_text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    block_type=role.name.lower(),
                    temperature=pipeline.get("temperature", 0.5),
                    max_tokens=pipeline.get("max_tokens", 500),
                )
                translated_text = translated
            except Exception as e:
                logger.error(f"Text translation failed: {e}")
                return text
        else:
            translated_text = processed_text

        postprocess_fn = pipeline.get("postprocess_fn")
        if postprocess_fn:
            translated_text = postprocess_fn(text, translated_text)

        if context:
            context.record_translation(
                text, translated_text, role=role.name,
                source_lang=source_lang, target_lang=target_lang,
            )

        return translated_text