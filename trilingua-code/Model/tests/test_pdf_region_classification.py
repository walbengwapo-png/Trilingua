"""Geometry fixtures only: none of these are OCR acceptance material."""
import io
from pathlib import Path
from unittest.mock import Mock

import fitz
from PIL import Image
import pytest

from document.extractor import read_pdf
from document.pdf_regions import inventory_pdf, local_matches
from document.regenerator import reconstruct_from_sidecar
from dto.requests import DocumentTranslationRequest


def fixture(path, native=False, hidden=False, shared=False):
    stream = io.BytesIO()
    Image.new('RGB', (600, 800), 'white').save(stream, 'PNG')
    with fitz.open() as doc:
        p = doc.new_page()
        xref = p.insert_image(p.rect, stream=stream.getvalue())
        if native or hidden:
            p.insert_text((40, 80), 'Caption', render_mode=3 if hidden else 0)
        if shared:
            p = doc.new_page()
            p.insert_image(p.rect, xref=xref)
        doc.save(path)


def test_gate_hold_does_not_call_recognition_and_keeps_mixed_regions(tmp_path, monkeypatch):
    import document.ocr_extractor as ocr
    path = tmp_path/'source.pdf'
    fixture(path, native=True)
    recognize = Mock(side_effect=AssertionError('OCR past gate'))
    monkeypatch.setattr(ocr, 'recognize_image', recognize)
    blocks, report = inventory_pdf(path, read_pdf(str(path)), 'English')
    assert blocks and {r['source_kind'] for r in report['regions']} == {'native', 'raster'}
    assert report['regions'][-1]['reason'] == 'ocr_acceptance_hold'
    assert not recognize.called


def test_all_held_pipeline_and_regeneration_preserve_original(tmp_path, document_pipeline, monkeypatch):
    path = tmp_path/'source.pdf'
    fixture(path)
    translate = Mock(side_effect=AssertionError('All-held must not translate'))
    monkeypatch.setattr(document_pipeline.translation_pipeline, 'batch_translate_blocks', translate)
    result = document_pipeline.translate(DocumentTranslationRequest(str(path), 'English', 'Cebuano', mode='fast'))
    assert result.blocks == []
    assert result.sidecar['content_summary']['status'] == 'untranslated'
    assert result.sidecar['content_summary']['translated'] == 0
    assert Path(result.output_path).read_bytes() == path.read_bytes()
    assert '_untranslated.pdf' in result.output_path
    out = tmp_path/'regen.pdf'
    reconstruct_from_sidecar(result.sidecar, {}, str(path), str(out))
    assert out.read_bytes() == path.read_bytes()


def test_hidden_native_is_not_used_as_gate_shortcut(tmp_path):
    path = tmp_path/'hidden.pdf'
    fixture(path, hidden=True)
    blocks, report = inventory_pdf(path, read_pdf(str(path)), 'English')
    assert not blocks
    assert any(r['source_kind'] == 'hidden_ocr' for r in report['regions'])


def test_shared_image_inventory_is_document_wide(tmp_path):
    path = tmp_path/'shared.pdf'
    fixture(path, shared=True)
    _, report = inventory_pdf(path, [], 'English')
    assert all(r['occurrence_count'] == 2 and r['safety_hold'] for r in report['regions'])


def test_local_many_to_many_dedup_does_not_merge_repeated_words_elsewhere():
    native = [{'text': 'the lesson', 'position': [0, 0, 60, 20], 'visible': True},
              {'text': 'the lesson', 'position': [0, 100, 60, 120], 'visible': True}]
    words = [{'text': 'the', 'position': [0, 0, 20, 20]},
             {'text': 'lesson', 'position': [20, 0, 60, 20]}]
    matches = local_matches(native, words)
    assert [(m['native'], m['ocr']) for m in matches] == [(0, 0), (0, 1)]


def test_strict_native_overflow_keeps_source_and_page_count(tmp_path):
    from document.reconstructor import write_pdf_preserved
    source, output = tmp_path/'native.pdf', tmp_path/'out.pdf'
    with fitz.open() as doc:
        p = doc.new_page(width=250, height=100)
        p.insert_text((30, 45), 'Source text')
        doc.save(source)
    blocks = read_pdf(str(source))
    blocks[0].update(text='A very long translation. ' * 500, _original_text='Source text', region_id='native')
    result = write_pdf_preserved(blocks, source, str(output), strict=True)
    assert result['held'][0]['reason'] == 'native_fit_hold'
    with fitz.open(output) as doc:
        assert len(doc) == 1 and 'Source text' in doc[0].get_text()
