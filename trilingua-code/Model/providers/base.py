# -*- coding: utf-8 -*-
"""
Abstract base class for all translation providers.

Every provider must implement this interface.
Providers are responsible ONLY for communicating with an AI API
and returning normalized responses. They contain NO prompt engineering,
NO document logic, and NO validation logic.
"""

from abc import ABC, abstractmethod
from typing import Optional
from dto.responses import TranslationResponse


class TranslationProvider(ABC):
    """Abstract interface for AI translation providers."""

    @abstractmethod
    def translate(self, text: str, source_lang: str, target_lang: str,
                  block_type: str = "paragraph", context_hint: str = "") -> TranslationResponse:
        """Translate a single text block.

        Args:
            text: The source text to translate.
            source_lang: Source language name (e.g. "English").
            target_lang: Target language name (e.g. "Cebuano").
            block_type: Type of text block (paragraph, header, table_cell, etc.).
            context_hint: Optional context from previous translations.

        Returns:
            A normalized TranslationResponse.
        """
        pass

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
        """Return the provider name (e.g. 'gptoss', 'mistral')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the active model name."""
        pass