"""Translation-provider failover for temporary cloud API failures."""

from provider_usage import ProviderStopped, ollama_post, ollama_headers
import os
import threading
import time

from .base import TranslationProvider
from dto.responses import TranslationResponse


class FallbackTranslationProvider(TranslationProvider):
    """Use the fallback provider when the primary cannot translate a block."""

    def __init__(self, primary: TranslationProvider, fallback: TranslationProvider,
                 cooldown_seconds: float | None = None):
        self._primary = primary
        self._fallback = fallback
        self._cooldown_seconds = (
            float(os.environ.get("TRANSLATION_PRIMARY_COOLDOWN_SECONDS", "300"))
            if cooldown_seconds is None else max(0.0, float(cooldown_seconds))
        )
        self._failure = (0.0, "")
        self._fallback_failure = (0.0, "")
        self._fallback_cooldown_seconds = max(0.0, float(os.environ.get(
            "TRANSLATION_FALLBACK_COOLDOWN_SECONDS", "60"
        )))
        self._lock = threading.Lock()
        self._fallback_slots = threading.BoundedSemaphore(max(
            1, int(os.environ.get("GEMINI_FALLBACK_CONCURRENCY", "1"))
        ))

    @property
    def name(self) -> str:
        return f"{self._primary.name}_with_{self._fallback.name}_fallback"

    @property
    def model_name(self) -> str:
        return f"{self._primary.model_name}|{self._fallback.model_name}"

    @property
    def provider_names(self) -> tuple[str, ...]:
        return (self._primary.name, self._fallback.name)

    @property
    def batch_limits(self) -> dict:
        defaults = {
            "gptoss": {"max_batch_chars": 4000, "max_batch_items": 12},
            "gemini": {"max_batch_chars": 6000, "max_batch_items": 16},
        }
        primary = getattr(
            self._primary, "batch_limits",
            defaults.get(self._primary.name, {"max_batch_chars": 1500, "max_batch_items": 5}),
        )
        fallback = getattr(
            self._fallback, "batch_limits",
            defaults.get(self._fallback.name, {"max_batch_chars": 1500, "max_batch_items": 5}),
        )
        return {
            "max_batch_chars": min(primary["max_batch_chars"], fallback["max_batch_chars"]),
            "max_batch_items": min(primary["max_batch_items"], fallback["max_batch_items"]),
        }

    @property
    def max_concurrency(self):
        # The backup provider is independently serialized. Its quota must not
        # turn a healthy GPT-OSS primary route into a one-worker pipeline.
        return getattr(self._primary, "max_concurrency", None)

    @property
    def batch_provider_name(self) -> str:
        primary_limit = getattr(self._primary, "batch_limits", {
            "max_batch_chars": 6000 if self._primary.name == "gemini" else 4000
        })
        fallback_limit = getattr(self._fallback, "batch_limits", {
            "max_batch_chars": 6000 if self._fallback.name == "gemini" else 4000
        })
        limits = [(primary_limit["max_batch_chars"], self._primary.name),
                  (fallback_limit["max_batch_chars"], self._fallback.name)]
        return min(limits)[1]

    def estimate_tokens(self, text: str) -> int:
        return self._primary.estimate_tokens(text)

    def routing_state(self) -> dict:
        retry_at, error = self._failure
        return {
            "primary_provider": self._primary.name,
            "primary_model": self._primary.model_name,
            "fallback_provider": self._fallback.name,
            "fallback_model": self._fallback.model_name,
            "retry_after_seconds": round(max(0.0, retry_at - time.monotonic()), 1),
            "last_error": error,
        }

    def health(self) -> dict:
        primary = self._primary.health()
        fallback = self._fallback.health()
        route = self.routing_state()
        remaining = route["retry_after_seconds"]
        return {
            **primary,
            "provider": self.name,
            "model": self.model_name,
            **route,
            "primary_status": primary.get("status", "unknown"),
            "status": "degraded" if remaining else primary.get("status", "unknown"),
            "fallback_status": fallback.get("status", "unknown"),
        }

    def translate(self, *args, **kwargs):
        # Inspect routing state under the lock, but never hold it during a
        # healthy primary request. Holding this lock around translate() used
        # to serialize all eight GPT-OSS scheduler slots.
        with self._lock:
            retry_at, primary_error = self._failure
            use_primary = time.monotonic() >= retry_at

        if use_primary:
            try:
                response = self._primary.translate(*args, **kwargs)
            except ProviderStopped:
                raise
            except Exception as error:  # provider boundary must fail open
                response = None
                primary_error = str(error)
            else:
                if response.success:
                    with self._lock:
                        self._failure = (0.0, "")
                    return response
                primary_error = response.error_message or "unknown provider error"

            # Empty/malformed output is request-local and must not divert all
            # other healthy GPT-OSS batches to Gemini. Only service-wide
            # transport/quota failures open the primary circuit.
            if self._is_service_failure(primary_error):
                with self._lock:
                    self._failure = (
                    time.monotonic() + self._cooldown_seconds,
                    primary_error,
                )
                print(f"  [Translation] {self._primary.name} unavailable: "
                      f"{primary_error}; using {self._fallback.name} during cooldown")
            else:
                print(f"  [Translation] {self._primary.name} request failed: "
                      f"{primary_error}; trying {self._fallback.name} for this request")

        fallback_response = self.translate_secondary(*args, **kwargs)
        if fallback_response.success:
            fallback_response.warnings.append(
                f"{self._primary.name} unavailable; translated with {self._fallback.name}."
            )
            return fallback_response

        fallback_error = fallback_response.error_message or "unknown provider error"
        fallback_response.success = False
        fallback_response.error_message = (
            f"{self._primary.name} failed: {primary_error}; "
            f"{self._fallback.name} failed: {fallback_error}"
        )
        return fallback_response

    def translate_secondary(self, *args, **kwargs) -> TranslationResponse:
        """Call the backup directly for a semantically-invalid primary reply.

        Echo detection belongs to the pipeline, so it deliberately does not
        open the primary outage circuit. Gemini remains one-at-a-time.
        """
        try:
            with self._fallback_slots:
                with self._lock:
                    retry_at, prior_error = self._fallback_failure
                if time.monotonic() < retry_at:
                    return TranslationResponse(
                        translated_text="", provider=self._fallback.name,
                        model=self._fallback.model_name, success=False,
                        error_message=(
                            f"{self._fallback.name} fallback is cooling down after: "
                            f"{prior_error}"
                        ),
                    )
                response = self._fallback.translate(*args, **kwargs)
        except ProviderStopped:
            raise
        except Exception as error:
            response = TranslationResponse(
                translated_text="", provider=self._fallback.name,
                model=self._fallback.model_name, success=False,
                error_message=str(error),
            )
        if response.success:
            with self._lock:
                self._fallback_failure = (0.0, "")
            response.warnings.append(
                f"Semantic translation fallback used {self._fallback.name}."
            )
        elif self._is_service_failure(response.error_message):
            with self._lock:
                self._fallback_failure = (
                    time.monotonic() + self._fallback_cooldown_seconds,
                    response.error_message or "unknown fallback error",
                )
        return response

    @staticmethod
    def _is_service_failure(message: str) -> bool:
        lowered = (message or "").lower()
        return any(marker in lowered for marker in (
            "rate limit", "429", "timed out", "timeout", "cannot connect",
            "connection", "unavailable", "server error", "status 5",
        ))
