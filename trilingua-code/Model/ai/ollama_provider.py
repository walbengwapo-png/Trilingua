# -*- coding: utf-8 -*-
"""
GPT-OSS (Ollama) provider for AI analysis tasks.

This provider handles NON-TRANSLATION AI tasks:
- Document analysis
- Quality review
- Layout planning

It communicates with Ollama's /api/chat endpoint and expects
structured JSON responses. Uses a SEPARATE (typically smaller)
model than the translation provider.

This is NOT a translation provider. Translation is handled by
Model/providers/gptoss.py and Model/providers/mistral.py.
"""

import os
import json
import time as _time
import requests
from typing import Any

from .base import AIAnalysisProvider


class OllamaAnalysisProvider(AIAnalysisProvider):
    """Analysis provider using GPT-OSS via Ollama Cloud.

    Default model is 'llama3.1:8b' — smaller and faster than the
    translation model ('gpt-oss:20b-cloud'). Analysis tasks don't
    need a large model; they need fast, structured JSON output.

    The model can be overridden via the OLLAMA_ANALYSIS_MODEL env var.
    The API URL is shared with the translation provider (OLLAMA_CLOUD_URL).
    """

    def __init__(self, api_url: str = "", model: str = ""):
        self._api_url = api_url or os.environ.get(
            "OLLAMA_CLOUD_URL", "http://localhost:11434/api/chat"
        )
        self._model = model or os.environ.get(
            "OLLAMA_ANALYSIS_MODEL", "llama3.1:8b"
        )

    @property
    def name(self) -> str:
        return "ollama_analysis"

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
            ConnectionError: If Ollama is unreachable.
        """
        start_time = _time.time()

        # Build the request — always use stream=False for analysis
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for consistent JSON
            },
        }

        last_error = ""

        for attempt in range(3):
            try:
                resp = requests.post(
                    self._api_url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=120,  # Analysis can take longer for large docs
                )

                if resp.status_code == 429:
                    wait = 2 ** attempt
                    print(f"  [OllamaAnalysis] Rate limited, retrying in {wait}s...")
                    _time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                # Extract content from the response
                content = data.get("message", {}).get("content", "").strip()
                if not content:
                    raise RuntimeError("Empty response from Ollama analysis model")

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
                    f"Ollama analysis did not return valid JSON. "
                    f"Response preview: {content[:200]}"
                )

            except requests.exceptions.ConnectionError:
                last_error = (
                    f"Cannot connect to Ollama at {self._api_url}. "
                    f"Ensure Ollama is running."
                )
                if attempt < 2:
                    print(f"  [OllamaAnalysis] Connection error, retrying ({attempt + 1}/3)...")
                    _time.sleep(2)
                    continue
                raise ConnectionError(last_error)

            except requests.exceptions.Timeout:
                last_error = "Ollama analysis request timed out"
                if attempt < 2:
                    print(f"  [OllamaAnalysis] Timeout, retrying ({attempt + 1}/3)...")
                    _time.sleep(2)
                    continue
                raise RuntimeError(last_error)

            except (requests.exceptions.RequestException, RuntimeError) as e:
                last_error = str(e)
                if attempt < 2:
                    print(f"  [OllamaAnalysis] Error: {e}, retrying ({attempt + 1}/3)...")
                    _time.sleep(1)
                    continue
                raise RuntimeError(
                    f"Ollama analysis failed after 3 attempts: {last_error}"
                )

        # Should not reach here, but just in case
        raise RuntimeError(
            f"Ollama analysis failed after 3 attempts: {last_error}"
        )

    def health(self) -> dict[str, Any]:
        """Check if Ollama is accessible and the model is available."""
        try:
            # Check connectivity via the tags endpoint
            base_url = self._api_url.replace("/api/chat", "")
            resp = requests.get(f"{base_url}/api/tags", timeout=5)

            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                model_available = self._model in model_names

                return {
                    "status": "ok" if model_available else "degraded",
                    "provider": self.name,
                    "model": self._model,
                    "model_available": model_available,
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