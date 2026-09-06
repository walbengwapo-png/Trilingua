"""Fail over from one translation provider to another on a hard failure."""

from dto.responses import TranslationResponse
from .base import TranslationProvider


class FallbackTranslationProvider(TranslationProvider):
    """Use the secondary provider only when the primary returns a failure.

    Providers already handle their own transient retry and rate-limit logic.
    This wrapper therefore avoids duplicate requests on a successful response
    and changes provider only after that provider has exhausted its recovery.
    """

    def __init__(self, primary: TranslationProvider, fallback: TranslationProvider):
        self.primary = primary
        self.fallback = fallback

    @property
    def name(self) -> str:
        return f"{self.primary.name}_with_{self.fallback.name}_fallback"

    @property
    def model_name(self) -> str:
        return f"{self.primary.model_name}|{self.fallback.model_name}"

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        block_type: str = "paragraph",
        context_hint: str = "",
        document_type: str = "",
    ) -> TranslationResponse:
        result = self.primary.translate(
            text, source_lang, target_lang, block_type, context_hint, document_type
        )
        if result.success:
            return result

        fallback_result = self.fallback.translate(
            text, source_lang, target_lang, block_type, context_hint, document_type
        )
        if fallback_result.success:
            fallback_result.warnings.append(
                f"Primary provider {self.primary.name} failed; used {self.fallback.name} fallback."
            )
            return fallback_result

        fallback_result.error_message = (
            f"Primary ({self.primary.name}): {result.error_message}; "
            f"fallback ({self.fallback.name}): {fallback_result.error_message}"
        )
        return fallback_result

    def health(self) -> dict:
        return {
            "status": "ok",
            "provider": self.name,
            "primary": self.primary.health(),
            "fallback": self.fallback.health(),
        }

    def estimate_tokens(self, text: str) -> int:
        return self.primary.estimate_tokens(text)
