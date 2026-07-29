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
import requests
from typing import Any

from .base import AIAnalysisProvider

MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODELS_URL = "https://api.mistral.ai/v1/models"


class MistralAnalysisProvider(AIAnalysisProvider):
    """Analysis provider using Mistral AI API.

    Default model is 'mistral-small-latest' — fast and capable of
    structured JSON output. Can be overridden via the MISTRAL_ANALYSIS_MODEL
    env var. The API key is shared with the translation provider
    (MISTRAL_API_KEY).
    """

    def __init__(self, api_key: str = "", model: str = ""):
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
        start_time = _time.time()

        # Build the request
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 8192,
            "stream": False,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        last_error = ""

        for attempt in range(3):
            try:
                resp = requests.post(
                    MISTRAL_CHAT_URL,
                    headers=headers,
                    json=payload,
                    timeout=120,
                )

                if resp.status_code == 429:
                    wait = 2 ** attempt
                    print(f"  [MistralAnalysis] Rate limited, retrying in {wait}s...")
                    _time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                # Extract content from the chat completion response
                choices = data.get("choices", [])
                if not choices:
                    raise RuntimeError("Empty choices in Mistral analysis response")
                content = choices[0].get("message", {}).get("content", "").strip()
                if not content:
                    raise RuntimeError("Empty response from Mistral analysis model")

                # Try to parse as JSON
                # First, try direct parse
                try:
                    result = json.loads(content)
                    return result
                except json.JSONDecodeError:
                    pass

                # Try extracting JSON from markdown code block
                import re
                json_match = re.search(
                    r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL
                )
                if json_match:
                    try:
                        result = json.loads(json_match.group(1))
                        return result
                    except json.JSONDecodeError:
                        pass

                # Try finding a JSON object anywhere in the response
                json_match = re.search(r'(\{.*\})', content, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group(1))
                        return result
                    except json.JSONDecodeError:
                        pass

                raise RuntimeError(
                    f"Mistral analysis did not return valid JSON. "
                    f"Response preview: {content[:200]}"
                )

            except requests.exceptions.ConnectionError:
                last_error = (
                    f"Cannot connect to Mistral API at {MISTRAL_CHAT_URL}. "
                    f"Check network and API key."
                )
                if attempt < 2:
                    print(f"  [MistralAnalysis] Connection error, retrying ({attempt + 1}/3)...")
                    _time.sleep(2)
                    continue
                raise ConnectionError(last_error)

            except requests.exceptions.Timeout:
                last_error = "Mistral analysis request timed out"
                if attempt < 2:
                    print(f"  [MistralAnalysis] Timeout, retrying ({attempt + 1}/3)...")
                    _time.sleep(2)
                    continue
                raise RuntimeError(last_error)

            except (requests.exceptions.RequestException, RuntimeError) as e:
                last_error = str(e)
                if attempt < 2:
                    print(f"  [MistralAnalysis] Error: {e}, retrying ({attempt + 1}/3)...")
                    _time.sleep(1)
                    continue
                raise RuntimeError(
                    f"Mistral analysis failed after 3 attempts: {last_error}"
                )

        raise RuntimeError(
            f"Mistral analysis failed after 3 attempts: {last_error}"
        )

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
