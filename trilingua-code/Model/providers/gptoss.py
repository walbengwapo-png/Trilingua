# -*- coding: utf-8 -*-
"""
GPT-OSS (Ollama Cloud) translation provider.

Communicates with Ollama Cloud API at http://localhost:11434/api/chat.
Always uses stream=false.
Returns only assistant.message.content.
Never exposes reasoning or provider-specific JSON.
"""

import os
import json
import time as _time
import requests
from dto.responses import TranslationResponse
from .base import TranslationProvider


class GPTOSSProvider(TranslationProvider):
    """Translation provider using GPT-OSS via Ollama Cloud."""

    def __init__(self, api_url: str = "", model: str = ""):
        self._api_url = api_url or os.environ.get("OLLAMA_CLOUD_URL", "http://localhost:11434/api/chat")
        self._model = model or os.environ.get("OLLAMA_CLOUD_MODEL", "gpt-oss:20b-cloud")

    @property
    def name(self) -> str:
        return "gptoss"

    @property
    def model_name(self) -> str:
        return self._model

    def translate(self, text: str, source_lang: str, target_lang: str,
                  block_type: str = "paragraph", context_hint: str = "",
                  document_type: str = "") -> TranslationResponse:
        """Translate a single text block using GPT-OSS via Ollama Cloud."""
        start_time = _time.time()

        # Build messages using the prompts module
        from prompts.specialized import get_system_prompt
        from prompts.translation import build_translation_prompt

        system_msg = get_system_prompt(document_type, target_lang)
        user_msg = build_translation_prompt(text, source_lang, target_lang, block_type)

        # Add context hint if provided
        if context_hint:
            user_msg = f"Previous context: {context_hint}\n\n{user_msg}"

        for attempt in range(3):
            try:
                resp = requests.post(
                    self._api_url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                        },
                    },
                    timeout=60,
                )

                if resp.status_code == 429:
                    wait = 2 ** attempt
                    print(f"  Warning: Rate limited, retrying in {wait}s...")
                    _time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                # Extract only assistant.message.content — never expose reasoning
                result = data.get("message", {}).get("content", "").strip()

                if not result:
                    raise RuntimeError(f"GPT-OSS returned empty response for: {text[:60]}...")

                # Run hallucination detection
                from validators.hallucination_detector import sanitize_translation, detect_hallucination

                try:
                    result = sanitize_translation(result, text)
                except RuntimeError as sanitize_err:
                    if "Hallucinated repetition" in str(sanitize_err) and attempt < 2:
                        print(f"  ⚠️  Repeated hallucination detected, retrying ({attempt + 1}/3)...")
                        _time.sleep(1)
                        continue
                    elif "Hallucinated repetition" in str(sanitize_err):
                        print(f"  ⚠️  Using raw output after repetition hallucination")

                is_hallucinated, reason = detect_hallucination(result, text)
                if is_hallucinated and attempt < 2:
                    print(f"  ⚠️  Hallucination detected ({reason}), retrying ({attempt + 1}/3)...")
                    _time.sleep(1)
                    continue

                # Estimate token usage from response
                token_usage = {}
                if "eval_count" in data:
                    token_usage["output"] = data["eval_count"]
                if "prompt_eval_count" in data:
                    token_usage["input"] = data["prompt_eval_count"]
                if not token_usage:
                    token_usage = {"input": len(text.split()), "output": len(result.split())}

                elapsed_ms = (_time.time() - start_time) * 1000
                return TranslationResponse(
                    translated_text=result,
                    provider=self.name,
                    model=self._model,
                    token_usage=token_usage,
                    execution_time_ms=elapsed_ms,
                )

            except requests.exceptions.ConnectionError:
                if attempt == 2:
                    elapsed_ms = (_time.time() - start_time) * 1000
                    return TranslationResponse(
                        translated_text="",
                        provider=self.name,
                        model=self._model,
                        success=False,
                        error_message="Cannot connect to Ollama Cloud at " + self._api_url +
                                      ". Ensure it is running.",
                        execution_time_ms=elapsed_ms,
                    )
                print(f"  Warning: Connection error, retrying ({attempt + 1}/3)...")
                _time.sleep(2)

            except requests.exceptions.Timeout:
                if attempt == 2:
                    elapsed_ms = (_time.time() - start_time) * 1000
                    return TranslationResponse(
                        translated_text="",
                        provider=self.name,
                        model=self._model,
                        success=False,
                        error_message="GPT-OSS request timed out",
                        execution_time_ms=elapsed_ms,
                    )
                print(f"  Warning: Timeout, retrying ({attempt + 1}/3)...")
                _time.sleep(2)

            except Exception as e:
                if attempt == 2:
                    elapsed_ms = (_time.time() - start_time) * 1000
                    return TranslationResponse(
                        translated_text="",
                        provider=self.name,
                        model=self._model,
                        success=False,
                        error_message=f"GPT-OSS error: {str(e)}",
                        execution_time_ms=elapsed_ms,
                    )
                print(f"  Warning: Error: {e}, retrying ({attempt + 1}/3)...")
                _time.sleep(1)

        elapsed_ms = (_time.time() - start_time) * 1000
        return TranslationResponse(
            translated_text="",
            provider=self.name,
            model=self._model,
            success=False,
            error_message="GPT-OSS translation failed after 3 attempts.",
            execution_time_ms=elapsed_ms,
        )

    def health(self) -> dict:
        """Check if Ollama Cloud is accessible."""
        try:
            # Use the list models endpoint or just check connectivity
            base_url = self._api_url.replace("/api/chat", "")
            resp = requests.get(f"{base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                available = self._model in model_names or not model_names
                return {
                    "status": "ok" if available else "degraded",
                    "provider": self.name,
                    "model": self._model,
                    "available_models": model_names[:5] if model_names else [],
                }
            return {
                "status": "unavailable",
                "provider": self.name,
                "model": self._model,
                "error": f"Ollama returned status {resp.status_code}",
            }
        except Exception as e:
            return {
                "status": "unavailable",
                "provider": self.name,
                "model": self._model,
                "error": str(e),
            }

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text string."""
        return len(text.split())