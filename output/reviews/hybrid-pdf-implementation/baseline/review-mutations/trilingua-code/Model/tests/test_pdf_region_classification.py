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


def test_native_hold_keeps_later_fitting_block_on_its_page(tmp_path):
    from document.reconstructor import write_pdf_preserved
    source, output = tmp_path/'native.pdf', tmp_path/'out.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=250, height=130)
        page.insert_text((30, 40), 'First source')
        page.insert_text((30, 90), 'Second source')
        doc.save(source)
    blocks = read_pdf(str(source))
    assert len(blocks) == 2
    blocks[0].update(text='Long translation ' * 500, _original_text='First source', region_id='held')
    blocks[1].update(text='Fits', _original_text='Second source', region_id='fits')
    validation = write_pdf_preserved(blocks, str(source), str(output), strict=True)
    assert [entry['region_id'] for entry in validation['held']] == ['held']
    with fitz.open(output) as doc:
        assert len(doc) == 1
        assert 'First source' in doc[0].get_text() and 'Fits' in doc[0].get_text()
        assert 'Second source' not in doc[0].get_text()


@pytest.mark.parametrize('failure', ['uncertain_style', 'missing_font'])
def test_image_wide_hold_discards_earlier_candidate_paragraphs(tmp_path, monkeypatch, failure):
    import document.ocr_extractor as ocr
    import document.image_reconstructor as renderer
    path = tmp_path/'source.pdf'
    fixture(path)
    original = path.read_bytes()
    paragraphs = [{'text':text, 'position':[40, y, 180, y+20], 'page':0,
                   'ocr':{'confidence':99, 'words':[{'text':text, 'position':[40,y,180,y+20], 'confidence':99}]}}
                  for text,y in [('Alpha',50),('Beta',200)]]
    # Pure routing fixture: no recognition or acceptance artifact is produced.
    monkeypatch.setattr(ocr, 'require_ready', lambda *args: 'eng')
    monkeypatch.setattr(ocr, 'recognize_image', Mock(return_value=paragraphs))
    error = renderer.ImageHold('Uncertain source style') if failure == 'uncertain_style' else FileNotFoundError('Missing font asset')
    monkeypatch.setattr(renderer, 'estimate_style', Mock(side_effect=[
        {'font_id':'NotoSans-Regular', 'initial_size':14}, error]))
    blocks, report = inventory_pdf(path, [], 'English')
    assert blocks == []
    assert len(report['regions']) == 1 and report['regions'][0]['status'] == 'held'
    assert report['regions'][0]['reason'] == 'image_safety_hold'
    assert path.read_bytes() == original


def test_held_dto_blocks_show_source_instead_of_attempted_translation(tmp_path, document_pipeline, monkeypatch):
    path = tmp_path/'native.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=250, height=100)
        page.insert_text((30,45), 'Original source')
        doc.save(path)
    monkeypatch.setattr('pipeline.document_pipeline.unit_pipeline_enabled', lambda:False)
    def translated(blocks, *args, **kwargs):
        return [dict(block, text='Unfittable translation ' * 500, _original_text=block['text']) for block in blocks]
    monkeypatch.setattr(document_pipeline.translation_pipeline, 'batch_translate_blocks', translated)
    result = document_pipeline.translate(DocumentTranslationRequest(str(path), 'English', 'Cebuano', mode='fast'))
    assert result.content_summary['translated'] == 0
    assert result.translated_blocks[0]['text'].strip() == 'Original source'
    assert result.translated_blocks[0]['passthrough'] is True
    assert result.blocks[0]['block_index'] == 0
