# -*- coding: utf-8 -*-
"""
Translation Cache.

Hash-based translation cache that deduplicates translations within a document.
If the same source text appears multiple times (e.g., headers, footers,
repeated phrases), the cache returns the previously translated version
instead of making another API call.

This improves:
- Speed: avoids redundant API calls
- Consistency: identical source text always gets identical translation
- Cost: fewer API calls per document

The cache is cleared at the start of each document translation.
It uses MD5 hashing of the source text as the cache key.
"""

import hashlib
from typing import Any


class TranslationCache:
    """Hash-based translation cache for document-level deduplication.

    Usage:
        cache = TranslationCache()

        # Before translating:
        cached = cache.get(text, source_lang, target_lang)
        if cached is not None:
            return cached

        # After translating:
        cache.put(text, source_lang, target_lang, translated_text, metadata)
    """

    def __init__(self):
        self._cache: dict[str, str] = {}  # key -> translated_text
        self._metadata: dict[str, dict] = {}  # key -> metadata
        self._hits: int = 0
        self._misses: int = 0
        self._puts: int = 0

    def get(self, text: str, source_lang: str, target_lang: str) -> str | None:
        """Get a cached translation if available.

        Args:
            text: Source text to look up.
            source_lang: Source language.
            target_lang: Target language.

        Returns:
            Cached translated text, or None if not in cache.
        """
        key = self._make_key(text, source_lang, target_lang)
        result = self._cache.get(key)

        if result is not None:
            self._hits += 1
        else:
            self._misses += 1

        return result

    def put(self, text: str, source_lang: str, target_lang: str,
            translated_text: str, metadata: dict[str, Any] | None = None) -> None:
        """Store a translation in the cache.

        Args:
            text: Source text.
            source_lang: Source language.
            target_lang: Target language.
            translated_text: Translated text to cache.
            metadata: Optional metadata (block_index, provider, etc.)
        """
        key = self._make_key(text, source_lang, target_lang)
        self._cache[key] = translated_text
        if metadata:
            self._metadata[key] = metadata
        self._puts += 1

    def has(self, text: str, source_lang: str, target_lang: str) -> bool:
        """Check if a translation is cached."""
        key = self._make_key(text, source_lang, target_lang)
        return key in self._cache

    def clear(self) -> None:
        """Clear all cached translations. Called at start of each document."""
        self._cache.clear()
        self._metadata.clear()
        self._hits = 0
        self._misses = 0
        self._puts = 0

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "puts": self._puts,
            "hit_rate": f"{hit_rate:.1f}%",
            "cache_size": len(self._cache),
        }

    @staticmethod
    def _make_key(text: str, source_lang: str, target_lang: str) -> str:
        """Create a deterministic hash key from text and language pair.

        Uses MD5 for speed (not security). The hash is combined with
        language codes to ensure correct language matching.
        """
        normalized = text.strip().lower()
        text_hash = hashlib.md5(normalized.encode("utf-8")).hexdigest()
        return f"{text_hash}:{source_lang}:{target_lang}"