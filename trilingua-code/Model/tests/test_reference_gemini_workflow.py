import json
import re
from types import SimpleNamespace

from document.document_analyzer import DocumentProfile, SectionInfo
from document.semantic_chunker import SemanticChunk
from dto.requests import TranslationRequest
from dto.responses import TranslationResponse
from pipeline import translation_pipeline as pipeline_module
from pipeline.translation_pipeline import TranslationPipeline, _is_echo_output
from prompts.translation import build_translation_prompt
from providers.fallback import FallbackTranslationProvider
from providers.gemini import GeminiProvider
from providers.gptoss import GPTOSSProvider
from validators.ai_quality_reviewer import QualityIssue, QualityReview


class RecordingProvider:
    name = "gptoss"
    model_name = "primary-model"
    batch_limits = {"max_batch_chars": 4000, "max_batch_items": 12}

    def __init__(self, batch_payload=None):
        self.calls = []
        self.batch_payload = batch_payload

    def estimate_tokens(self, text):
        return len(text.split())

    def translate(self, text, source_lang, target_lang, block_type="paragraph",
                  context_hint="", document_type="", response_format="text"):
        self.calls.append({
            "text": text,
            "block_type": block_type,
            "response_format": response_format,
        })
        if block_type == "batch":
            indices = [int(value) for value in re.findall(r"\[BLOCK_(\d+)\]", text)]
            payload = self.batch_payload
            if payload is None:
                payload = {str(idx): f"Hubad {idx}" for idx in indices}
            return TranslationResponse(
                translated_text=json.dumps(payload), provider=self.name,
                model=self.model_name,
            )
        return TranslationResponse(
            translated_text=f"Hubad: {text}", provider=self.name,
            model=self.model_name,
        )


def _profile():
    return DocumentProfile(
        document_type="report", writing_style="formal", language="English",
        confidence=0.9, sections=[SectionInfo(1, "A", 0)],
    )


def test_reference_prompt_preserves_sensitive_content_and_language_style():
    cebuano = build_translation_prompt(
        "Dr. Santos — 12 September 2026\nhttps://example.test",
        "English", "Cebuano", "heading",
    )
    filipino = build_translation_prompt("Please call me.", "English", "Filipino")

    assert "Preserve names, initials, numbers, dates, URLs" in cebuano
    assert "intentional line breaks exactly" in cebuano
    assert "verb focus and aspect" in cebuano
    assert "aspect, voice, formality" in filipino


def test_gptoss_to_gemini_chain_uses_conservative_limits_and_attribution():
    primary = RecordingProvider()
    primary.translate = lambda *args, **kwargs: TranslationResponse(
        translated_text="", provider="gptoss", model="primary-model",
        success=False, error_message="primary unavailable",
    )
    fallback = RecordingProvider()
    fallback.name = "gemini"
    fallback.model_name = "fallback-model"
    fallback.batch_limits = {"max_batch_chars": 6000, "max_batch_items": 16}
    fallback.max_concurrency = 1

    chain = FallbackTranslationProvider(primary, fallback, cooldown_seconds=300)
    result = chain.translate("Good morning", "English", "Cebuano")

    assert result.provider == "gemini"
    assert chain.provider_names == ("gptoss", "gemini")
    assert chain.batch_limits == {"max_batch_chars": 4000, "max_batch_items": 12}
    # Backup quota is enforced only when it is used; it must not serialize a
    # healthy GPT-OSS primary route.
    assert chain.max_concurrency is None
    assert chain.routing_state()["retry_after_seconds"] > 0


def test_semantic_groups_are_real_batch_boundaries_and_metadata_is_preserved():
    provider = RecordingProvider()
    pipeline = TranslationPipeline(provider)
    chunker = SimpleNamespace(chunk_blocks=lambda blocks, profile: [
        SemanticChunk("one two", [0, 1], "section", 2),
        SemanticChunk("three four", [2, 3], "section", 2),
    ])
    blocks = [
        {"type": "paragraph", "text": f"Source sentence {idx}.",
         "shape_id": idx, "custom_metadata": f"meta-{idx}"}
        for idx in range(4)
    ]

    translated = pipeline.batch_translate_blocks(
        blocks, "English", "Cebuano",
        mode=SimpleNamespace(semantic_chunking=True),
        semantic_chunker=chunker, document_profile=_profile(),
        translation_cache=None,
    )

    assert len(provider.calls) == 2
    assert all(call["response_format"] == "json" for call in provider.calls)
    assert [item["shape_id"] for item in translated] == [0, 1, 2, 3]
    assert [item["custom_metadata"] for item in translated] == [
        "meta-0", "meta-1", "meta-2", "meta-3",
    ]


def test_missing_batch_id_is_retried_individually_and_extra_id_is_ignored():
    provider = RecordingProvider(batch_payload={"0": "Hubad zero", "99": "ignore"})
    pipeline = TranslationPipeline(provider)
    translated = pipeline.batch_translate_blocks(
        [
            {"type": "paragraph", "text": "First source sentence."},
            {"type": "paragraph", "text": "Second source sentence."},
        ],
        "English", "Cebuano", translation_cache=None,
    )

    assert len(provider.calls) == 2
    assert translated[0]["text"] == "Hubad zero"
    assert translated[1]["text"].startswith("Hubad:")
    assert len(translated) == 2


def test_malformed_batch_json_recovers_each_original_block():
    provider = RecordingProvider()
    original_translate = provider.translate

    def malformed(text, source_lang, target_lang, block_type="paragraph",
                  context_hint="", document_type="", response_format="text"):
        if block_type == "batch":
            provider.calls.append({
                "text": text, "block_type": block_type,
                "response_format": response_format,
            })
            return TranslationResponse(
                translated_text="not valid json", provider="gptoss",
                model="primary-model",
            )
        return original_translate(
            text, source_lang, target_lang, block_type,
            context_hint, document_type, response_format,
        )

    provider.translate = malformed
    translated = TranslationPipeline(provider).batch_translate_blocks(
        [
            {"type": "paragraph", "text": "First complete source sentence."},
            {"type": "paragraph", "text": "Second complete source sentence."},
        ],
        "English", "Cebuano", translation_cache=None,
    )

    assert len(translated) == 2
    assert all(item["text"].startswith("Hubad:") for item in translated)


def test_dual_provider_failure_names_both_failures():
    class FailedProvider(RecordingProvider):
        def __init__(self, name):
            super().__init__()
            self.name = name
            self.model_name = f"{name}-model"

        def translate(self, *args, **kwargs):
            return TranslationResponse(
                translated_text="", provider=self.name, model=self.model_name,
                success=False, error_message=f"{self.name} unavailable",
            )

    chain = FallbackTranslationProvider(
        FailedProvider("gptoss"), FailedProvider("gemini"), cooldown_seconds=300
    )
    result = chain.translate("Translate this sentence", "English", "Cebuano")

    assert not result.success
    assert "gptoss failed" in result.error_message
    assert "gemini failed" in result.error_message


def test_title_case_heading_gets_echo_retry_but_honorific_name_does_not():
    assert _is_echo_output(
        "Community Health Program", "Community Health Program", "heading"
    )
    assert not _is_echo_output("Dr. Santos", "Dr. Santos", "heading")

    provider = RecordingProvider()
    responses = iter(("Community Health Program", "Programa sa Panglawas sa Komunidad"))
    provider.translate = lambda *args, **kwargs: TranslationResponse(
        translated_text=next(responses), provider="gptoss", model="primary-model"
    )
    result = TranslationPipeline(provider).translate(TranslationRequest(
        text="Community Health Program", source_lang="English",
        target_lang="Cebuano", block_type="heading",
    ))

    assert result.success
    assert result.translated_text == "Programa sa Panglawas sa Komunidad"


def test_oversized_block_splits_and_restores_blank_line(monkeypatch):
    monkeypatch.setattr(pipeline_module, "_TRANSLATION_MAX_TOKENS", 5)
    provider = RecordingProvider()
    pipeline = TranslationPipeline(provider)
    source = (
        "This first sentence has enough words to split safely.\n\n"
        "This second paragraph also has enough words to split safely."
    )
    translated = pipeline.batch_translate_blocks(
        [{"type": "paragraph", "text": source}],
        "English", "Cebuano", translation_cache=None,
    )

    assert len(provider.calls) >= 2
    assert "\n\n" in translated[0]["text"]


def test_provider_payloads_request_structured_json(monkeypatch):
    class Response:
        status_code = 200
        headers = {}

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"message": {"content": '{"0":"Hubad"}'}}

    gptoss = GPTOSSProvider(api_url="http://test/api/chat", model="test")
    gptoss_payload = {}

    def gptoss_post(*args, **kwargs):
        gptoss_payload.update(kwargs["json"])
        return Response()

    monkeypatch.setattr(gptoss._session, "post", gptoss_post)
    gptoss.translate("[BLOCK_0] Hello", "English", "Cebuano",
                     response_format="json")
    assert gptoss_payload["format"] == "json"

    gemini = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
    gemini_payload = {}

    class GeminiResponse(Response):
        @staticmethod
        def json():
            return {"candidates": [{"content": {"parts": [{"text": '{"0":"Hubad"}'}]}}]}

    def gemini_post(*args, **kwargs):
        gemini_payload.update(kwargs["json"])
        return GeminiResponse()

    monkeypatch.setattr(gemini._session, "post", gemini_post)
    gemini.translate("[BLOCK_0] Hello", "English", "Cebuano",
                     response_format="json")
    assert gemini_payload["generationConfig"]["responseMimeType"] == "application/json"
    assert gemini_payload["generationConfig"]["responseSchema"]["required"] == ["0"]


def test_text_fast_mode_skips_review_and_returns_extended_contract(monkeypatch):
    import server

    class Pipeline:
        @staticmethod
        def translate(request):
            return TranslationResponse(
                translated_text="Maayong buntag", provider="gptoss",
                model="primary-model",
            )

    class Reviewer:
        @staticmethod
        def review(**kwargs):
            raise AssertionError("fast mode must not run quality review")

    monkeypatch.setattr(server, "_translation_pipeline", Pipeline())
    monkeypatch.setattr(server, "_text_quality_reviewer", Reviewer())
    result = server.translate_text(server.TextRequest(
        text="Good morning", source_lang="English",
        target_lang="Cebuano", mode="fast",
    ))

    assert result["mode"] == "fast"
    assert result["quality_score"] is None
    assert result["quality_issues"] == []
    assert result["provider"] == "gptoss"


def test_text_auto_resolves_to_balanced_and_caches_targeted_repair(monkeypatch):
    import server

    issue = QualityIssue("critical", "untranslated", "Heading was unchanged")
    reviews = iter((
        QualityReview(30.0, [issue], True, "Translate the heading"),
        QualityReview(94.0, [], False, "Good translation"),
    ))

    class Pipeline:
        def __init__(self):
            self.stored = None

        @staticmethod
        def translate(request):
            return TranslationResponse(
                translated_text="Community Health Program", provider="gptoss",
                model="primary-model",
            )

        @staticmethod
        def _translate_with_echo_guard(**kwargs):
            return TranslationResponse(
                translated_text="Programa sa Panglawas sa Komunidad",
                provider="gemini", model="fallback-model",
            )

        def store_translation(self, *args):
            self.stored = args

    class Reviewer:
        @staticmethod
        def review(**kwargs):
            return next(reviews)

        @staticmethod
        def needs_retranslation(review):
            return review.retry_required

    pipeline = Pipeline()
    monkeypatch.setattr(server, "_translation_pipeline", pipeline)
    monkeypatch.setattr(server, "_text_quality_reviewer", Reviewer())
    result = server.translate_text(server.TextRequest(
        text="Community Health Program", source_lang="English",
        target_lang="Cebuano", mode="auto",
    ))

    assert result["translated"] == "Programa sa Panglawas sa Komunidad"
    assert result["provider"] == "gemini"
    assert result["mode"] == "balanced"
    assert result["quality_score"] == 94.0
    assert pipeline.stored is not None
