# -*- coding: utf-8 -*-
"""Google Gemini translation provider."""

import os
import re
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

import requests

from dto.responses import TranslationResponse
from .base import TranslationProvider


GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_INTERACTIONS_URL = f"{GEMINI_API_BASE_URL}/interactions"
_ACTUAL_CONTEXT_WINDOW = 1_000_000

# Opt-in metadata-only diagnostics (GEMINI_DIAGNOSTIC=1). Used to capture the
# response structure of failing translation calls without ever logging document
# content: only top-level keys, status, text lengths, and the extraction path.
_GEMINI_DIAGNOSTIC = os.environ.get("GEMINI_DIAGNOSTIC", "").lower() in ("1", "true", "yes")


def _diag(message: str) -> None:
    if _GEMINI_DIAGNOSTIC:
        print(f"  [Gemini-DIAG] {message}")
# Gemini 3.6 may spend its entire 8k response budget reasoning about a short
# translation, turning a one-line request into a long timeout. Long document
# chunks can still request more than the floor below, up to this cap.
_MAX_OUTPUT_TOKENS = int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", "2048"))


def _retry_after_seconds(response, default: float) -> float:
    """Read Gemini's quota cooldown instead of immediately re-hitting 429."""
    value = response.headers.get("Retry-After", "")
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return default


def _response_text(data: dict) -> str:
    """Return the text from Gemini's first generated candidate."""
    candidates = data.get("candidates") or []
    if not candidates:
        prompt_feedback = data.get("promptFeedback", {})
        raise RuntimeError(f"Gemini returned no candidates: {prompt_feedback}")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text.strip():
        finish_reason = candidates[0].get("finishReason", "unknown")
        raise RuntimeError(f"Gemini returned empty content (finish reason: {finish_reason})")
    return text.strip()


def _interaction_text(data: dict) -> str:
    """Extract model text from the current (or legacy) Interactions response."""
    parts = []
    for step in data.get("steps") or []:
        if step.get("type") == "model_output":
            parts.extend(item.get("text", "") for item in step.get("content") or []
                         if item.get("type") == "text")
    used_legacy = False
    if not parts:
        parts.extend(item.get("text", "") for item in data.get("outputs") or []
                     if item.get("type") == "text")
        used_legacy = True
    text = "".join(parts).strip()
    if _GEMINI_DIAGNOSTIC:
        _diag(
            f"extract path={'legacy_outputs' if used_legacy else 'current_steps'} "
            f"status='{data.get('status', '')}' steps={len(data.get('steps') or [])} "
            f"outputs={len(data.get('outputs') or [])} text_len={len(text)}"
        )
    if not text:
        raise RuntimeError(f"Gemini Interactions returned no text: {data.get('status', 'unknown')}")
    return text


def _batch_response_schema(text: str) -> dict:
    """Build an exact string-valued schema for the batch IDs in a prompt."""
    block_ids = list(dict.fromkeys(re.findall(r"\[BLOCK_(\d+)\]", text)))
    return {
        "type": "object",
        "properties": {block_id: {"type": "string"} for block_id in block_ids},
        "required": block_ids,
    }


class GeminiProvider(TranslationProvider):
    """Translation provider using the Google Gemini REST API."""

    _POOL_SIZE = 16

    def __init__(self, api_key: str = "", model: str = ""):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_maxsize=self._POOL_SIZE,
            pool_connections=self._POOL_SIZE,
            max_retries=0,
        )
        self._session.mount("https://", adapter)

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def batch_limits(self) -> dict:
        return {"max_batch_chars": 6000, "max_batch_items": 16}

    @property
    def max_concurrency(self) -> int:
        return 1

    def _thinking_config(self) -> dict:
        """Keep Gemini's reasoning latency proportional to translation work."""
        if self._model.startswith("gemini-2.5"):
            return {"thinkingBudget": int(os.environ.get("GEMINI_THINKING_BUDGET", "0"))}
        return {"thinkingLevel": os.environ.get("GEMINI_THINKING_LEVEL", "minimal")}

    def _uses_interactions_api(self) -> bool:
        return self._model.startswith("gemini-3.")

    def translate(self, text: str, source_lang: str, target_lang: str,
                  block_type: str = "paragraph", context_hint: str = "",
                  document_type: str = "", response_format: str = "text") -> TranslationResponse:
        """Translate a single text block with Gemini."""
        start_time = time.time()
        if not self._api_key:
            return TranslationResponse(
                translated_text="", provider=self.name, model=self._model,
                success=False,
                error_message="GEMINI_API_KEY environment variable is not set.",
            )

        from prompts.specialized import get_system_prompt
        from prompts.translation import build_translation_prompt

        system_msg = get_system_prompt(document_type, target_lang)
        user_msg = build_translation_prompt(text, source_lang, target_lang, block_type)
        if context_hint:
            user_msg = f"Previous context: {context_hint}\n\n{user_msg}"

        estimated_input_tokens = (len(system_msg) + len(user_msg)) // 4
        estimated_source_tokens = max(1, len(text) // 4)
        # Keep short UI translations responsive while allowing proportionally
        # more output for larger document chunks.
        dynamic_max_tokens = min(
            _ACTUAL_CONTEXT_WINDOW - estimated_input_tokens,
            _MAX_OUTPUT_TOKENS,
            max(512, (estimated_source_tokens * 2) + 64),
        )
        url = f"{GEMINI_API_BASE_URL}/models/{self._model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system_msg}]},
            "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": dynamic_max_tokens,
                "thinkingConfig": self._thinking_config(),
            },
        }
        if response_format == "json":
            payload["generationConfig"]["responseMimeType"] = "application/json"
            payload["generationConfig"]["responseSchema"] = _batch_response_schema(text)
        if self._uses_interactions_api():
            url = GEMINI_INTERACTIONS_URL
            payload = {
                "model": self._model,
                "system_instruction": system_msg,
                "input": user_msg,
                "store": False,
                "generation_config": {
                    "temperature": 0.3,
                    "max_output_tokens": dynamic_max_tokens,
                    "thinking_level": os.environ.get("GEMINI_THINKING_LEVEL", "low"),
                },
            }
            if response_format == "json":
                payload["response_format"] = {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": _batch_response_schema(text),
                }
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}
        last_result = ""

        max_attempts = max(1, int(os.environ.get("GEMINI_MAX_ATTEMPTS", "1")))
        for attempt in range(max_attempts):
            try:
                response = self._session.post(
                    url, headers=headers, json=payload,
                    timeout=(10, int(os.environ.get("GEMINI_REQUEST_TIMEOUT_SECONDS", "30"))),
                )
                if response.status_code == 429:
                    wait = _retry_after_seconds(response, 0)
                    if attempt < max_attempts - 1:
                        wait = max(wait, 1.0)
                        print(f"  [Gemini] Rate limited; retrying in "
                              f"{wait:.1f}s ({attempt + 1}/{max_attempts})")
                        time.sleep(wait)
                        continue
                    return TranslationResponse(
                        translated_text="", provider=self.name, model=self._model,
                        success=False,
                        error_message=(
                            f"Gemini rate limit reached"
                            f"; retry after {wait:.0f} seconds." if wait else
                            "Gemini rate limit reached."
                        ),
                        execution_time_ms=(time.time() - start_time) * 1000,
                    )
                response.raise_for_status()
                data = response.json()
                if _GEMINI_DIAGNOSTIC:
                    _diag(
                        f"response status={response.status_code} keys={sorted(data.keys())} "
                        f"steps={len(data.get('steps') or [])} outputs={len(data.get('outputs') or [])} "
                        f"candidates={len(data.get('candidates') or [])}"
                    )
                result = (_interaction_text(data)
                          if self._uses_interactions_api() else _response_text(data))
                result = re.sub(r"^```[\w]*\n?", "", result)
                result = re.sub(r"\n?```$", "", result).strip()
                last_result = result
                if _GEMINI_DIAGNOSTIC:
                    _same = re.sub(r"\s+", " ", text.strip()).lower()
                    _out = re.sub(r"\s+", " ", result.strip()).lower()
                    _diag(
                        f"translate response_format={response_format} "
                        f"result_len={len(result)} source_len={len(text)} "
                        f"echo={bool(_same and _same == _out)}"
                    )

                if response_format != "json" and len(text.split()) >= 5:
                    from validators.hallucination_detector import sanitize_translation, detect_hallucination
                    try:
                        result = sanitize_translation(result, text)
                    except RuntimeError as error:
                        if "Hallucinated repetition" in str(error) and attempt < 2:
                            time.sleep(1)
                            continue
                    hallucinated, reason = detect_hallucination(result, text)
                    if hallucinated and attempt < 2:
                        print(f"  Warning: Hallucination detected ({reason}), retrying ({attempt + 1}/3)...")
                        time.sleep(1)
                        continue

                if not result:
                    raise RuntimeError(f"Gemini returned empty translation for: {text[:60]}...")
                return TranslationResponse(
                    translated_text=result, provider=self.name, model=self._model,
                    token_usage={"input": estimated_input_tokens, "output": len(result.split())},
                    execution_time_ms=(time.time() - start_time) * 1000,
                )
            except requests.exceptions.Timeout:
                error_message = f"Gemini API timed out after {max_attempts} attempt(s)"
            except (requests.exceptions.RequestException, RuntimeError, ValueError) as error:
                error_message = (
                    f"Gemini API error after {max_attempts} attempt(s): "
                    f"{str(error).replace(self._api_key, '[REDACTED]')}"
                )

            if attempt < max_attempts - 1:
                print(f"  Warning: {error_message}; retrying ({attempt + 1}/{max_attempts})...")
                time.sleep(1)
            else:
                return TranslationResponse(
                    translated_text=last_result, provider=self.name, model=self._model,
                    success=False, error_message=error_message,
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

        return TranslationResponse(
            translated_text="", provider=self.name, model=self._model, success=False,
            error_message=f"Gemini translation failed after {max_attempts} attempt(s).",
            execution_time_ms=(time.time() - start_time) * 1000,
        )

    def health(self) -> dict:
        if not self._api_key:
            return {"status": "unavailable", "provider": self.name, "model": self._model,
                    "error": "GEMINI_API_KEY not configured"}
        try:
            response = self._session.get(
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

    def estimate_tokens(self, text: str) -> int:
        return len(text.split())
