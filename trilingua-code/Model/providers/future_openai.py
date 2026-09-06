# -*- coding: utf-8 -*-
"""
OpenAI translation provider.

STUB — Future implementation.
When ready, implement the TranslationProvider interface
to communicate with the OpenAI API.

API: https://api.openai.com/v1/chat/completions
Model options: gpt-4o, gpt-4-turbo, gpt-3.5-turbo
"""

from dto.responses import TranslationResponse
from .base import TranslationProvider


class OpenAIProvider(TranslationProvider):
    """Future: Translation provider using OpenAI API."""

    def __init__(self, api_key: str = "", model: str = "gpt-4o"):
        raise NotImplementedError(
            "OpenAI provider is a stub for future implementation. "
            "Implement translate(), health(), and estimate_tokens() methods."
        )

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return "gpt-4o"

    def translate(self, text, source_lang, target_lang, block_type="paragraph", context_hint=""):
        raise NotImplementedError

    def health(self):
        return {"status": "stub", "provider": self.name, "model": self.model_name}

    def estimate_tokens(self, text):
        return len(text.split())