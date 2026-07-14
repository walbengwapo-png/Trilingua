# -*- coding: utf-8 -*-
"""
Terminology and context management.

Provides context buffering for maintaining translation consistency
across chunks. Extracted from document_translator_v3.py Context_Buffer.
"""

from collections import deque


class ContextBuffer:
    """Sliding window of last N translated blocks for context hints."""

    def __init__(self, window_size: int = 2):
        self._buffer = deque(maxlen=window_size)

    def push(self, translated_text: str) -> None:
        self._buffer.append(translated_text)

    def get_hint(self) -> str:
        if not self._buffer:
            return ""
        return " ||| ".join(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()


class TerminologyManager:
    """Manages terminology mappings for consistent translations.

    Architecture placeholder for future:
    - Company terms
    - Academic terms
    - Medical terms
    - Legal terms
    - Government terminology
    - User-defined terminology
    """

    def __init__(self):
        self._terminology: dict[str, str] = {}

    def add_term(self, source: str, target: str) -> None:
        """Add a term mapping."""
        self._terminology[source.lower()] = target

    def add_terms(self, terms: dict[str, str]) -> None:
        """Add multiple term mappings."""
        for source, target in terms.items():
            self._terminology[source.lower()] = target

    def get(self, source: str) -> str | None:
        """Get the target translation for a source term."""
        return self._terminology.get(source.lower())

    def get_all(self) -> dict[str, str]:
        """Get all term mappings."""
        return dict(self._terminology)

    def clear(self) -> None:
        """Clear all term mappings."""
        self._terminology.clear()