"""Local regressions for the test3 content and PDF reconstruction failures."""
import copy
import io
import json
from types import SimpleNamespace

import pymupdf as fitz
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


def test_strict_title_uses_free_space_without_splitting_words(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=220)
        page.insert_text((30, 130), "Source", fontsize=29)
        page.insert_text((30, 162), "Neighbor stays", fontsize=12)
        doc.save(source)
    blocks = read_pdf(str(source), "single")
    blocks[0].update(text="Translated title", _original_text=blocks[0]["text"])
    blocks[1]["passthrough"] = True

    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)

    assert report["held"] == []
    assert report["status"] == "passed" and report["output_pages"] == 1
    with fitz.open(output) as doc:
        text = " ".join(doc[0].get_text().split())
        assert "Translated title" in text and "Neighbor stays" in text
        assert "Source" not in text


def test_strict_banner_uses_panel_width_without_crossing_border(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    panel = fitz.Rect(30, 55, 270, 100)
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=180)
        page.draw_rect(panel, fill=(0, .3, .7))
        page.insert_text((34, 70), "First source", fontsize=12, color=(1, 1, 1))
        page.insert_text((34, 94), "Second source", fontsize=12, color=(1, 1, 1))
        doc.save(source)
    blocks = read_pdf(str(source), "single")
    assert len(blocks) == 2
    blocks[0].update(text="A complete translated banner sentence", _original_text=blocks[0]["text"])
    blocks[1]["passthrough"] = True

    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)

    assert report["held"] == []
    assert report["status"] == "passed" and report["output_pages"] == 1
    for fragment in report["blocks"]:
        assert panel.contains(fitz.Rect(fragment["rect"]))


def test_strict_preflight_reserves_shared_whitespace_between_blocks(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=180)
        page.draw_line((70, 20), (70, 170))
        for y, text in [(70, "One"), (110, "Two"), (138, "End")]:
            page.insert_text((30, y), text, fontsize=12)
        doc.save(source)
    blocks = read_pdf(str(source), "single")
    assert len(blocks) == 3
    for block, text in zip(blocks, ["alpha beta gamma", "delta theta sigma"]):
        block.update(text=text, _original_text=block["text"])
    blocks[2]["passthrough"] = True

    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)

    assert report["status"] == "passed"
    assert [entry["block_index"] for entry in report["held"]] == [1]


def test_strict_native_underline_is_not_a_table_boundary(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=180)
        page.draw_line((25, 56), (275, 56))
        page.insert_text((30, 70), "Source heading", fontsize=12)
        width = fitz.get_text_length("Source heading", fontsize=12)
        page.draw_rect(fitz.Rect(30, 70, 30 + width, 71), fill=(0, 0, 0), color=None)
        doc.save(source)
    blocks = read_pdf(str(source), "single")
    blocks[0].update(text="Translated heading", _original_text=blocks[0]["text"])

    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)

    assert report["held"] == [] and report["status"] == "passed"
    with fitz.open(output) as doc:
        assert doc[0].get_drawings(), "Keep the original underline artwork"


def test_strict_blue_background_seam_does_not_hold_native_prose(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    panel = fitz.Rect(30, 50, 270, 84)
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=180)
        for y in [50, 67]:
            page.draw_rect(fitz.Rect(30, y, 270, y + 17), fill=(0, .3, .7), color=None)
        page.insert_text((34, 63), "First source", fontsize=12, color=(1, 1, 1))
        page.insert_text((34, 80), "Second source", fontsize=12, color=(1, 1, 1))
        doc.save(source)
    blocks = read_pdf(str(source), "single")
    for block in blocks:
        block.update(text="Complete translated sentence", _original_text=block["text"])

    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)

    assert report["held"] == [] and report["status"] == "passed"
    assert all(panel.contains(fitz.Rect(fragment["rect"])) for fragment in report["blocks"])


def test_thin_filled_vertical_divider_bounds_expanded_text(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=220)
        page.draw_rect(fitz.Rect(200, 40, 201, 180), fill=(0, 0, 0), color=None)
        for x, y, text in [(30, 80, "Source"), (30, 104, "Below stays"), (230, 80, "Right stays")]:
            page.insert_text((x, y), text, fontsize=12)
        doc.save(source)
    blocks = read_pdf(str(source), "single")
    for block in blocks:
        if block["text"] == "Source":
            block.update(text="ABCDEFGHIJKLMNOPQRSTUVW is a reference code.", _original_text="Source")
        else:
            block["passthrough"] = True

    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)

    assert report["status"] == "passed" and not report["held"]
    assert all(fitz.Rect(fragment["rect"]).x1 <= 200 for fragment in report["blocks"]
               if fragment["action"] == "fit")


@pytest.mark.parametrize("target", [
    "Ibutang kini ilawom sa mainit nga tubig o i.",
    "Ibutang kini ilawom sa mainit nga tubig o i-",
    "Ibutang kini ilawom sa mainit nga tubig o i... ang ibabaw, dayon pahiri kini.",
    "Ibutang kini ilawom sa mainit nga tubig o i… ang ibabaw, dayon pahiri kini.",
])
def test_content_guard_rejects_dangling_verb_prefix(target):
    from validators.hallucination_detector import translation_content_issue
    assert translation_content_issue("Rinse or steam it, then wipe with a soft cloth.", target)


@pytest.mark.parametrize("source,target", [
    ("Choose option I.", "Pilia ang kapilian I."),
    ("Steam it, then wipe it.", "I-singaw kini, dayon pahiri."),
    ("Letters a, e, or i.", "Mga letra a, e, o i."),
    ("Letters a, e, or i...", "Mga letra a, e, o i..."),
])
def test_content_guard_preserves_complete_text_and_literal_letters(source, target):
    from validators.hallucination_detector import translation_content_issue
    assert not translation_content_issue(source, target)


def test_incomplete_instruction_is_retried_before_acceptance():
    from unittest.mock import Mock
    complete = "Hugasi o i-singaw kini, dayon pahiri gamit ang humok nga panapton."
    provider = SimpleNamespace(name="mock", model_name="local", translate=Mock(side_effect=[
        TranslationResponse("Hugasi kini o i."), TranslationResponse(complete),
    ]))
    response = TranslationPipeline(provider)._translate_with_echo_guard(
        text="Rinse or steam it, then wipe with a soft cloth.",
        source_lang="English", target_lang="Cebuano", block_type="paragraph",
        context_hint="", document_type="",
    )
    assert response.success and response.translated_text == complete
    assert provider.translate.call_count == 2
    assert "finish every instruction" in provider.translate.call_args.kwargs["context_hint"]


def test_repeated_incomplete_instruction_is_not_returned_as_success():
    from unittest.mock import Mock
    provider = SimpleNamespace(name="mock", model_name="local", translate=Mock(
        side_effect=lambda **kwargs: TranslationResponse("Hugasi kini o i.")))
    response = TranslationPipeline(provider)._translate_with_echo_guard(
        text="Rinse or steam it, then wipe with a soft cloth.",
        source_lang="English", target_lang="Cebuano", block_type="paragraph",
        context_hint="", document_type="",
    )
    assert not response.success and not response.translated_text
    assert provider.translate.call_count == 2


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


def test_redaction_padding_preserves_an_unowned_neighboring_span(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((30, 70), "Source line", fontsize=12)
        page.insert_text((30, 84), "Neighbor stays", fontsize=12)
        doc.save(source)

    with fitz.open(source) as doc:
        spans = [span for block in doc[0].get_text("dict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"]]
    assert len(spans) == 2
    first = spans[0]
    block = {
        "page": 0, "pdf_coordinates": "display", "type": "paragraph",
        "position": list(first["bbox"]), "text": "Hubad",
        "style": {"font": "helv", "font_size": 12},
        "lines": [{"bbox": list(first["bbox"]), "text": first["text"], "size": 12}],
    }

    report = write_pdf_preserved([block], str(source), str(output))

    assert report["status"] == "passed"
    with fitz.open(output) as doc:
        text = " ".join(" ".join(page.get_text().split()) for page in doc)
    assert "Hubad" in text
    assert "Neighbor stays" in text
    assert "Source line" not in text


def test_redaction_removes_an_overlapping_hidden_duplicate(tmp_path):
    source, output = tmp_path / "duplicate.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.insert_text((30, 70), "Source line", fontsize=12)
        page.insert_text((30, 70), "Source line", fontsize=12, render_mode=3)
        doc.save(source)

    blocks = read_pdf(str(source), "single")
    block = blocks[0]
    block.update(text="Hubad", _original_text=block["text"])
    report = write_pdf_preserved([block], str(source), str(output))

    assert report["status"] == "passed"
    with fitz.open(output) as doc:
        text = doc[0].get_text()
    assert "Hubad" in text
    assert "Source line" not in text


def test_pdf_extractor_merges_text_missing_from_dict_mode(tmp_path, monkeypatch):
    source = tmp_path / "blocks-only.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((30, 70), "Styled source")
        page.insert_text((30, 170), "Blocks only")
        doc.save(source)

    get_text = fitz.Page.get_text

    def omit_second_dict_block(page, option="text", *args, **kwargs):
        result = get_text(page, option, *args, **kwargs)
        if option == "dict":
            result["blocks"] = result["blocks"][:1]
        return result

    monkeypatch.setattr(fitz.Page, "get_text", omit_second_dict_block)
    blocks = read_pdf(str(source), "single")
    assert [block["text"] for block in blocks] == ["Styled source", "Blocks only"]


def test_legacy_contact_icon_stays_in_source_while_its_label_is_translated(tmp_path, monkeypatch):
    from document.pdf_regions import inventory_pdf
    source, output = tmp_path / "contact.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((30, 70), "(", fontname="tiro", fontsize=12)
        page.insert_text((40, 70), "Source contact", fontsize=12)
        doc.save(source)
    get_text = fitz.Page.get_text

    def legacy_icon(page, option="text", *args, **kwargs):
        result = get_text(page, option, *args, **kwargs)
        if option == "dict" and page.parent.name == str(source):
            for block in result["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        if span["text"] == "(":
                            span.update(text="\uf028", font="Wingdings-Regular")
        return result

    monkeypatch.setattr(fitz.Page, "get_text", legacy_icon)
    blocks, inventory = inventory_pdf(source, read_pdf(str(source)), "English")
    assert blocks and all("\uf028" not in block["text"] for block in blocks)
    assert any(region["status"] == "held" for region in inventory["regions"])
    for block in blocks:
        block.update(_original_text=block["text"], text="Translated contact")
    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)
    assert report["status"] == "passed"
    with fitz.open(output) as doc:
        text = " ".join(doc[0].get_text().split())
    assert "(" in text and "Translated contact" in text
    assert "Source contact" not in text


def test_adjacent_contact_rows_keep_their_own_icons_and_translated_labels(tmp_path, monkeypatch):
    from document.pdf_regions import inventory_pdf
    source, output = tmp_path / "contact-rows.pdf", tmp_path / "output.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=180)
        for y, icon, label in [(70, "(", "Source phone"), (86, ")", "Source email")]:
            page.insert_text((30, y), icon, fontname="tiro", fontsize=12)
            page.insert_text((40, y), label, fontsize=12)
        doc.save(source)
    get_text = fitz.Page.get_text

    def legacy_icons(page, option="text", *args, **kwargs):
        result = get_text(page, option, *args, **kwargs)
        if option == "dict" and page.parent.name == str(source):
            for block in result["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        if span["text"] in {"(", ")"}:
                            span.update(text="\uf028" if span["text"] == "(" else "\uf02a",
                                        font="Wingdings-Regular")
        return result

    monkeypatch.setattr(fitz.Page, "get_text", legacy_icons)
    blocks, _ = inventory_pdf(source, read_pdf(str(source)), "English")
    assert [block["text"] for block in blocks] == ["Source phone", "Source email"]
    for block in blocks:
        block.update(_original_text=block["text"], text=block["text"].replace("Source", "Translated"))
    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)
    assert report["status"] == "passed" and not report["held"]
    with fitz.open(output) as doc:
        text = " ".join(doc[0].get_text().split())
        assert "Translated phone" in text and "Translated email" in text
        assert "(" in text and ")" in text


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
            server.translate_document(upload, "English", "Cebuano", "auto", "balanced", 'strict')
    assert caught.value.status_code == 422
    assert caught.value.detail["validation"] == report
