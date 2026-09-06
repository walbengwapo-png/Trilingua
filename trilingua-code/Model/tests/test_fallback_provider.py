from dto.responses import TranslationResponse
from providers.base import TranslationProvider
from providers.fallback import FallbackTranslationProvider


class StubProvider(TranslationProvider):
    def __init__(self, name, success, text=""):
        self._name = name
        self.success = success
        self.text = text
        self.calls = 0

    @property
    def name(self):
        return self._name

    @property
    def model_name(self):
        return f"{self._name}-model"

    def translate(self, *args, **kwargs):
        self.calls += 1
        return TranslationResponse(
            translated_text=self.text,
            provider=self.name,
            model=self.model_name,
            success=self.success,
            error_message="" if self.success else "unavailable",
        )

    def health(self):
        return {"status": "ok", "provider": self.name}

    def estimate_tokens(self, text):
        return len(text.split())


def test_fallback_is_not_called_when_primary_succeeds():
    primary = StubProvider("primary", True, "maayo")
    fallback = StubProvider("fallback", True, "fallback output")

    result = FallbackTranslationProvider(primary, fallback).translate(
        "good", "English", "Cebuano"
    )

    assert result.translated_text == "maayo"
    assert primary.calls == 1
    assert fallback.calls == 0


def test_fallback_returns_translation_after_primary_failure():
    primary = StubProvider("primary", False)
    fallback = StubProvider("fallback", True, "maayo")

    result = FallbackTranslationProvider(primary, fallback).translate(
        "good", "English", "Cebuano"
    )

    assert result.success
    assert result.provider == "fallback"
    assert any("Primary provider primary failed" in warning for warning in result.warnings)
    assert primary.calls == fallback.calls == 1
