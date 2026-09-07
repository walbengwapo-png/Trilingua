"""Regression coverage for rate-limited merged document analysis."""

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.fallback_provider import FallbackAnalysisProvider
from ai.mistral_provider import MistralAnalysisError, MistralAnalysisProvider
from ai.ollama_provider import OllamaAnalysisProvider
from config.environment import load_engine_environment
from document.document_analyzer import DocumentAnalyzer


def response(status=200, content='{"summary":"A health program"}', headers=None):
    result = requests.Response()
    result.status_code = status
    result.headers.update(headers or {})
    body = ({"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
            if status == 200 else
            {"message": "Rate limit exceeded" if status == 429 else "Rejected", "code": "1300"})
    result._content = json.dumps(body).encode()
    return result


@pytest.fixture
def http(monkeypatch):
    post = Mock()
    sleep = Mock()
    monkeypatch.setattr("ai.mistral_provider.requests.post", post)
    monkeypatch.setattr("ai.mistral_provider._time.sleep", sleep)
    return post, sleep


def test_rate_limit_retries_honor_header_and_keep_error(http):
    post, sleep = http
    post.return_value = response(429, headers={"Retry-After": "12"})
    with pytest.raises(MistralAnalysisError, match="HTTP 429.*Rate limit exceeded.*1300") as error:
        MistralAnalysisProvider(api_key="secret").analyze("Return JSON", "test")
    assert error.value.retry_after == 12
    assert post.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [12, 12]


def test_rate_limit_without_header_uses_longer_backoff(http):
    post, sleep = http
    post.side_effect = [response(429), response()]
    assert MistralAnalysisProvider(api_key="secret").analyze("JSON", "test")["summary"]
    sleep.assert_called_once_with(30)


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422])
def test_permanent_error_is_not_retried(http, status):
    post, sleep = http
    post.return_value = response(status)
    with pytest.raises(MistralAnalysisError, match=f"HTTP {status}"):
        MistralAnalysisProvider(api_key="secret").analyze("JSON", "test")
    assert post.call_count == 1
    sleep.assert_not_called()


def test_missing_key_does_not_make_request(http, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(MistralAnalysisError, match="MISTRAL_API_KEY"):
        MistralAnalysisProvider().analyze("JSON", "test")
    http[0].assert_not_called()


@pytest.mark.parametrize("failure", [response(503), requests.Timeout(), requests.ConnectionError()])
def test_transient_error_can_recover(http, failure):
    post, sleep = http
    post.side_effect = [failure, response()]
    assert MistralAnalysisProvider(api_key="secret").analyze("JSON", "test")["summary"]
    assert post.call_count == 2
    assert sleep.call_count == 1


def test_json_mode_and_object_validation(http):
    post, _ = http
    post.side_effect = [response(content="[]"), response(content="null"), response()]
    assert MistralAnalysisProvider(api_key="secret").analyze("JSON", "test")["summary"]
    assert post.call_count == 3
    assert post.call_args.kwargs["json"]["response_format"] == {"type": "json_object"}


def test_long_retry_after_does_not_block_worker(http):
    post, sleep = http
    post.return_value = response(429, headers={"Retry-After": "300"})
    with pytest.raises(MistralAnalysisError) as error:
        MistralAnalysisProvider(api_key="secret").analyze("JSON", "test")
    assert error.value.retry_after == 300
    assert post.call_count == 1
    sleep.assert_not_called()


def test_merged_analysis_fallback_cooldown_and_recovery(http, monkeypatch):
    post, sleep = http
    post.return_value = response(429, headers={"Retry-After": "120"})
    clock = Mock(return_value=100)
    monkeypatch.setattr("ai.fallback_provider.time.monotonic", clock)
    fallback = Mock()
    fallback.name = "ollama_analysis"
    fallback.model_name = "llama3.2:1b"
    fallback.analyze.return_value = {
        "document_type": "report", "confidence": 0.8,
        "sections": [{"title": "Health", "level": 1, "start_block": 0}],
        "summary": "Community health program", "domain": "health",
        "translation_terms": [{"source": "health", "target": "panglawas"}],
    }
    provider = FallbackAnalysisProvider(
        MistralAnalysisProvider(api_key="secret", max_attempts=1), fallback
    )
    analyzer = DocumentAnalyzer(provider)
    blocks = [{"text": "Health program", "type": "heading"}]
    profile, prepass = analyzer.analyze_with_prepass(blocks, "English", "Cebuano")
    assert profile.confidence == 0.8
    assert profile.analyzer_model == "llama3.2:1b"
    assert prepass["terms"] == [("health", "panglawas")]
    clock.return_value = 161  # Still obey Mistral's 120-second window.
    analyzer.analyze_with_prepass(blocks, "English", "Cebuano")
    assert post.call_count == 1
    assert fallback.analyze.call_count == 2
    assert provider.health()["status"] == "degraded"
    assert "HTTP 429" in provider.health()["last_error"]
    sleep.assert_not_called()
    clock.return_value = 221
    post.return_value = response()
    provider.analyze("JSON", "test")
    assert post.call_count == 2
    assert provider.model_name == "mistral-small-latest"
    assert provider.health()["last_error"] == ""


def test_both_providers_fail_preserves_both_causes(http):
    post, _ = http
    post.return_value = response(429)
    fallback = Mock()
    fallback.name = "ollama_analysis"
    fallback.analyze.side_effect = ConnectionError("Ollama offline")
    provider = FallbackAnalysisProvider(
        MistralAnalysisProvider(api_key="secret", max_attempts=1), fallback
    )
    with pytest.raises(RuntimeError, match="HTTP 429.*Ollama offline"):
        provider.analyze("JSON", "test")


def test_environment_loads_analysis_settings_and_preserves_overrides(tmp_path, monkeypatch):
    settings = {
        "MISTRAL_API_KEY": '"secret" # comment',
        "MISTRAL_ANALYSIS_MODEL": "'mistral-small-latest'",
        "OLLAMA_ANALYSIS_MODEL": "llama3.2:1b # installed",
        "TRANSLATION_ANALYZER_MODE": "merged",
    }
    for key in settings:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OLLAMA_CLOUD_MODEL", "process-override")
    monkeypatch.delenv("APP_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(f"{k}={v}" for k, v in settings.items()) +
                        "\nOLLAMA_CLOUD_MODEL=file-value\nAPP_KEY=unrelated", encoding="utf-8-sig")
    load_engine_environment(env_file)
    import os
    assert os.environ["MISTRAL_API_KEY"] == "secret"
    assert os.environ["MISTRAL_ANALYSIS_MODEL"] == "mistral-small-latest"
    assert os.environ["OLLAMA_ANALYSIS_MODEL"] == "llama3.2:1b"
    assert os.environ["TRANSLATION_ANALYZER_MODE"] == "merged"
    assert os.environ["OLLAMA_CLOUD_MODEL"] == "process-override"
    assert "APP_KEY" not in os.environ


def test_ollama_fallback_requests_json(http):
    post, _ = http
    result = response()
    result._content = b'{"message":{"content":"{\\"summary\\":\\"ok\\"}"}}'
    post.return_value = result
    assert OllamaAnalysisProvider().analyze("JSON", "test") == {"summary": "ok"}
    assert post.call_args.kwargs["json"]["format"] == "json"
