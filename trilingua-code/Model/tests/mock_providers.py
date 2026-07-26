"""Mock providers for deterministic regression testing.

These providers simulate LLM responses without making network calls.
They return predictable, verifiable output so the golden test set can
check structural integrity (block count, ordering, no empty translations)
without requiring a live API.
"""

import re
import time
from typing import Any

from dto.responses import TranslationResponse


class MockTranslationProvider:
    """Deterministic mock translation provider.

    Translates by reversing the text and prepending a marker.
    This makes it trivial to verify that the pipeline calls the provider
    correctly: every non-empty block should appear in the output with the
    marker, and no block should be lost.
    """

    def __init__(self, delay_ms: float = 0.0):
        self._delay = delay_ms / 1000.0

    @property
    def name(self) -> str:
        return "mock_translation"

    @property
    def model_name(self) -> str:
        return "mock_model_v0"

    def translate(self, text: str, source_lang: str = "", target_lang: str = "",
                  block_type: str = "paragraph", context_hint: str = "",
                  document_type: str = "") -> TranslationResponse:
        if self._delay:
            time.sleep(self._delay)

        if not text or not text.strip():
            return TranslationResponse(
                translated_text="",
                provider=self.name,
                model=self.model_name,
                success=True,
            )

        translated = f"[MOCK:{len(text.split())}w] {text[::-1]}"

        return TranslationResponse(
            translated_text=translated,
            provider=self.name,
            model=self.model_name,
            token_usage={"input": len(text.split()), "output": len(translated.split())},
            success=True,
        )

    def health(self) -> dict:
        return {"status": "ok", "provider": self.name, "model": self.model_name}

    def estimate_tokens(self, text: str) -> int:
        return len(text.split())


class MockAnalysisProvider:
    """Deterministic mock AI analysis provider.

    Returns a fixed, minimal JSON profile that satisfies the
    DocumentAnalyzer's parser without requiring any AI calls.
    """

    def __init__(self, delay_ms: float = 0.0):
        self._delay = delay_ms / 1000.0

    @property
    def name(self) -> str:
        return "mock_analysis"

    @property
    def model_name(self) -> str:
        return "mock_analysis_v0"

    def analyze(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if self._delay:
            time.sleep(self._delay)

        return {
            "document_type": "general_document",
            "writing_style": "formal",
            "language": "English",
            "confidence": 0.85,
            "sections": [
                {"level": 1, "title": "Introduction", "start_block": 0},
            ],
            "structure": [],
            "terminology": ["pipeline", "translation", "mock"],
            "abbreviations": [],
            "entities": [],
            "repeated_phrases": [],
            "summary": "A mock document for testing purposes.",
            "domain": "general",
            "terms": [
                {"source": "pipeline", "target": "pipeline"},
                {"source": "translation", "target": "translation"},
            ],
        }

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "provider": self.name, "model": self.model_name}
