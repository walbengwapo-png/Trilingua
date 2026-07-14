# -*- coding: utf-8 -*-
"""
Google Gemini translation provider.

STUB — Future implementation.
When ready, implement the TranslationProvider interface
to communicate with the Google Gemini API.

API: https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent
"""

from dto.responses import TranslationResponse
from .base import TranslationProvider


class GeminiProvider(TranslationProvider):
    """Future: Translation provider using Google Gemini API."""

    def __init__(self, api_key: str = "", model: str = "gemini-pro"):
        raise NotImplementedError(
            "Gemini provider is a stub for future implementation. "
            "Implement translate(), health(), and estimate_tokens() methods."
        )

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return "gemini-pro"

    def translate(self, text, source_lang, target_lang, block_type="paragraph", context_hint=""):
        raise NotImplementedError

    def health(self):
        return {"status": "stub", "provider": self.name, "model": self.model_name}

    def estimate_tokens(self, text):
        return len(text.split())