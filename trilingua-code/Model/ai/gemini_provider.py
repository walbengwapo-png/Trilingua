# -*- coding: utf-8 -*-
"""Google Gemini provider for structured document-analysis tasks."""

import json
import os
import re
import time as _time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from .base import AIAnalysisProvider


GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_INTERACTIONS_URL = f"{GEMINI_API_BASE_URL}/interactions"


class GeminiAnalysisError(RuntimeError):
    """Actionable Gemini API failure, including the provider retry window."""

    def __init__(self, message: str, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after_seconds(response, default: float) -> float:
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


def _response_text(data: dict) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data.get('promptFeedback', {})}")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text.strip():
        reason = candidates[0].get("finishReason", "unknown")
        raise RuntimeError(f"Gemini returned empty content (finish reason: {reason})")
    return text.strip()


def _interaction_text(data: dict) -> str:
    """Extract text from the current Interactions API steps schema."""
    parts = []
    for step in data.get("steps") or []:
        if step.get("type") != "model_output":
            continue
        for content in step.get("content") or []:
            if content.get("type") == "text" and content.get("text"):
                parts.append(content["text"])
    # Keep compatibility with the schema used before the May 2026 API change.
    if not parts:
        for output in data.get("outputs") or []:
            if output.get("type") == "text" and output.get("text"):
                parts.append(output["text"])
    text = "".join(parts).strip()
    if not text:
        raise RuntimeError(f"Gemini Interactions returned no text: {data.get('status', 'unknown')}")
    return text


def _balanced_json_object(text: str) -> str | None:
    """Return the first balanced brace-delimited object in *text*.

    A model can wrap its JSON in prose or place an explanatory sentence after
    the object.  Unlike a greedy single-pass regex (which stops at the last
    closing brace and can swallow a second object), this scans brace-by-brace
    while respecting string literals, so a lone nested object is extracted
    losslessly.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


class GeminiAnalysisProvider(AIAnalysisProvider):
    """Analysis provider using Gemini JSON responses."""

    def __init__(self, api_key: str = "", model: str = "", max_attempts: int = 3):
        self._max_attempts = max(1, max_attempts)
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model = model or os.environ.get("GEMINI_ANALYSIS_MODEL", "gemini-2.5-flash")

    @property
    def name(self) -> str:
        return "gemini_analysis"

    @property
    def model_name(self) -> str:
        return self._model

    def _thinking_config(self) -> dict[str, Any]:
        """Use the latency control supported by the selected Gemini family."""
        if self._model.startswith("gemini-2.5"):
            # Gemini 2.5 Flash allows thinking to be disabled. Document
            # profiling is a bounded extraction task, so it does not need a
            # large hidden reasoning budget before translation can start.
            return {"thinkingBudget": int(os.environ.get("GEMINI_THINKING_BUDGET", "0"))}
        # Gemini 3 models use thinkingLevel rather than thinkingBudget.  The
        # documented minimal level keeps analysis responsive; it is still not
        # an unsupported attempt to disable Gemini 3 thinking entirely.
        return {"thinkingLevel": os.environ.get("GEMINI_THINKING_LEVEL", "minimal")}

    def _uses_interactions_api(self) -> bool:
        return self._model.startswith("gemini-3.")

    def analyze(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not self._api_key:
            raise GeminiAnalysisError("GEMINI_API_KEY is not set")

        url = f"{GEMINI_API_BASE_URL}/models/{self._model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                # Document-analysis responses are structured JSON, not a full
                # document translation. A bounded response avoids spending a
                # very large Gemini 3.6 reasoning budget on this pre-pass.
                "maxOutputTokens": int(os.environ.get("GEMINI_ANALYSIS_MAX_OUTPUT_TOKENS", "2048")),
                "responseMimeType": "application/json",
                "thinkingConfig": self._thinking_config(),
            },
        }
        if self._uses_interactions_api():
            # Gemini 3 is optimized for the current Interactions API.  The
            # legacy generateContent endpoint can hold a request until hidden
            # reasoning finishes, which left document jobs stalled before the
            # translation phase.  Use the documented, stateless API instead.
            url = GEMINI_INTERACTIONS_URL
            payload = {
                "model": self._model,
                "system_instruction": system_prompt,
                "input": user_prompt,
                "store": False,
                "generation_config": {
                    "temperature": 0.1,
                    "max_output_tokens": int(os.environ.get("GEMINI_ANALYSIS_MAX_OUTPUT_TOKENS", "2048")),
                    "thinking_level": os.environ.get("GEMINI_THINKING_LEVEL", "low"),
                },
                "response_format": {"type": "text", "mime_type": "application/json"},
            }
        headers = {"Content-Type": "application/json", "x-goog-api-key": self._api_key}

        for attempt in range(self._max_attempts):
            delay = 2 ** attempt
            try:
                response = requests.post(
                    url, headers=headers, json=payload,
                    timeout=(10, int(os.environ.get("GEMINI_ANALYSIS_TIMEOUT_SECONDS", "30"))),
                )
                if response.status_code >= 400:
                    message = self._http_error(response)
                    transient = response.status_code in (408, 429, 500, 502, 503, 504)
                    delay = _retry_after_seconds(
                        response, 30 * (2 ** attempt) if response.status_code == 429 else delay
                    )
                    if not transient or attempt == self._max_attempts - 1 or delay > 60:
                        raise GeminiAnalysisError(message, retry_after=delay if transient else 0)
                    print(f"  [GeminiAnalysis] {message}; retrying in {delay:g}s "
                          f"(attempt {attempt + 2}/{self._max_attempts})")
                    _time.sleep(delay)
                    continue

                content = (_interaction_text(response.json())
                           if self._uses_interactions_api() else _response_text(response.json()))
                candidates = [content]
                # Gemini normally honours responseMimeType, but a model can
                # still wrap JSON in a Markdown fence.  These must be regex
                # escapes (not literal ``\\s`` / ``\\n`` characters).
                fenced = re.search(r"```(?:json)?\s*\n(.*?)\n```", content, re.DOTALL)
                if fenced:
                    candidates.append(fenced.group(1))
                # Balanced-brace extraction handles fenceless nested JSON even
                # when prose precedes or follows the object.
                if _balanced_json_object(content):
                    candidates.append(_balanced_json_object(content))
                embedded = re.search(r"(\{.*\})", content, re.DOTALL)
                if embedded:
                    candidates.append(embedded.group(1))
                # Deduplicate while preserving order (prose-wrapped responses
                # produce identical candidates through multiple paths).
                seen: set[str] = set()
                for candidate in candidates:
                    if candidate in seen:
                        continue
                    seen.add(candidate)
                    try:
                        result = json.loads(candidate)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(result, dict):
                        return result
                raise RuntimeError("Gemini analysis did not return a JSON object")
            except GeminiAnalysisError:
                raise
            except (requests.exceptions.RequestException, RuntimeError, ValueError,
                    TypeError, AttributeError) as error:
                if isinstance(error, requests.exceptions.Timeout):
                    message = "Gemini analysis request timed out"
                elif isinstance(error, requests.exceptions.ConnectionError):
                    message = "Cannot connect to the Gemini API; check network connectivity"
                else:
                    message = str(error).replace(self._api_key, "[REDACTED]")
                if attempt == self._max_attempts - 1:
                    raise GeminiAnalysisError(
                        f"Gemini analysis failed after {self._max_attempts} attempt(s): {message}"
                    ) from error
                print(f"  [GeminiAnalysis] {message}; retrying in {delay:g}s "
                      f"(attempt {attempt + 2}/{self._max_attempts})")
                _time.sleep(delay)

        raise GeminiAnalysisError("Gemini analysis failed without a response")

    def _http_error(self, response) -> str:
        detail = ""
        try:
            data = response.json()
            if isinstance(data, dict):
                error = data.get("error", data)
                if isinstance(error, dict):
                    detail = str(error.get("message", ""))
                    if error.get("status"):
                        detail += f" ({error['status']})"
                    if error.get("code") is not None:
                        detail += f" (code {error['code']})"
        except ValueError:
            pass
        detail = detail.replace(self._api_key, "[REDACTED]")[:500]
        guidance = {
            400: "Check the Gemini request and model configuration.",
            401: "Check GEMINI_API_KEY.",
            403: "Check Gemini API access and billing.",
            404: "Check GEMINI_ANALYSIS_MODEL.",
            429: "Check Gemini rate limits and quota; retry after cooldown.",
        }.get(response.status_code, "")
        return f"Gemini analysis HTTP {response.status_code}: {detail}. {guidance}".strip()

    def health(self) -> dict[str, Any]:
        if not self._api_key:
            return {"status": "unavailable", "provider": self.name, "model": self._model,
                    "error": "GEMINI_API_KEY not set"}
        try:
            response = requests.get(
                f"{GEMINI_API_BASE_URL}/models/{self._model}",
                headers={"x-goog-api-key": self._api_key}, timeout=10,
            )
            if response.status_code == 200:
                return {"status": "ok", "provider": self.name, "model": self._model}
            return {"status": "unavailable", "provider": self.name, "model": self._model,
                    "error": f"Gemini API returned status {response.status_code}"}
        except requests.exceptions.RequestException as error:
            return {"status": "unavailable", "provider": self.name, "model": self._model,
                    "error": str(error).replace(self._api_key, "[REDACTED]")}
