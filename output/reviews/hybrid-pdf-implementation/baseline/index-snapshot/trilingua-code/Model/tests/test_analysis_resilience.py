"""Regression coverage for rate-limited merged document analysis."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.fallback_provider import FallbackAnalysisProvider
from ai.gemini_provider import GeminiAnalysisError, GeminiAnalysisProvider
from ai.ollama_provider import OllamaAnalysisProvider
from config.environment import load_engine_environment
from document.document_analyzer import DocumentAnalyzer
from dto.requests import DocumentTranslationRequest
from pipeline.document_context import DocumentContext
from pipeline.document_pipeline import DocumentPipeline
from providers.gemini import GeminiProvider
from validators.ai_quality_reviewer import AIQualityReviewer


def response(status=200, content='{"summary":"A health program"}', headers=None):
    result = requests.Response()
    result.status_code = status
    result.headers.update(headers or {})
    body = ({"candidates": [{"content": {"parts": [{"text": content}]}, "finishReason": "STOP"}]}
            if status == 200 else
            {"error": {"message": "Rate limit exceeded" if status == 429 else "Rejected", "code": "1300"}})
    result._content = json.dumps(body).encode()
    return result


@pytest.fixture
def http(monkeypatch):
    post = Mock()
    sleep = Mock()
    monkeypatch.setattr("ai.gemini_provider.requests.post", post)
    monkeypatch.setattr("ai.gemini_provider._time.sleep", sleep)
    return post, sleep


def test_rate_limit_retries_honor_header_and_keep_error(http):
    post, sleep = http
    post.return_value = response(429, headers={"Retry-After": "12"})
    with pytest.raises(GeminiAnalysisError, match="HTTP 429.*Rate limit exceeded.*1300") as error:
        GeminiAnalysisProvider(api_key="secret").analyze("Return JSON", "test")
    assert error.value.retry_after == 12
    assert post.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [12, 12]


def test_rate_limit_without_header_uses_longer_backoff(http):
    post, sleep = http
    post.side_effect = [response(429), response()]
    assert GeminiAnalysisProvider(api_key="secret").analyze("JSON", "test")["summary"]
    sleep.assert_called_once_with(30)


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422])
def test_permanent_error_is_not_retried(http, status):
    post, sleep = http
    post.return_value = response(status)
    with pytest.raises(GeminiAnalysisError, match=f"HTTP {status}"):
        GeminiAnalysisProvider(api_key="secret").analyze("JSON", "test")
    assert post.call_count == 1
    sleep.assert_not_called()


def test_missing_key_does_not_make_request(http, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GeminiAnalysisError, match="GEMINI_API_KEY"):
        GeminiAnalysisProvider().analyze("JSON", "test")
    http[0].assert_not_called()


@pytest.mark.parametrize("failure", [response(503), requests.Timeout(), requests.ConnectionError()])
def test_transient_error_can_recover(http, failure):
    post, sleep = http
    post.side_effect = [failure, response()]
    assert GeminiAnalysisProvider(api_key="secret").analyze("JSON", "test")["summary"]
    assert post.call_count == 2
    assert sleep.call_count == 1


def test_json_mode_and_object_validation(http):
    post, _ = http
    post.side_effect = [response(content="[]"), response(content="null"), response()]
    assert GeminiAnalysisProvider(api_key="secret").analyze("JSON", "test")["summary"]
    assert post.call_count == 3
    assert post.call_args.kwargs["json"]["generationConfig"]["responseMimeType"] == "application/json"
    assert post.call_args.kwargs["json"]["generationConfig"]["thinkingConfig"] == {
        "thinkingBudget": 0
    }


def test_gemini_3_analysis_uses_interactions_api_with_low_thinking(http):
    post, _ = http
    interaction = response()
    interaction._content = json.dumps({
        "steps": [{"type": "model_output", "content": [
            {"type": "text", "text": '{"summary":"ok"}'}
        ]}]
    }).encode()
    post.return_value = interaction
    GeminiAnalysisProvider(api_key="secret", model="gemini-3.6-flash").analyze("JSON", "test")
    assert post.call_args.args[0].endswith("/interactions")
    assert post.call_args.kwargs["json"]["generation_config"]["thinking_level"] == "low"
    assert post.call_args.kwargs["json"]["response_format"] == {
        "type": "text", "mime_type": "application/json"
    }


def test_gemini_3_translation_uses_interactions_api(monkeypatch):
    post = Mock()
    response_value = response()
    response_value._content = json.dumps({
        "steps": [{"type": "model_output", "content": [
            {"type": "text", "text": "Kumusta"}
        ]}]
    }).encode()
    post.return_value = response_value
    monkeypatch.setattr(requests.Session, "post", post)

    result = GeminiProvider(api_key="secret", model="gemini-3.6-flash").translate(
        "Hello", "English", "Cebuano"
    )

    assert result.success
    assert result.translated_text == "Kumusta"
    assert post.call_args.args[0].endswith("/interactions")
    assert post.call_args.kwargs["json"]["generation_config"]["thinking_level"] == "low"


def test_long_retry_after_does_not_block_worker(http):
    post, sleep = http
    post.return_value = response(429, headers={"Retry-After": "300"})
    with pytest.raises(GeminiAnalysisError) as error:
        GeminiAnalysisProvider(api_key="secret").analyze("JSON", "test")
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
        GeminiAnalysisProvider(api_key="secret", max_attempts=1), fallback
    )
    analyzer = DocumentAnalyzer(provider)
    blocks = [{"text": "Health program", "type": "heading"}]
    profile, prepass = analyzer.analyze_with_prepass(blocks, "English", "Cebuano")
    assert profile.confidence == 0.8
    assert profile.analyzer_model == "llama3.2:1b"
    assert prepass["terms"] == [("health", "panglawas")]
    clock.return_value = 161  # Still obey Gemini's 120-second window.
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
    assert provider.model_name == "gemini-2.5-flash"
    assert provider.health()["last_error"] == ""


def test_both_providers_fail_preserves_both_causes(http):
    post, _ = http
    post.return_value = response(429)
    fallback = Mock()
    fallback.name = "ollama_analysis"
    fallback.analyze.side_effect = ConnectionError("Ollama offline")
    provider = FallbackAnalysisProvider(
        GeminiAnalysisProvider(api_key="secret", max_attempts=1), fallback
    )
    with pytest.raises(RuntimeError, match="HTTP 429.*Ollama offline"):
        provider.analyze("JSON", "test")


def test_no_fallback_preserves_independent_roles_and_opens_circuit():
    primary = Mock()
    primary.name = "gemini_analysis"
    primary.model_name = "gemini-test"
    primary.analyze.side_effect = RuntimeError("quota exhausted")
    provider = FallbackAnalysisProvider(
        primary, None, cooldown_seconds=60, min_interval_seconds=0
    )

    with pytest.raises(RuntimeError, match="quota exhausted"):
        provider.analyze("system", "first")
    with pytest.raises(RuntimeError, match="quota exhausted"):
        provider.analyze("system", "second")

    assert primary.analyze.call_count == 1
    assert provider.health()["fallback_provider"] is None


def test_analysis_primary_calls_are_globally_paced(monkeypatch):
    clock = [100.0]
    primary = Mock(name="gemini")
    primary.name = "gemini_analysis"
    primary.model_name = "gemini-test"
    primary.analyze.return_value = {"summary": "ok"}
    fallback = Mock(name="ollama")
    fallback.name = "ollama_analysis"
    fallback.model_name = "gptoss-test"

    monkeypatch.setattr("ai.fallback_provider.time.monotonic", lambda: clock[0])
    waits = []
    def advance(seconds):
        waits.append(seconds)
        clock[0] += seconds
    monkeypatch.setattr("ai.fallback_provider.time.sleep", advance)

    provider = FallbackAnalysisProvider(
        primary, fallback, min_interval_seconds=4
    )
    provider.analyze("system", "first")
    clock[0] += 1
    provider.analyze("system", "second")

    assert waits == [3.0]
    assert primary.analyze.call_count == 2
    assert fallback.analyze.call_count == 0


def test_environment_loads_analysis_settings_and_preserves_overrides(tmp_path, monkeypatch):
    settings = {
        "GEMINI_API_KEY": '"secret" # comment',
        "GEMINI_ANALYSIS_MODEL": "'gemini-2.5-flash'",
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
    assert os.environ["GEMINI_API_KEY"] == "secret"
    assert os.environ["GEMINI_ANALYSIS_MODEL"] == "gemini-2.5-flash"
    assert os.environ["OLLAMA_ANALYSIS_MODEL"] == "llama3.2:1b"
    assert os.environ["TRANSLATION_ANALYZER_MODE"] == "merged"
    assert os.environ["OLLAMA_CLOUD_MODEL"] == "process-override"
    assert "APP_KEY" not in os.environ


def test_environment_loads_provider_role_and_gptoss_settings(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TRANSLATION_PROVIDER=gptoss\n"
        "ANALYSIS_PROVIDER=gemini\n"
        "ANALYSIS_FALLBACK_PROVIDER=ollama\n"
        "GPTOSS_MAX_ATTEMPTS=1\n"
        "QUALITY_REVIEW_BLIND=true\n",
        encoding="utf-8",
    )
    for key in (
        "TRANSLATION_PROVIDER", "ANALYSIS_PROVIDER",
        "ANALYSIS_FALLBACK_PROVIDER", "GPTOSS_MAX_ATTEMPTS",
        "QUALITY_REVIEW_BLIND",
    ):
        monkeypatch.delenv(key, raising=False)

    load_engine_environment(env_file)

    assert os.environ["TRANSLATION_PROVIDER"] == "gptoss"
    assert os.environ["ANALYSIS_PROVIDER"] == "gemini"
    assert os.environ["ANALYSIS_FALLBACK_PROVIDER"] == "ollama"
    assert os.environ["GPTOSS_MAX_ATTEMPTS"] == "1"
    assert os.environ["QUALITY_REVIEW_BLIND"] == "true"


def test_blind_quality_review_does_not_receive_analyzer_classification():
    provider = Mock()
    provider.analyze.return_value = {
        "0": {"score": 95, "issues": [], "summary": "Accurate"}
    }
    reviewer = AIQualityReviewer(provider, blind_review=True)

    reviewer.batch_review(
        [(0, "The report is ready today.", "Andam na ang taho karong adlawa.")],
        document_type="confidential_merger_analysis",
    )

    system_prompt, user_prompt = provider.analyze.call_args.args
    assert "confidential_merger_analysis" not in system_prompt
    assert "confidential_merger_analysis" not in user_prompt
    assert "The report is ready today." in user_prompt
    assert "Andam na ang taho karong adlawa." in user_prompt


def test_failed_batch_review_does_not_create_per_block_ai_request_storm():
    provider = Mock()
    provider.analyze.side_effect = RuntimeError("rate limited")
    reviewer = AIQualityReviewer(provider, blind_review=True)

    reviews = reviewer.batch_review([
        (0, "The report is ready today.", "Andam na ang taho karong adlawa."),
        (1, "The meeting starts tomorrow.", "Magsugod ang miting ugma."),
    ])

    assert provider.analyze.call_count == 1
    assert len(reviews) == 2
    assert all("deterministic checks" in item.summary for item in reviews.values())
    assert all(item.score is None and not item.available and not item.passed
               for item in reviews.values())
    assert "APP_KEY" not in os.environ


def test_failed_single_review_keeps_translation_unscored():
    provider = Mock()
    provider.analyze.side_effect = RuntimeError("rate limited")
    reviewer = AIQualityReviewer(provider, blind_review=True)

    review = reviewer.review(
        "The report is ready today.",
        "Andam na ang taho karong adlawa.",
    )

    assert review.score is None
    assert not review.available
    assert not review.passed
    assert not reviewer.needs_retranslation(review)


def test_nonfinite_review_score_is_unavailable():
    provider = Mock()
    provider.analyze.return_value = {"score": "Infinity", "issues": []}
    reviewer = AIQualityReviewer(provider, blind_review=True)

    single = reviewer.review("The report is ready today.", "Andam na ang taho karong adlawa.")
    assert single.score is None and not single.available

    provider.analyze.return_value = {"0": {"score": "NaN", "issues": []}}
    batch = reviewer.batch_review([(0, "The report is ready today.", "Andam na ang taho karong adlawa.")])
    assert batch[0].score is None and not batch[0].available


def test_ollama_fallback_requests_json(http):
    post, _ = http
    result = response()
    result._content = b'{"message":{"content":"{\\"summary\\":\\"ok\\"}"}}'
    post.return_value = result
    assert OllamaAnalysisProvider().analyze("JSON", "test") == {"summary": "ok"}
    assert post.call_args.kwargs["json"]["format"] == "json"


def test_malformed_optional_profile_fields_fail_open():
    provider = Mock()
    provider.model_name = "gemini-test"
    provider.analyze.return_value = {
        "confidence": None,
        "sections": [{"level": "not-a-number", "start_block": None}],
        "structure": [{"block_index": "unknown"}],
    }

    profile, prepass = DocumentAnalyzer(provider).analyze_with_prepass(
        [{"text": "A short report", "type": "paragraph"}], "English", "Cebuano"
    )

    assert profile.confidence == 0.0
    assert profile.sections[0].level == 1
    assert profile.sections[0].start_block == 0
    assert profile.structure[0].block_index == 0
    assert prepass == {"summary": "", "domain": "", "terms": []}


def test_docx_inplace_pipeline_runs_analysis_before_translation(monkeypatch, tmp_path):
    """Office documents must not bypass Gemini's analyzer/prepass stage."""
    analysis = Mock()
    analysis.model_name = "gemini-analysis-test"
    analysis.analyze.return_value = {
        "document_type": "business_proposal",
        "writing_style": "formal",
        "language": "English",
        "confidence": 0.9,
        "sections": [{"level": 1, "title": "Overview", "start_block": 0}],
        "terminology": ["proposal"],
        "summary": "A proposal.",
        "domain": "business",
        "translation_terms": [{"source": "proposal", "target": "sugyot"}],
    }
    provider = SimpleNamespace(name="gemini", model_name="gemini-translation-test")
    translator = Mock()
    translator.provider = provider
    translator.batch_translate_blocks.side_effect = lambda blocks, *args, **kwargs: [
        {"type": block["type"], "text": f"TL:{block['text']}"} for block in blocks
    ]
    pipeline = DocumentPipeline(translator, ai_analysis_provider=analysis)
    monkeypatch.setattr(pipeline, "_get_cache", lambda: None)

    replayed = []
    def walker(_input, _output, translate_fn, glossary_store=None, save=False):
        for block_type, text in (("heading", "Overview"), ("paragraph", "Proposal body")):
            result = translate_fn(text, block_type)
            if save:
                replayed.append(result)

    monkeypatch.setattr("pipeline.document_pipeline._translate_docx_inplace_with_translator", walker)
    request = DocumentTranslationRequest(
        file_path=str(tmp_path / "input.docx"), source_lang="English", target_lang="Cebuano",
        mode="balanced",
    )
    ctx = DocumentContext()
    ctx.start_timer()
    ctx.mode = __import__("config.processing_modes", fromlist=["BALANCED"]).BALANCED

    response = pipeline._translate_inplace(
        request, ".docx", str(tmp_path / "translated.docx"), None, ctx
    )

    assert analysis.analyze.called
    kwargs = translator.batch_translate_blocks.call_args.kwargs
    assert kwargs["document_profile"].document_type == "business_proposal"
    assert "Document context: A proposal." in kwargs["context_preamble"]
    assert replayed == ["TL:Overview", "TL:Proposal body"]
    assert response.document_type == "business_proposal"


def test_txt_pipeline_forwards_prepass_preamble_to_batch(document_pipeline, tmp_path):
    """Non-inplace (.txt) translation must forward the prepass preamble.

    The inplace DOCX path already forwards the preamble; the plain-text batch
    path must not drop it, otherwise prepass context is silently lost for the
    bulk of document translations.
    """
    src = tmp_path / "input.txt"
    src.write_text(
        "This is a short English paragraph that needs to be translated.\n"
        "A second sentence inside the same translation test document.\n",
        encoding="utf-8",
    )

    forwarded = {}
    original = document_pipeline.translation_pipeline.batch_translate_blocks
    def spy(*args, **kwargs):
        forwarded.update(kwargs)
        return original(*args, **kwargs)

    with patch.object(
        document_pipeline.translation_pipeline, "batch_translate_blocks",
        side_effect=spy,
    ):
        response = document_pipeline.translate(
            DocumentTranslationRequest(
                file_path=str(src),
                source_lang="English",
                target_lang="Cebuano",
                mode="balanced",
            )
        )

    assert response.success
    assert "context_preamble" in forwarded
    assert forwarded["context_preamble"], "prepass preamble must not be empty"
    assert "Document context:" in forwarded["context_preamble"]
