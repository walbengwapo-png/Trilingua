"""Keep analysis available during a primary provider outage or rate limit."""

import os
import threading
import time

from .base import AIAnalysisProvider


class FallbackAnalysisProvider(AIAnalysisProvider):
    def __init__(self, primary, fallback, cooldown_seconds=60,
                 min_interval_seconds=None):
        self._primary = primary
        self._fallback = fallback
        self._cooldown_seconds = cooldown_seconds
        self._min_interval_seconds = max(0.0, float(
            min_interval_seconds
            if min_interval_seconds is not None
            else os.environ.get("ANALYSIS_PRIMARY_MIN_INTERVAL_SECONDS", "4")
        ))
        # Replace the pair atomically so health checks do not wait on an API
        # request while the primary-call lock is held.
        self._failure = (0.0, "")
        self._last_primary_call_at = None
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
                    # One process-wide provider instance serves every document.
                    # Serialize and pace primary calls so separate documents cannot
                    # create a request-per-minute burst even when the web endpoint
                    # accepts them concurrently.
                    now = time.monotonic()
                    if self._last_primary_call_at is not None:
                        wait = self._min_interval_seconds - (
                            now - self._last_primary_call_at
                        )
                        if wait > 0:
                            time.sleep(wait)
                    self._last_primary_call_at = time.monotonic()
                    result = self._primary.analyze(system_prompt, user_prompt)
                    self._local.model = self._primary.model_name
                    self._failure = (0.0, "")
                    return result
                except (RuntimeError, ConnectionError) as exc:
                    retry_at = time.monotonic() + max(
                        self._cooldown_seconds, getattr(exc, "retry_after", 0)
                    )
                    self._failure = (retry_at, str(exc))
                    if self._fallback is not None:
                        print(f"  [Analysis] {exc}; using {self._fallback.name} "
                              f"({self._fallback.model_name}) during cooldown")
                    else:
                        print(f"  [Analysis] {exc}; independent AI unavailable "
                              "during cooldown")
            primary_error = self._failure[1]

        if self._fallback is None:
            raise RuntimeError(
                f"Primary analysis/review unavailable: {primary_error}"
            )

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
            "fallback_provider": self._fallback.name if self._fallback else None,
            "fallback_model": self._fallback.model_name if self._fallback else None,
            "primary_min_interval_seconds": self._min_interval_seconds,
            "retry_after_seconds": round(remaining, 1),
            "last_error": error,
        }
