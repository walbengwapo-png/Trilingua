# -*- coding: utf-8 -*-
"""
Mistral AI translation provider.

Extracted from document_translator_v3.py.
Responsible ONLY for communicating with the Mistral AI API.
Contains NO prompt engineering — prompts come from prompts/ modules.
"""

import os
import random
import re
import time
import requests
from dto.responses import TranslationResponse
from dto.requests import CODE_TO_LANG, LANGUAGES
from .base import TranslationProvider


MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

# Mistral Small 4 (mistral-small-latest) — from official model card at
# https://docs.mistral.ai/models/model-cards/mistral-small-4-0-26-03/
#   Context window: 256K tokens
#   Max output:     Not separately documented; default to 8192
#   API rate limits (Scale plan, Tier 1): ~20 RPM, 2M TPM
_ACTUAL_CONTEXT_WINDOW = 256_000
_MAX_OUTPUT_TOKENS = 8192


class MistralProvider(TranslationProvider):
    """Translation provider using Mistral AI API."""

    _POOL_SIZE = 16  # matches ThreadPoolExecutor worker count

    def __init__(self, api_key: str = "", model: str = ""):
        self._api_key = api_key or os.environ.get("MISTRAL_API_KEY", "")
        self._model = model or os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_maxsize=self._POOL_SIZE,
            pool_connections=self._POOL_SIZE,
            max_retries=0,
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    @property
    def name(self) -> str:
        return "mistral"

    @property
    def model_name(self) -> str:
        return self._model

    def translate(self, text: str, source_lang: str, target_lang: str,
                  block_type: str = "paragraph", context_hint: str = "",
                  document_type: str = "") -> TranslationResponse:
        """Translate a single text block using Mistral AI API."""
        import time as _time
        start_time = _time.time()

        if not self._api_key:
            return TranslationResponse(
                translated_text="",
                provider=self.name,
                model=self._model,
                success=False,
                error_message="MISTRAL_API_KEY environment variable is not set.",
            )

        # Build the system message and user message — use prompts module
        from prompts.specialized import get_system_prompt
        from prompts.translation import build_translation_prompt

        system_msg = get_system_prompt(document_type, target_lang)
        user_msg = build_translation_prompt(text, source_lang, target_lang, block_type)

        # Token budget — Mistral Small 4 has a 256K context window
        total_chars = len(system_msg) + len(user_msg)
        estimated_input_tokens = total_chars // 4
        available_for_output = _ACTUAL_CONTEXT_WINDOW - estimated_input_tokens
        dynamic_max_tokens = max(1, min(available_for_output, _MAX_OUTPUT_TOKENS))

        last_result = ""
        for attempt in range(3):
            try:
                resp = self._session.post(
                    MISTRAL_API_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        "temperature": 0.3,
                        "max_tokens": dynamic_max_tokens,
                    },
                    timeout=30,
                )

                if resp.status_code == 429:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    print(f"  Warning: Rate limited, retrying in {wait:.1f}s...")
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                result = resp.json()["choices"][0]["message"]["content"].strip()

                # Remove accidental markdown code block wrapping
                if result.startswith("```"):
                    result = re.sub(r'^```[\w]*\n?', '', result)
                    result = re.sub(r'\n?```$', '', result)
                    result = result.strip()

                last_result = result

                # OPTIMIZATION: Skip hallucination detection for very short blocks (<5 words)
                # Short blocks (headings, labels, single words) cannot meaningfully hallucinate
                # and the detection overhead is disproportionate to the translation work.
                src_word_count = len(text.split())
                if src_word_count >= 5:
                    # Run validation only for blocks with meaningful content
                    from validators.hallucination_detector import sanitize_translation, detect_hallucination

                    try:
                        result = sanitize_translation(result, text)
                    except RuntimeError as sanitize_err:
                        if "Hallucinated repetition" in str(sanitize_err) and attempt < 2:
                            print(f"  ⚠️  Repeated hallucination detected, retrying ({attempt + 1}/3)...")
                            time.sleep(1)
                            continue
                        elif "Hallucinated repetition" in str(sanitize_err):
                            print(f"  ⚠️  Using raw output after repetition hallucination")
                        else:
                            print(f"  ⚠️  Sanitizer warning: {sanitize_err}")

                    is_hallucinated, reason = detect_hallucination(result, text)
                    if is_hallucinated:
                        if attempt < 2:
                            print(f"  ⚠️  Hallucination detected ({reason}), retrying ({attempt + 1}/3)...")
                            time.sleep(1)
                            continue
                        else:
                            print(f"  ⚠️  Hallucination persists after 3 attempts ({reason}), attempting cleanup...")
                            cleaned = re.sub(
                                r'^(here\s+(is|are|\'s)\s+the\s+translat\S*\s*[:\-]?\s*)',
                                '', result, flags=re.IGNORECASE
                            )
                            cleaned = re.sub(
                                r'^(translat\S*\s*[:\-]\s*)', '', cleaned, flags=re.IGNORECASE
                            )
                            cleaned = re.sub(
                                r'\s*\(?\s*let\s+me\s+know\s+if\s+.*$', '', cleaned, flags=re.IGNORECASE
                            )
                            cleaned = re.sub(
                                r'\s*\(?\s*i\s+hope\s+this\s+helps\s*\)?\s*$', '', cleaned, flags=re.IGNORECASE
                            )
                            cleaned = cleaned.strip()
                            if cleaned:
                                result = cleaned

                if not result:
                    raise RuntimeError(f"Mistral returned empty translation for: {text[:60]}...")

                elapsed_ms = (_time.time() - start_time) * 1000
                return TranslationResponse(
                    translated_text=result,
                    provider=self.name,
                    model=self._model,
                    token_usage={"input": estimated_input_tokens, "output": len(result.split())},
                    execution_time_ms=elapsed_ms,
                )

            except requests.exceptions.Timeout:
                if attempt == 2:
                    elapsed_ms = (_time.time() - start_time) * 1000
                    return TranslationResponse(
                        translated_text=last_result,
                        provider=self.name,
                        model=self._model,
                        success=False,
                        error_message=f"Mistral API timed out after 3 attempts",
                        execution_time_ms=elapsed_ms,
                    )
                print(f"  Warning: Timeout, retrying ({attempt + 1}/3)...")
                time.sleep(1)

            except requests.exceptions.RequestException as e:
                if attempt == 2:
                    elapsed_ms = (_time.time() - start_time) * 1000
                    return TranslationResponse(
                        translated_text=last_result,
                        provider=self.name,
                        model=self._model,
                        success=False,
                        error_message=f"Mistral API error after 3 attempts: {e}",
                        execution_time_ms=elapsed_ms,
                    )
                print(f"  Warning: API error: {e}, retrying ({attempt + 1}/3)...")
                time.sleep(1)

        # Fallback after all retries
        elapsed_ms = (_time.time() - start_time) * 1000
        if last_result:
            return TranslationResponse(
                translated_text=last_result,
                provider=self.name,
                model=self._model,
                warnings=["Used raw output after 3 failed sanitization attempts"],
                execution_time_ms=elapsed_ms,
            )

        return TranslationResponse(
            translated_text="",
            provider=self.name,
            model=self._model,
            success=False,
            error_message="Mistral translation failed after 3 attempts.",
            execution_time_ms=elapsed_ms,
        )

    def health(self) -> dict:
        if not self._api_key:
            return {
                "status": "unavailable",
                "provider": self.name,
                "model": self._model,
                "error": "API key not configured",
            }
        return {
            "status": "ok",
            "provider": self.name,
            "model": self._model,
        }

    def estimate_tokens(self, text: str) -> int:
        return len(text.split())