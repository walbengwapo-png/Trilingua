"""OCR completeness, evidence gates, geometry and reconstruction regressions."""
import io
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import fitz
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document import ocr_extractor as ocr
from document.extractor import read_pdf
from document.regenerator import rich_block_entry, reconstruct_from_sidecar
from document.reconstructor import reconstruct_document, choose_output_path
from dto.requests import DocumentTranslationRequest


def block(text="Recognized source words.", page=0):
    return {"type": "paragraph", "text": text, "page": page, "position": [40, 40, 300, 70],
            "ocr_reflow": True, "ocr": {"pack": "eng", "confidence": 55.5,
                                        "uncertain_words": [{"text": "source", "confidence": 20}]}}


def mixed_pdf(path):
    image = io.BytesIO()
    Image.new("RGB", (1200, 1600), "white").save(image, "PNG")
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((60, 100), "This selectable paragraph must appear exactly once.")
        page = doc.new_page()
        page.insert_image(page.rect, stream=image.getvalue())
        doc.new_page()
        doc.save(path)


def test_decimal_confidence_and_uncertain_words_are_retained(monkeypatch):
    import pytesseract
    from .test_ocr_functional import hocr
    data=hocr([('Clear',98.25,[100,200,250,230]),('uncertain',22.5,[300,200,450,230]),
               ('unknown','nan',[500,200,650,230])],box='100 200 650 230')
    monkeypatch.setattr(pytesseract, "image_to_pdf_or_hocr", Mock(return_value=data))
    blocks = ocr.recognize_image(Image.new("RGB", (1000, 1000)), "eng", page=2, page_size=(500, 500))
    assert blocks[0]["text"] == "Clear uncertain unknown"
    assert blocks[0]["position"] == [50, 100, 325, 115]
    assert blocks[0]["page"] == 2
    assert [w["text"] for w in blocks[0]["ocr"]["uncertain_words"]] == ["uncertain", "unknown"]
    assert "quality_score" not in blocks[0]


def test_empty_recognition_is_an_explicit_failure(monkeypatch):
    import pytesseract
    monkeypatch.setattr(pytesseract, "image_to_pdf_or_hocr", lambda *a, **k: b"<html></html>")
    with pytest.raises(ocr.OCRUnavailable, match="not silently omitted"):
        ocr.recognize_image(Image.new("RGB", (300, 300)), "eng")


def test_mixed_pdf_retains_native_and_records_scan_gate_hold(tmp_path, monkeypatch):
    path = tmp_path / "mixed.pdf"
    mixed_pdf(path)
    native = read_pdf(str(path))
    recognize = Mock(side_effect=AssertionError("No OCR while acceptance is held"))
    monkeypatch.setattr(ocr, "recognize_image", recognize)
    blocks, report = ocr.complete_pdf(path, native, "English")
    assert [b["text"] for b in blocks] == [b["text"] for b in native]
    assert [p["classification"] for p in report["pages"]] == ["native", "raster", "blank"]
    assert report["regions"][-1]["reason"] == "ocr_acceptance_hold"
    assert not recognize.called


def test_native_text_filtered_by_column_is_not_replaced_with_ocr(tmp_path, monkeypatch):
    path = tmp_path / "native.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 100), "Existing text excluded by selected column.")
        doc.save(path)
    require = Mock(side_effect=AssertionError("Must not OCR filtered native text"))
    monkeypatch.setattr(ocr, "require_ready", require)
    blocks, report = ocr.complete_pdf(path, [], "English", "right")
    assert not blocks and report["regions"][0]["reason"] == "filtered_or_unextracted_native"


def accepted_report(tmp_path, monkeypatch):
    state = {"ready": True, "version": "test-engine", "installed_packs": ["eng"],
             "pack_sha256": {"eng": "test-hash"}}
    monkeypatch.setattr(ocr, "readiness", lambda: state)
    # Contract fixture under a mocked engine, never installed as application evidence.
    report = {"schema_version": 2, "minimum_word_accuracy_percent": 95, "sample_count_valid": True,
              "settings": ocr.SETTINGS, "engine": state,
              "categories": {"English / scan": {"cases": ["scan"], "decision": "go", "word_accuracy_percent": 99}},
              "cases": [{"id": "scan", "status": "measured", "acceptance_eligible": True,
                         'split':'heldout', 'language':'English', 'pack':'eng', 'input_category':'scan',
                         'contract_errors':[]}]}
    path = tmp_path / "acceptance.json"
    monkeypatch.setenv("OCR_ACCEPTANCE_REPORT", str(path))
    return report, path


@pytest.mark.parametrize("change", ["none", "synthetic", "engine", "threshold", "pack", "settings", 'calibration', 'legacy'])
def test_only_matching_accepted_evidence_enables_scan_category(tmp_path, monkeypatch, change):
    report, path = accepted_report(tmp_path, monkeypatch)
    if change == "synthetic": report["cases"][0]["acceptance_eligible"] = False
    if change == "engine": report["engine"] = {**report["engine"], "version": "old-engine"}
    if change == "threshold": report["minimum_word_accuracy_percent"] = 90
    if change == "pack": report["engine"] = {**report["engine"], "pack_sha256": {"eng": "different"}}
    if change == "settings": report["settings"] = {}
    if change == 'calibration': report['cases'][0]['split'] = 'calibration'
    if change == 'legacy': report['schema_version'] = 1
    path.write_text(json.dumps(report))
    # Even the former positive unsigned fixture must now fail closed.
    with pytest.raises(ocr.OCRUnavailable, match="on hold"):
        ocr.require_ready("English", "scan")
    with pytest.raises(ocr.OCRUnavailable, match="on hold"):
        ocr.require_ready("English", "photo")


@pytest.mark.parametrize("extension", ["png", "jpg", "jpeg"])
@pytest.mark.parametrize("unit_mode", [False, True])
def test_image_upload_output_and_sidecar_regeneration(tmp_path, monkeypatch, document_pipeline, extension, unit_mode):
    monkeypatch.setattr('pipeline.document_pipeline.unit_pipeline_enabled', lambda: unit_mode)
    monkeypatch.setattr('pipeline.translation_pipeline.unit_pipeline_enabled', lambda: unit_mode)
    path = tmp_path / f"worksheet.{extension}"
    Image.new("RGB", (600, 800), "white").save(path)
    recognize = Mock(side_effect=AssertionError('No recognition while gate held'))
    monkeypatch.setattr(ocr, "recognize_image", recognize)
    monkeypatch.setenv('OCR_ACCEPTANCE_REPORT', str(tmp_path/'no-evidence.json'))
    response = document_pipeline.translate(DocumentTranslationRequest(str(path), "English", "Cebuano", mode="fast"))
    assert response.success and Path(response.output_path).suffix == '.pdf'
    assert not response.blocks and response.sidecar['content_summary']['status'] == 'untranslated'
    assert response.sidecar['extraction']['warnings']
    edited = tmp_path/'edited.pdf'
    reconstruct_from_sidecar(response.sidecar, {}, str(path), str(edited))
    with fitz.open(edited) as pdf:
        assert len(pdf) == 1 and pdf[0].get_images() and not pdf[0].get_text().strip()
    assert not recognize.called


def test_mixed_document_pipeline_retains_original_pages_without_reflow(tmp_path, document_pipeline):
    path = tmp_path / "mixed.pdf"
    mixed_pdf(path)
    result = document_pipeline.translate(DocumentTranslationRequest(str(path), "English", "Cebuano", mode="fast"))
    assert result.success and result.sidecar['content_summary']['status'] in {'partial', 'untranslated'}
    assert not any(b.get('ocr_reflow') for b in result.blocks)
    regenerated = tmp_path / 'regenerated.pdf'
    reconstruct_from_sidecar(result.sidecar, {}, str(path), str(regenerated))
    with fitz.open(regenerated) as pdf:
        assert len(pdf) == 3 and pdf[1].get_images()


def test_historical_v2_reflow_sidecar_keeps_regeneration_behavior(tmp_path):
    source = tmp_path/'legacy.pdf'
    mixed_pdf(source)
    entry = rich_block_entry(0, block('Old OCR text'), 'source')
    sidecar = {'version': 2, 'format': '.pdf', 'blocks': [entry]}
    out = tmp_path/'legacy-output.pdf'
    reconstruct_from_sidecar(sidecar, {0: 'Edited historical text'}, str(source), str(out))
    with fitz.open(out) as pdf:
        assert 'Edited historical text' in pdf[0].get_text()
        assert not pdf[0].get_images()


def test_corrupt_and_mismatched_images_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "require_ready", lambda *a: "eng")
    path = tmp_path / "bad.png"
    path.write_bytes(b"Not a PNG")
    with pytest.raises(ocr.OCRUnavailable, match="Invalid"):
        ocr.extract_image(path, "English")
    Image.new("RGB", (300, 300)).save(path, "JPEG")
    with pytest.raises(ocr.OCRUnavailable, match="matching its extension"):
        ocr.extract_image(path, "English")


def test_image_resolution_limits():
    with pytest.raises(ocr.OCRUnavailable, match="200 pixels"):
        ocr.prepare_image(Image.new("RGB", (100, 500)))


def test_transparent_background_is_flattened_to_white():
    image = ocr.prepare_image(Image.new("RGBA", (300, 300), (0, 0, 0, 0)))
    assert image.getpixel((0, 0)) == 255


def test_environment_loads_ocr_paths_without_overriding_process_settings(tmp_path, monkeypatch):
    from config.environment import load_engine_environment
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    monkeypatch.delenv("OCR_ACCEPTANCE_REPORT", raising=False)
    monkeypatch.setenv("OCR_TESSERACT_CMD", "process-override")
    path = tmp_path / ".env"
    path.write_text('TESSDATA_PREFIX="C:/OCR data/tessdata"\nOCR_ACCEPTANCE_REPORT=C:/report.json\nOCR_TESSERACT_CMD=file-value')
    load_engine_environment(path)
    import os
    assert os.environ["TESSDATA_PREFIX"] == "C:/OCR data/tessdata"
    assert os.environ["OCR_ACCEPTANCE_REPORT"] == "C:/report.json"
    assert os.environ["OCR_TESSERACT_CMD"] == "process-override"


def test_reflow_overflow_and_html_are_preserved_without_scan_overlay(tmp_path):
    output = tmp_path / "translated.pdf"
    text = "<script>source</script> " + "Readable translated paragraph. " * 1000
    result = reconstruct_document([block(text)], str(output), "source.png")
    with fitz.open(output) as pdf:
        assert len(pdf) > 1
        extracted = ' '.join(page.get_text() for page in pdf)
        assert "<script>source</script>" in extracted
        assert extracted.count("paragraph.") == 1000
    assert result["layout"] == "separate_translated_text"


def test_output_maps_and_rich_metadata():
    assert choose_output_path("source.jpeg").endswith(".pdf")
    assert rich_block_entry(0, block(), "source")["ocr"]["confidence"] == 55.5
