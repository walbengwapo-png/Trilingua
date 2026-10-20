# -*- coding: utf-8 -*-
"""
Abstract base class for all translation providers.

Every provider must implement this interface.
Providers are responsible ONLY for communicating with an AI API
and returning normalized responses. They contain NO prompt engineering,
NO document logic, and NO validation logic.
"""

import time as _time
from abc import ABC, abstractmethod
from typing import Optional
from dto.pipeline import TranslationUnit, TranslationUnitResult
from dto.responses import TranslationResponse


def _protected_spans_hint(unit: TranslationUnit) -> str:
    """Build a short prompt hint asking the provider to preserve masked spans."""
    if not unit.protected_spans:
        return ""
    kinds = ", ".join(sorted({span.kind for span in unit.protected_spans}))
    return (
        "Do not translate, reorder or alter the following kinds of spans "
        "in any way (keep them character-for-character identical): "
        f"{kinds}. End of instruction."
    )


class TranslationProvider(ABC):
    """Abstract interface for AI translation providers."""

    @abstractmethod
    def translate(self, text: str, source_lang: str, target_lang: str,
                  block_type: str = "paragraph", context_hint: str = "",
                  document_type: str = "", response_format: str = "text") -> TranslationResponse:
        """Translate a single text block.

        Args:
            text: The source text to translate.
            source_lang: Source language name (e.g. "English").
            target_lang: Target language name (e.g. "Cebuano").
            block_type: Type of text block (paragraph, header, table_cell, etc.).
            context_hint: Optional context from previous translations.
            response_format: "text" for normal translation or "json" for
                ID-keyed batch output.

        Returns:
            A normalized TranslationResponse.
        """
        pass

    def translate_many(self, units, source_lang: str, target_lang: str,
                       context_hint: str = "", document_type: str = "",
                       ctx=None) -> list:
        """Translate many ``TranslationUnit`` objects without batching.

        Default compatibility implementation: iterates ``translate()`` once per
        unit and returns an ordered list of ``TranslationUnitResult`` records
        aligned with ``units``. Providers may override with a batch-capable
        implementation; none are required to in this release.

        Args:
            units: Sequence of TranslationUnit objects.
            source_lang: Source language name (e.g. "English").
            target_lang: Target language name (e.g. "Cebuano").
            context_hint: Optional shared context from the document.
            document_type: Type of source document.
            ctx: Optional pipeline context for stats bookkeeping.

        Returns:
            List of TranslationUnitResult, one per unit in input order.
        """
        results = []
        for idx, unit in enumerate(units):
            parts = [part for part in (context_hint, unit.previous_context, unit.next_context) if part]
            hint = "\n".join(parts)
            span_hint = _protected_spans_hint(unit)
            if span_hint:
                hint = "\n".join(p for p in (hint, span_hint) if p)
            started = _time.time()
            response = self.translate(
                text=unit.source_text,
                source_lang=source_lang,
                target_lang=target_lang,
                block_type=unit.role,
                context_hint=hint,
                document_type=document_type,
            )
            elapsed_ms = (_time.time() - started) * 1000.0
            results.append(TranslationUnitResult(
                unit_id=unit.unit_id,
                status="translated" if response.success else "failed",
                translated_text=response.translated_text if response.success else "",
                error=response.error_message if not response.success else "",
                provider=response.provider or getattr(self, "name", ""),
                model=response.model or getattr(self, "model_name", ""),
                execution_time_ms=elapsed_ms,
            ))
        return results

    @property
    def provider_names(self) -> tuple[str, ...]:
        """Return every provider that can service this translation route."""
        return (self.name,)

    @property
    def batch_limits(self) -> dict:
        """Return conservative limits for ID-keyed batch translation."""
        return {"max_batch_chars": 1500, "max_batch_items": 5}

    @property
    def max_concurrency(self) -> Optional[int]:
        """Return a provider concurrency cap, when one is required."""
        return None

    @abstractmethod
    def health(self) -> dict:
        """Check if the provider is available and return status info.

        Returns:
            dict with keys: status (str), model (str), provider (str)
        """
        pass

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """Estimate the number of tokens in a text string.

        Args:
            text: The text to estimate.

        Returns:
            Estimated token count.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name (e.g. 'gptoss', 'gemini')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the active model name."""
        pass
