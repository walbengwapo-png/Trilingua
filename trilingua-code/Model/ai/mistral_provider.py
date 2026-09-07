# -*- coding: utf-8 -*-
"""
Mistral AI analysis provider for non-translation AI tasks.

This provider handles NON-TRANSLATION AI tasks:
- Document analysis
- Quality review
- Layout planning

It communicates with Mistral's /v1/chat/completions endpoint and expects
structured JSON responses. Uses the SAME Mistral API key as the translation
provider, but can use a different (potentially smaller) model.

This is NOT a translation provider. Translation is handled by
Model/providers/mistral.py.
"""

import os
import json
import time as _time
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import requests
from typing import Any

from .base import AIAnalysisProvider

MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODELS_URL = "https://api.mistral.ai/v1/models"


class MistralAnalysisError(RuntimeError):
    """Actionable API failure, including the provider's retry window."""

    def __init__(self, message, retry_after=0):
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after_seconds(response, default):
    value = response.headers.get("Retry-After", "")
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return default


class MistralAnalysisProvider(AIAnalysisProvider):
    """Analysis provider using Mistral AI API.

    Default model is 'mistral-small-latest' — fast and capable of
    structured JSON output. Can be overridden via the MISTRAL_ANALYSIS_MODEL
    env var. The API key is shared with the translation provider
    (MISTRAL_API_KEY).
    """

    def __init__(self, api_key: str = "", model: str = "", max_attempts: int = 3):
        self._max_attempts = max(1, max_attempts)
        self._api_key = api_key or os.environ.get("MISTRAL_API_KEY", "")
        self._model = model or os.environ.get(
            "MISTRAL_ANALYSIS_MODEL", "mistral-small-latest"
        )

    @property
    def name(self) -> str:
        return "mistral_analysis"

    @property
    def model_name(self) -> str:
        return self._model

    def analyze(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Send a prompt and return structured JSON.

        The system prompt MUST instruct the model to return valid JSON.
        The user prompt MUST contain the data to analyze.

        Args:
            system_prompt: System instructions (should request JSON output).
            user_prompt: The text/data to analyze.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            RuntimeError: If response is empty, non-JSON, or analysis fails.
            ConnectionError: If Mistral API is unreachable.
        """
        if not self._api_key:
            raise MistralAnalysisError("MISTRAL_API_KEY is not set")

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 8192,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        for attempt in range(self._max_attempts):
            delay = 2 ** attempt
            try:
                resp = requests.post(
                    MISTRAL_CHAT_URL, headers=headers, json=payload,
                    timeout=(10, 120),
                )
                if resp.status_code >= 400:
                    message = self._http_error(resp)
                    transient = resp.status_code in (408, 429, 500, 502, 503, 504)
                    delay = _retry_after_seconds(
                        resp, 30 * (2 ** attempt) if resp.status_code == 429 else delay
                    )
                    if not transient or attempt == self._max_attempts - 1 or delay > 60:
                        raise MistralAnalysisError(message, retry_after=delay if transient else 0)
                    print(f"  [MistralAnalysis] {message}; retrying in {delay:g}s "
                          f"(attempt {attempt + 2}/{self._max_attempts})")
                    _time.sleep(delay)
                    continue

                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    raise RuntimeError("Empty choices in Mistral analysis response")
                choice = choices[0]
                if choice.get("finish_reason") == "length":
                    raise RuntimeError("Mistral analysis JSON was truncated at the output token limit")
                content = choice.get("message", {}).get("content")
                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("Empty or unsupported Mistral analysis content")

                # Retain compatibility with older models that wrap JSON in prose.
                content = content.strip()
                candidates = [content]
                fenced = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
                if fenced:
                    candidates.append(fenced.group(1))
                embedded = re.search(r'(\{.*\})', content, re.DOTALL)
                if embedded:
                    candidates.append(embedded.group(1))
                for candidate in candidates:
                    try:
                        result = json.loads(candidate)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(result, dict):
                        return result
                raise RuntimeError("Mistral analysis did not return a JSON object")

            except MistralAnalysisError:
                raise
            except (requests.exceptions.RequestException, RuntimeError,
                    ValueError, TypeError, AttributeError) as exc:
                if isinstance(exc, requests.exceptions.Timeout):
                    message = "Mistral analysis request timed out"
                elif isinstance(exc, requests.exceptions.ConnectionError):
                    message = "Cannot connect to the Mistral API; check network connectivity"
                else:
                    message = str(exc).replace(self._api_key, "[REDACTED]")
                if attempt == self._max_attempts - 1:
                    raise MistralAnalysisError(
                        f"Mistral analysis failed after {self._max_attempts} "
                        f"attempt(s): {message}"
                    ) from exc
                print(f"  [MistralAnalysis] {message}; retrying in {delay:g}s "
                      f"(attempt {attempt + 2}/{self._max_attempts})")
                _time.sleep(delay)

    def _http_error(self, response):
        # Keep the status/code and provider message, never authorization headers
        # or document content. Mistral can return an HTML error via a proxy.
        detail = ""
        try:
            data = response.json()
            if isinstance(data, dict):
                detail = str(data.get("message", ""))
                if data.get("code") is not None:
                    detail += f" (code {data['code']})"
        except ValueError:
            pass
        detail = detail.replace(self._api_key, "[REDACTED]")[:500]
        guidance = {
            401: "Check MISTRAL_API_KEY.",
            402: "Check Mistral workspace billing.",
            403: "Check Mistral workspace/model access.",
            404: "Check MISTRAL_ANALYSIS_MODEL.",
            429: "Check Mistral workspace rate limits and quota; retry after cooldown.",
        }.get(response.status_code, "")
        return f"Mistral analysis HTTP {response.status_code}: {detail}. {guidance}".strip()

    def health(self) -> dict[str, Any]:
        """Check if Mistral API is accessible and the configured model is available."""
        if not self._api_key:
            return {
                "status": "unavailable",
                "provider": self.name,
                "model": self._model,
                "error": "MISTRAL_API_KEY not set",
            }

        try:
            headers = {"Authorization": f"Bearer {self._api_key}"}
            resp = requests.get(MISTRAL_MODELS_URL, headers=headers, timeout=10)

            if resp.status_code == 200:
                models_data = resp.json().get("data", [])
                model_ids = [m.get("id", "") for m in models_data]
                model_available = self._model in model_ids

                return {
                    "status": "ok" if model_available else "degraded",
                    "provider": self.name,
                    "model": self._model,
                    "model_available": model_available,
                    "available_models": model_ids[:10] if model_ids else [],
                }

            return {
                "status": "unavailable",
                "provider": self.name,
                "model": self._model,
                "error": f"Mistral API returned status {resp.status_code}",
            }

        except Exception as e:
            return {
                "status": "unavailable",
                "provider": self.name,
                "model": self._model,
                "error": str(e),
            }
