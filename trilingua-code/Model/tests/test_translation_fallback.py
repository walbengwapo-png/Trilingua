from types import SimpleNamespace
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
import pytest

from dto.responses import TranslationResponse
from providers.fallback import FallbackTranslationProvider
from providers.gptoss import GPTOSSProvider
from pipeline.translation_pipeline import TranslationPipeline, _build_batch_prompt
from dto.requests import TranslationRequest


class Provider:
    def __init__(self, name, response):
        self.name = name
        self.model_name = f"{name}-model"
        self._response = response
        self.calls = 0

    def translate(self, *args, **kwargs):
        self.calls += 1
        return self._response

    def health(self):
        return {"status": "ok", "provider": self.name, "model": self.model_name}

    def estimate_tokens(self, text):
        return len(text.split())


def test_rate_limited_gemini_falls_back_to_gptoss():
    primary = Provider("gemini", TranslationResponse(
        translated_text="", provider="gemini", model="gemini-model", success=False,
        error_message="Gemini rate limit reached.",
    ))
    fallback = Provider("gptoss", TranslationResponse(
        translated_text="Maayong buntag", provider="gptoss", model="gptoss-model",
    ))

    result = FallbackTranslationProvider(primary, fallback).translate(
        "Good morning", "English", "Cebuano"
    )

    assert result.success
    assert result.translated_text == "Maayong buntag"
    assert primary.calls == fallback.calls == 1


def test_primary_echo_uses_serialized_semantic_fallback():
    """An echoed success is not an outage, but it must reach Gemini."""
    source = "This sentence needs a real Cebuano translation."
    primary = Provider("gptoss", TranslationResponse(
        translated_text=source, provider="gptoss", model="gptoss-model",
    ))
    fallback = Provider("gemini", TranslationResponse(
        translated_text="Kinahanglan hubaron kini nga tudling-pulong sa Cebuano.",
        provider="gemini", model="gemini-model",
    ))
    pipeline = TranslationPipeline(FallbackTranslationProvider(primary, fallback))

    result = pipeline._translate_with_echo_guard(
        text=source, source_lang="English", target_lang="Cebuano",
        block_type="paragraph", context_hint="", document_type="",
    )

    assert result.success
    assert result.provider == "gemini"
    assert primary.calls == 2
    assert fallback.calls == 1


def test_fallback_cap_does_not_reduce_primary_concurrency(monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_CONCURRENCY", "1")
    primary = Provider("gptoss", TranslationResponse("Hubad"))
    primary.max_concurrency = 8
    fallback = Provider("gemini", TranslationResponse("Hubad"))
    fallback.max_concurrency = 1

    route = FallbackTranslationProvider(primary, fallback)

    assert route.max_concurrency == 8


def test_invalid_primary_batch_is_recovered_by_one_gemini_batch():
    class EchoBatchProvider(Provider):
        def translate(self, text, *args, **kwargs):
            self.calls += 1
            return TranslationResponse(
                translated_text=json.dumps({
                    "0": "The first sentence needs translation.",
                    "1": "The second sentence needs translation.",
                }), provider="gptoss", model="primary-model",
            )

    class GeminiBatchProvider(Provider):
        def translate(self, text, *args, **kwargs):
            self.calls += 1
            return TranslationResponse(
                translated_text=json.dumps({
                    "0": "Kinahanglan hubaron ang unang tudling-pulong.",
                    "1": "Kinahanglan hubaron ang ikaduhang tudling-pulong.",
                }), provider="gemini", model="fallback-model",
            )

    primary = EchoBatchProvider("gptoss", TranslationResponse(""))
    fallback = GeminiBatchProvider("gemini", TranslationResponse(""))
    pipeline = TranslationPipeline(FallbackTranslationProvider(primary, fallback))

    translated = pipeline.batch_translate_blocks(
        [
            {"type": "paragraph", "text": "The first sentence needs translation."},
            {"type": "paragraph", "text": "The second sentence needs translation."},
        ], "English", "Cebuano", translation_cache=None,
    )

    assert [block["text"] for block in translated] == [
        "Kinahanglan hubaron ang unang tudling-pulong.",
        "Kinahanglan hubaron ang ikaduhang tudling-pulong.",
    ]
    assert primary.calls == 1
    assert fallback.calls == 1


def test_primary_failure_opens_circuit_for_later_blocks():
    primary = Provider("gemini", TranslationResponse(
        translated_text="", provider="gemini", model="gemini-model", success=False,
        error_message="Gemini rate limit reached.",
    ))
    fallback = Provider("gptoss", TranslationResponse(
        translated_text="Hubad", provider="gptoss", model="gptoss-model",
    ))
    provider = FallbackTranslationProvider(primary, fallback, cooldown_seconds=300)

    provider.translate("First sentence", "English", "Cebuano")
    provider.translate("Second sentence", "English", "Cebuano")

    assert primary.calls == 1
    assert fallback.calls == 2
    assert provider.health()["status"] == "degraded"
    assert provider.batch_provider_name == "gptoss"


def test_fallback_route_does_not_serialize_healthy_primary_calls():
    class ConcurrentPrimary(Provider):
        def __init__(self):
            super().__init__("gptoss", TranslationResponse("Hubad"))
            self.active = 0
            self.maximum = 0
            self.guard = threading.Lock()
            self.barrier = threading.Barrier(2)

        def translate(self, *args, **kwargs):
            with self.guard:
                self.active += 1
                self.maximum = max(self.maximum, self.active)
            self.barrier.wait(timeout=2)
            time.sleep(0.02)
            with self.guard:
                self.active -= 1
            return self._response

    primary = ConcurrentPrimary()
    fallback = Provider("gemini", TranslationResponse("Fallback"))
    route = FallbackTranslationProvider(primary, fallback)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(
            lambda _: route.translate("Text", "English", "Cebuano"), range(2)
        ))

    assert all(result.success for result in results)
    assert primary.maximum == 2
    assert fallback.calls == 0


def test_failed_fallback_opens_its_own_circuit():
    primary = Provider("gptoss", TranslationResponse(
        "", success=False, error_message="GPT-OSS rate limit reached"
    ))
    fallback = Provider("gemini", TranslationResponse(
        "", success=False, error_message="Gemini rate limit reached"
    ))
    route = FallbackTranslationProvider(primary, fallback, cooldown_seconds=300)

    route.translate("First", "English", "Cebuano")
    route.translate("Second", "English", "Cebuano")

    assert primary.calls == 1
    assert fallback.calls == 1


def test_combined_failure_is_explicitly_marked_unsuccessful():
    """When both providers fail, the combined response must carry success=False."""
    primary = Provider("gptoss", TranslationResponse(
        translated_text="", provider="gptoss", model="gptoss-model", success=False,
        error_message="GPT-OSS request failed: model returned nothing",
    ))
    fallback = Provider("gemini", TranslationResponse(
        translated_text="", provider="gemini", model="gemini-model", success=False,
        error_message="Gemini API error",
    ))
    route = FallbackTranslationProvider(primary, fallback, cooldown_seconds=300)

    result = route.translate("Good morning", "English", "Cebuano")

    assert result.success is False
    assert result.translated_text == ""
    assert "GPT-OSS request failed" in result.error_message
    assert "Gemini API error" in result.error_message


def test_document_pipeline_raises_when_all_providers_fail():
    primary = Provider("gemini", TranslationResponse(
        translated_text="", provider="gemini", model="gemini-model", success=False,
        error_message="Gemini unavailable",
    ))
    fallback = Provider("gptoss", TranslationResponse(
        translated_text="", provider="gptoss", model="gptoss-model", success=False,
        error_message="GPT-OSS unavailable",
    ))
    pipeline = TranslationPipeline(
        FallbackTranslationProvider(primary, fallback, cooldown_seconds=300)
    )

    try:
        pipeline.batch_translate_blocks(
            [{"type": "paragraph", "text": "This must be translated correctly."}],
            "English", "Cebuano",
            translation_cache=None,
        )
    except RuntimeError as error:
        assert "Translation failed for 1 block" in str(error)
    else:
        raise AssertionError("Provider failure was incorrectly reported as success")


def test_batch_prompt_uses_the_actual_block_ids():
    prompt = _build_batch_prompt(
        [(0, "First"), (7, "Second")], "English", "Cebuano", "gemini"
    )

    assert '{"0": "...", "7": "..."}' in prompt
    assert "Use every exact BLOCK number" in prompt


def test_gptoss_honors_retry_after_and_recovers(monkeypatch):
    monkeypatch.setenv("GPTOSS_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("GPTOSS_MIN_INTERVAL_SECONDS", "0")
    waits = []
    monkeypatch.setattr("providers.gptoss._time.sleep", waits.append)

    limited = SimpleNamespace(status_code=429, headers={"Retry-After": "2"})
    success = SimpleNamespace(
        status_code=200,
        headers={},
        raise_for_status=lambda: None,
        json=lambda: {"message": {"content": "Kumusta"}},
    )
    provider = GPTOSSProvider(api_url="http://test/api/chat", model="test")
    calls = iter((limited, success))
    monkeypatch.setattr(provider._session, "post", lambda *a, **k: next(calls))

    result = provider.translate("Hello", "English", "Cebuano")

    assert result.success
    assert result.translated_text == "Kumusta"
    assert waits == [2.0]


def test_direct_ollama_cloud_uses_a_key_without_sending_it_to_local_ollama(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-cloud-key")
    cloud = GPTOSSProvider(api_url="https://ollama.com/api/chat", model="test")
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs["headers"])
        return SimpleNamespace(
            status_code=200, headers={}, raise_for_status=lambda: None,
            json=lambda: {"message": {"content": "Kumusta"}},
        )

    monkeypatch.setattr(cloud._session, "post", post)
    assert cloud.translate("Hello", "English", "Cebuano").success
    assert calls[0]["Authorization"] == "Bearer test-cloud-key"

    local = GPTOSSProvider(api_url="http://localhost:11434/api/chat", model="test")
    assert "Authorization" not in local._headers

    monkeypatch.delenv("OLLAMA_API_KEY")
    with pytest.raises(ValueError, match="OLLAMA_API_KEY"):
        GPTOSSProvider(api_url="https://ollama.com/api/chat", model="test")


def test_gptoss_uses_backend_budget_then_escalates_empty_reply(monkeypatch):
    monkeypatch.setenv("GPTOSS_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("GPTOSS_MAX_OUTPUT_TOKENS", "0")
    monkeypatch.setenv("GPTOSS_EMPTY_RETRY_OUTPUT_TOKENS", "16384")
    monkeypatch.setattr("providers.gptoss._time.sleep", lambda _seconds: None)
    payloads = []

    def post(*args, **kwargs):
        payloads.append(kwargs["json"])
        content = "" if len(payloads) == 1 else "Maayong buntag"
        return SimpleNamespace(
            status_code=200, headers={}, raise_for_status=lambda: None,
            json=lambda: {"message": {"content": content}},
        )

    provider = GPTOSSProvider(api_url="http://test/api/chat", model="test")
    monkeypatch.setattr(provider._session, "post", post)

    result = provider.translate("Good morning", "English", "Cebuano")

    assert result.success
    assert "num_predict" not in payloads[0]["options"]
    assert payloads[1]["options"]["num_predict"] == 8192


def test_rate_limited_batch_does_not_retry_every_block_individually():
    provider = Provider("gptoss", TranslationResponse(
        translated_text="", provider="gptoss", model="gptoss-model",
        success=False, error_message="GPT-OSS rate limit reached after paced retries",
    ))
    pipeline = TranslationPipeline(provider)

    try:
        pipeline.batch_translate_blocks(
            [
                {"type": "paragraph", "text": "The first sentence needs translation."},
                {"type": "paragraph", "text": "The second sentence needs translation."},
            ],
            "English", "Cebuano", translation_cache=None,
        )
    except RuntimeError as error:
        assert "Translation failed for 2 block" in str(error)
    else:
        raise AssertionError("Rate-limited document was incorrectly reported as successful")

    assert provider.calls == 1


# ===========================================================================
# Prepass preamble reaches batched (multi-block) provider calls
# ===========================================================================

def test_batch_primary_forwards_preamble_to_context_hint(translation_pipeline):
    """Multi-block batches must forward the preamble inside context_hint."""
    provider = translation_pipeline.provider
    captured = {}

    def fake_translate(text="", source_lang="", target_lang="", block_type="",
                       context_hint="", document_type="", response_format="text"):
        captured["context_hint"] = context_hint
        captured["response_format"] = response_format
        return TranslationResponse(
            translated_text='{"0": "Kumusta buntag", "1": "Maayong adlaw"}',
            provider="mock", model="mock", token_usage={}, success=True,
        )

    with mock.patch.object(provider, "translate", side_effect=fake_translate):
        translation_pipeline._translate_batch_worker(
            [(0, "Good morning", "paragraph"), (1, "Good day", "paragraph")],
            "English", "Cebuano",
            document_memory=None, translation_cache=None,
            quality_reviewer=None, document_profile=None,
            context_preamble="[PREPASS] terms",
            ctx=None,
        )

    assert captured["response_format"] == "json"
    assert "[PREPASS]" in captured["context_hint"]


def test_batch_semantic_fallback_forwards_preamble_to_context_hint():
    """The semantic-fallback batch must receive preamble + guidance combined."""
    secondary_kwargs = {}

    class FakeProvider:
        name = "fake"
        batch_provider_name = "fake"
        model_name = "fake-model"

        @staticmethod
        def translate(text="", source_lang="", target_lang="", block_type="",
                      context_hint="", document_type="", response_format="text"):
            return TranslationResponse(
                translated_text='{"0": "Good morning to everyone in the office", '
                                '"1": "I hope you are having a good day"}',
                provider="fake", model="fake", token_usage={}, success=True,
            )

        @staticmethod
        def translate_secondary(text="", source_lang="", target_lang="",
                                block_type="", context_hint="",
                                document_type="", response_format="text"):
            secondary_kwargs["context_hint"] = context_hint
            secondary_kwargs["response_format"] = response_format
            return TranslationResponse(
                translated_text='{"0": "Maayong buntag sa tanan sa opisina", '
                                '"1": "Naglaum ko nga maayo ang imong adlaw"}',
                provider="fake", model="fake", token_usage={}, success=True,
            )

    pipeline = TranslationPipeline(FakeProvider())
    result = pipeline._translate_batch_worker(
        [(0, "Good morning to everyone in the office", "paragraph"),
         (1, "I hope you are having a good day", "paragraph")],
        "English", "Cebuano",
        document_memory=None, translation_cache=None,
        quality_reviewer=None, document_profile=None,
        context_preamble="[PREPASS] terms",
        ctx=None,
    )

    assert secondary_kwargs["response_format"] == "json"
    assert "[PREPASS] terms" in secondary_kwargs["context_hint"]
    assert "Primary batch" in secondary_kwargs["context_hint"]
    assert result == {0: "Maayong buntag sa tanan sa opisina",
                      1: "Naglaum ko nga maayo ang imong adlaw"}
