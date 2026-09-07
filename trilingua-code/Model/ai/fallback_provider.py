"""Keep analysis available during a primary provider outage or rate limit."""

import threading
import time

from .base import AIAnalysisProvider


class FallbackAnalysisProvider(AIAnalysisProvider):
    def __init__(self, primary, fallback, cooldown_seconds=60):
        self._primary = primary
        self._fallback = fallback
        self._cooldown_seconds = cooldown_seconds
        # Replace the pair atomically so health checks do not wait on an API
        # request while the primary-call lock is held.
        self._failure = (0.0, "")
        self._lock = threading.Lock()
        self._local = threading.local()

    @property
    def name(self):
        return self._primary.name

    @property
    def model_name(self):
        # DocumentAnalyzer reads this immediately after analyze(). Keep the
        # actual model per thread so concurrent documents retain provenance.
        return getattr(self._local, "model", self._primary.model_name)

    def analyze(self, system_prompt, user_prompt):
        with self._lock:
            if time.monotonic() >= self._failure[0]:
                try:
                    result = self._primary.analyze(system_prompt, user_prompt)
                    self._local.model = self._primary.model_name
                    self._failure = (0.0, "")
                    return result
                except (RuntimeError, ConnectionError) as exc:
                    retry_at = time.monotonic() + max(
                        self._cooldown_seconds, getattr(exc, "retry_after", 0)
                    )
                    self._failure = (retry_at, str(exc))
                    print(f"  [Analysis] {exc}; using {self._fallback.name} "
                          f"({self._fallback.model_name}) during cooldown")
            primary_error = self._failure[1]

        try:
            result = self._fallback.analyze(system_prompt, user_prompt)
        except (RuntimeError, ConnectionError) as exc:
            raise RuntimeError(
                f"Primary analysis unavailable: {primary_error}. "
                f"Fallback {self._fallback.name} failed: {exc}"
            ) from exc
        self._local.model = self._fallback.model_name
        return result

    def health(self):
        retry_at, error = self._failure
        remaining = max(0, retry_at - time.monotonic())
        return {
            "status": "degraded" if remaining else "configured",
            "provider": self._primary.name,
            "model": self._primary.model_name,
            "fallback_provider": self._fallback.name,
            "fallback_model": self._fallback.model_name,
            "retry_after_seconds": round(remaining, 1),
            "last_error": error,
        }
