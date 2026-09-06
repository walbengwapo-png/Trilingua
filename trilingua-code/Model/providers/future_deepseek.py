# -*- coding: utf-8 -*-
"""
DeepSeek translation provider.

STUB — Future implementation.
When ready, implement the TranslationProvider interface
to communicate with the DeepSeek API.

API: https://api.deepseek.com/v1/chat/completions
Model: deepseek-chat, deepseek-coder
"""

from dto.responses import TranslationResponse
from .base import TranslationProvider


class DeepSeekProvider(TranslationProvider):
    """Future: Translation provider using DeepSeek API."""

    def __init__(self, api_key: str = "", model: str = "deepseek-chat"):
        raise NotImplementedError(
            "DeepSeek provider is a stub for future implementation. "
            "Implement translate(), health(), and estimate_tokens() methods."
        )

    @property
    def name(self) -> str:
        return "deepseek"

    @property
    def model_name(self) -> str:
        return "deepseek-chat"

    def translate(self, text, source_lang, target_lang, block_type="paragraph", context_hint=""):
        raise NotImplementedError

    def health(self):
        return {"status": "stub", "provider": self.name, "model": self.model_name}

    def estimate_tokens(self, text):
        return len(text.split())