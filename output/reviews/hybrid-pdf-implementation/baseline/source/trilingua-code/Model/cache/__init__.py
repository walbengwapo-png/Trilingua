# -*- coding: utf-8 -*-
"""
Translation cache package.

Provides persistent SQLite-backed translation cache for
deduplication across documents. Replaces the in-memory
TranslationCache for cross-session persistence.

Envvars:
    TRANSLATION_CACHE_ENABLED   (default: true)
    TRANSLATION_CACHE_TTL_DAYS  (default: 30)
"""

from .sqlite_cache import SQLiteTranslationCache

__all__ = ["SQLiteTranslationCache"]