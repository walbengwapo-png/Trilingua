"""Local regressions for the test3 content and PDF reconstruction failures."""
import copy
import io
import json
from types import SimpleNamespace

import fitz
import pytest

from document.extractor import read_pdf
from document.reconstructor import write_pdf_preserved
from dto.responses import TranslationResponse
from pipeline.translation_pipeline import TranslationPipeline


def test_pdf_unicode_punctuation_survives_without_system_fonts(tmp_path, monkeypatch):
    import document.reconstructor as reconstructor

    original_exists = reconstructor.os.path.exists
    monkeypatch.setattr(
        reconstructor.os.path, "exists",
        lambda path: False if str(path).startswith("C:\\Windows\\Fonts\\") else original_exists(path),
    )
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 80), "Source sentence with enough space for Unicode punctuation.", fontsize=12)
        doc.save(source)
    blocks = read_pdf(str(source), "single")
    target = "“Magandang umaga”—dalhin ang dokumento… ₱250."
    blocks[0]["_original_text"] = blocks[0]["text"]
    blocks[0]["text"] = target
    write_pdf_preserved(blocks, str(source), str(output))
    with fitz.open(output) as doc:
        text = " ".join(page.get_text() for page in doc).replace("\u00a0", " ")
        for character in ("“", "”", "—", "…", "₱"):
            assert character in text
        assert "Magandang umaga" in text
        assert "Source sentence" not in text


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_rotated_page_keeps_translation_upright(tmp_path, rotation):
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=400)
        origins = {90: (80, 260), 180: (260, 220), 270: (220, 80)}
        page.insert_text(origins[rotation], "Source sentence", fontsize=12, rotate=rotation)
        page.set_rotation(rotation)
        doc.save(source)
    blocks = read_pdf(str(source), "single")
    for block in blocks:
        block["_original_text"] = block["text"]
        block["text"] = "Translated sentence"
    write_pdf_preserved(blocks, str(source), str(output))
    with fitz.open(output) as doc:
        text = " ".join(doc[0].get_text().split())
        assert "Translated sentence" in text
        assert "Source sentence" not in text
        for block in doc[0].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                direction = fitz.Point(*line["dir"]) * doc[0].rotation_matrix
                origin = fitz.Point(0, 0) * doc[0].rotation_matrix
                assert direction.x - origin.x == pytest.approx(1)
                assert direction.y - origin.y == pytest.approx(0)


def test_overflow_preserves_all_words_on_readable_continuation(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((30, 150), "Short heading", fontsize=14)
        page.insert_text((30, 174), "Neighbor stays", fontsize=12)
        doc.save(source)
    blocks = read_pdf(str(source), "single")
    target = " ".join(f"word{i}" for i in range(150)) + " www.osha.gov/workers 250"
    blocks[0]["_original_text"] = blocks[0]["text"]
    blocks[0]["text"] = target
    blocks[1]["passthrough"] = True
    write_pdf_preserved(copy.deepcopy(blocks), str(source), str(output))
    with fitz.open(output) as doc:
        text = " ".join(page.get_text() for page in doc)
        assert all(word in text for word in target.split())
        assert "Neighbor stays" in text
        assert len(doc) > 1
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        assert span["size"] >= 8
                        assert page.rect.contains(fitz.Rect(span["bbox"]))


class ConversationalProvider:
    name, model_name = "mock", "local"

    def estimate_tokens(self, text):
        return len(text.split())

    def translate(self, **kwargs):
        return TranslationResponse(
            "Could you please provide the paragraph you would like translated?"
        )


def test_short_block_rejects_conversational_response():
    response = TranslationPipeline(ConversationalProvider())._translate_with_echo_guard(
        text="Hello", source_lang="English", target_lang="Cebuano",
        block_type="heading", context_hint="", document_type="",
    )
    assert not response.success
    assert not response.translated_text


def test_saved_output_gate_rejects_missing_or_unplaced_content(tmp_path):
    from validators.translation_validator import validate_pdf_output
    output = tmp_path / "missing.pdf"
    with fitz.open() as doc:
        doc.new_page(width=200, height=200)
        doc.save(output)
    placement = {"block_index": 0, "source_page": 0, "page": 0,
                 "rect": [20, 20, 160, 40], "text": "Missing text",
                 "font_size": 12, "action": "fit"}
    report = validate_pdf_output(output, [placement], 1, [{"text": "Missing text and ending"}])
    assert report["content_coverage"] == "failed"
    assert any("missing rendered text" in issue for issue in report["issues"])
    assert any("incomplete block placement" in issue for issue in report["issues"])


def test_redaction_padding_preserves_passthrough_neighbor(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((30, 70), "250", fontsize=12, fontname="hebo")
        page.insert_text((51, 70), "Source", fontsize=12)
        doc.save(source)
    with fitz.open(source) as doc:
        spans = [span for block in doc[0].get_text("dict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"]]
    blocks = [{"page": 0, "pdf_coordinates": "display", "type": "paragraph",
               "position": list(span["bbox"]), "text": span["text"],
               "style": {"font": "helv", "font_size": 12},
               "lines": [{"bbox": list(span["bbox"]), "text": span["text"], "size": 12}],
               "passthrough": span["text"] == "250"} for span in spans]
    for block in blocks:
        if not block["passthrough"]:
            block["text"] = "Hubad"
    report = write_pdf_preserved(blocks, str(source), str(output))
    assert report["status"] == "passed"
    with fitz.open(output) as doc:
        assert "250" in "".join(page.get_text() for page in doc)


def test_reflow_avoids_vector_illustration(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    figure = fitz.Rect(30, 85, 130, 125)
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((30, 65), "Source sentence", fontsize=12)
        page.draw_oval(figure, fill=(0, .5, 1))
        doc.save(source)
    blocks = read_pdf(str(source), "single")
    blocks[0]["text"] = " ".join(f"word{i}" for i in range(60))
    report = write_pdf_preserved(blocks, str(source), str(output))
    assert report["continuation_pages"] > 0
    assert not any(fitz.Rect(fragment["rect"]).intersects(figure)
                   for fragment in report["blocks"] if fragment["page"] == 0)


def test_continuation_darkens_white_panel_text(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.draw_rect(fitz.Rect(20, 40, 180, 75), fill=(0, .2, .5))
        page.insert_text((30, 65), "Heading with room", color=(1, 1, 1), fontsize=14)
        doc.save(source)
    blocks = read_pdf(str(source), "single")
    blocks[0]["text"] = " ".join(f"word{i}" for i in range(60))
    report = write_pdf_preserved(blocks, str(source), str(output))
    assert report["continuation_pages"] > 0
    assert any(fragment["action"] == "reference" for fragment in report["blocks"])
    with fitz.open(output) as doc:
        for fragment in report["blocks"]:
            if fragment["action"] not in {"continuation", "reference"}:
                continue
            spans = [span for block in doc[fragment["page"]].get_text("dict", clip=fitz.Rect(fragment["rect"]) + (-1,-1,1,1))["blocks"]
                     for line in block.get("lines", []) for span in line["spans"]]
            expected_color = 0xffffff if fragment["action"] == "reference" else 0
            assert spans and all(span["color"] == expected_color for span in spans)


def test_invalid_quality_repair_keeps_valid_initial_translation():
    class RepairProvider(ConversationalProvider):
        calls = 0

        def translate(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return TranslationResponse("Adunay 250 ka tawo.")
            return super().translate(**kwargs)

    reviewer = SimpleNamespace(
        review=lambda **kwargs: SimpleNamespace(summary="Repair requested", score=50, issues=[]),
        needs_retranslation=lambda review: True,
    )
    result = TranslationPipeline(RepairProvider())._translate_single_worker(
        text="There are 250 people.", source_lang="English", target_lang="Cebuano",
        block_type="paragraph", block_index=0, quality_reviewer=reviewer,
        document_memory=None, translation_cache=None, document_profile=None,
    )
    assert result == "Adunay 250 ka tawo."


def test_coherence_repair_cannot_remove_protected_content():
    from pipeline.coherence_polish import CoherencePolishPass

    class PolishProvider(ConversationalProvider):
        def translate(self, **kwargs):
            return TranslationResponse(json.dumps({"0": "Adunay mga tawo."}))

    source = [{"text": "There are 250 people in the room today."}]
    initial = [{"text": "250 ka tawo."}]
    assert CoherencePolishPass(PolishProvider()).polish_blocks(
        source, initial, "English", "Cebuano") == initial


def test_protected_literals_and_block_count():
    from validators.hallucination_detector import translation_content_issue, validate_translated_blocks
    source = "Visit FTA.gov/subscribe for 250 people; 250 people."
    assert not translation_content_issue(source, "FTA.gov/subscribe para sa 250 ug 250 ka tawo.")
    assert translation_content_issue(source, "FTA.gov/subscribe para sa 250 ka tawo.")
    assert translation_content_issue(source, "FTA.gov para sa 250 ug 250 ka tawo.")
    assert not translation_content_issue("100, 200 and 2.5 million", "100 ug 200 ug 2.5 milyon")
    assert not translation_content_issue("sample.organic and version 250abc", "sample.organic ug bersyon 250abc")
    with pytest.raises(ValueError, match="block count"):
        validate_translated_blocks([{"text": source}], [])


def test_invalid_batch_cannot_be_promoted_to_passthrough(monkeypatch):
    import pipeline.translation_pipeline as module
    monkeypatch.setattr(module, "_TRANSLATION_BATCH_ENABLED", True)

    class BatchProvider(ConversationalProvider):
        def translate(self, **kwargs):
            if kwargs.get("block_type") == "batch":
                return TranslationResponse(json.dumps({"0": "Please provide the text to translate."}))
            return super().translate(**kwargs)

    with pytest.raises(RuntimeError, match="Conversational response"):
        TranslationPipeline(BatchProvider()).batch_translate_blocks(
            [{"type": "heading", "text": "Report summary"}], "English", "Cebuano")


def test_glossary_cannot_remove_protected_numeric_content():
    class ValidProvider(ConversationalProvider):
        def translate(self, **kwargs):
            text = "Adunay 250 ka tawo."
            return TranslationResponse(json.dumps({"0": text}) if kwargs.get("block_type") == "batch" else text)

    glossary = SimpleNamespace(apply=lambda text: text.replace("250", ""))
    with pytest.raises(RuntimeError, match="Missing protected content"):
        TranslationPipeline(ValidProvider()).batch_translate_blocks(
            [{"type": "paragraph", "text": "There are 250 people."}],
            "English", "Cebuano", glossary_store=glossary)


def test_pdf_pipeline_exposes_saved_validation_in_response_and_sidecar(tmp_path, document_pipeline):
    from dto.requests import DocumentTranslationRequest
    source = tmp_path / "source.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((30, 65), "A sentence containing 250 people.", fontsize=12)
        doc.save(source)
    response = document_pipeline.translate(DocumentTranslationRequest(
        str(source), "English", "Cebuano", mode="fast"))
    assert response.output_validation["status"] == "passed"
    assert response.sidecar["output_validation"] == response.output_validation
    assert all(block["rendered_layout"]["status"] == "passed" for block in response.sidecar["blocks"])


@pytest.mark.parametrize("regenerate", [False, True])
def test_document_endpoint_returns_structured_validation_failure(monkeypatch, regenerate):
    import server
    from fastapi import HTTPException, UploadFile
    from validators.translation_validator import PDFValidationError

    report = {"status": "failed", "issues": ["Missing text"]}

    def fail(_operation):
        raise PDFValidationError(report)

    monkeypatch.setattr(server, "_run_pipeline_guarded", fail)
    upload = UploadFile(filename="document.pdf", file=io.BytesIO(b"local mock"))
    with pytest.raises(HTTPException) as caught:
        if regenerate:
            server.translate_document_regenerate(
                upload, json.dumps({"format": ".pdf"}), "", "{}", "English", "Cebuano", "auto")
        else:
            server.translate_document(upload, "English", "Cebuano", "auto", "balanced")
    assert caught.value.status_code == 422
    assert caught.value.detail["validation"] == report
