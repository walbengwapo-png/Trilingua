"""Searchable scan routing and saved-text consistency; synthetic geometry only."""
import io
from unittest.mock import Mock

import pymupdf as fitz
import numpy as np
import pytest
from PIL import ImageDraw, ImageFont

from document import ocr_extractor as ocr
from document.extractor import read_pdf
from document.image_reconstructor import (FONT_ROOT, ImageHold, apply_actions, decode_mask,
    occurrence_safety, plan_images, source_image, validate_output)
from document.pdf_regions import inventory_pdf
from .test_pdf_image_layout import geometry, action_for


def searchable_scan(tmp_path, visible_overlay=False, redaction=False, decorated=False, gradient=False):
    image, words = geometry()
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT_ROOT/'NotoSans-Regular.ttf'), 24)
    draw.text((40, 220), 'HELD', font=font, fill=(20, 35, 60))
    held_box = list(draw.textbbox((40, 220), 'HELD', font=font))
    if decorated:
        draw.rectangle((450, 200, 590, 350), fill=(250, 90, 30))
    if gradient:
        pixels = np.array(image)
        area = pixels[60:135, 20:370]
        background = (area == [245, 245, 245]).all(axis=2)
        ramp = np.broadcast_to(np.arange(350)[None, :, None]//4 + 140, area.shape)
        area[background] = ramp[background]
        from PIL import Image
        image = Image.fromarray(pixels)
    data = io.BytesIO()
    image.save(data, 'PNG')
    source = tmp_path/'searchable.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=500)
        page.insert_image(fitz.Rect(0, 0, 600, 400), stream=data.getvalue())
        page.insert_text((40, 100), 'SOURCE', fontsize=24, render_mode=0 if visible_overlay else 3)
        page.insert_text((180, 100), 'STALE SEARCH', fontsize=12, render_mode=3)
        page.insert_text((40, 250), 'HELD', fontsize=24, render_mode=3)
        page.insert_text((40, 450), 'Visible caption outside the image')
        page.insert_link({'kind': fitz.LINK_URI, 'from': fitz.Rect(35, 65, 350, 120), 'uri': 'https://example.org/'})
        if redaction:
            page.add_redact_annot(fitz.Rect(30, 430, 300, 460))
        doc.save(source)
    return source, image, words, held_box


def test_invisible_search_layer_does_not_block_ocr_or_count_as_untranslated_content(tmp_path, monkeypatch):
    source, _, words, held_box = searchable_scan(tmp_path)
    monkeypatch.setattr(ocr, 'require_ready', lambda *a, **k: 'eng')
    recognition = Mock(return_value=[
        {'type': 'paragraph', 'page': 0, 'text': 'SOURCE', 'position': words[0]['position'],
         'ocr': {'words': words, 'confidence': 99}, 'style': {}},
        {'type': 'paragraph', 'page': 0, 'text': 'HELD', 'position': held_box,
         'ocr': {'words': [{'text': 'HELD', 'position': held_box, 'confidence': 20}], 'confidence': 20}, 'style': {}},
    ])
    monkeypatch.setattr(ocr, 'recognize_image', recognition)
    monkeypatch.setattr('document.image_reconstructor.estimate_style', lambda *a: {
        'font_id': 'NotoSans-Regular', 'initial_size': 18})
    blocks, report = inventory_pdf(source, read_pdf(str(source)), 'English', ocr_mode='preview')
    assert recognition.call_count == 1
    assert any(b.get('image_region') and b['text'] == 'SOURCE' for b in blocks)
    assert any(b['text'] == 'Visible caption outside the image' for b in blocks)
    hidden = [r for r in report['regions'] if r['source_kind'] == 'hidden_ocr']
    assert hidden and all(r['status'] == 'container' and r['parent_region_id'] for r in hidden)
    held = [r for r in report['regions'] if r['status'] == 'held']
    assert len(held) == 1 and held[0]['source_kind'] == 'raster_text'


def test_replacement_removes_only_old_search_text_and_preserves_unedited_content_and_links(tmp_path):
    source, image, words, _ = searchable_scan(tmp_path)
    action = action_for(image, words, 'TARGET')
    with fitz.open(source) as doc:
        action.update(page=0, xref=doc[0].get_images()[0][0], region_id='translated')
        apply_actions(doc, [action])
        output = tmp_path/'translated.pdf'
        doc.save(output, garbage=4, deflate=True)
    validate_output(output, [action])
    with fitz.open(output) as doc:
        text = doc[0].get_text()
        assert 'TARGET' in text and 'SOURCE' not in text and 'STALE SEARCH' not in text
        assert 'HELD' in text and 'Visible caption outside the image' in text
        assert [link['uri'] for link in doc[0].get_links()] == ['https://example.org/']
        pixels = np.array(source_image(doc, doc[0].get_images()[0][0]))
        assert np.array_equal(pixels[~decode_mask(action)], np.array(image)[~decode_mask(action)])


@pytest.mark.parametrize('visible_overlay,redaction', [(True, False), (False, True)])
def test_visible_text_and_existing_redactions_remain_protected(tmp_path, visible_overlay, redaction):
    source, _, _, _ = searchable_scan(tmp_path, visible_overlay, redaction)
    with fitz.open(source) as doc:
        with pytest.raises(ImageHold):
            occurrence_safety(doc, 0, doc[0].get_images()[0][0])


@pytest.mark.parametrize('gradient', [False, True])
def test_searchable_scan_uses_local_background_and_keeps_artwork_outside_edits(tmp_path, gradient):
    source, image, words, _ = searchable_scan(tmp_path, decorated=True, gradient=gradient)
    with fitz.open(source) as doc:
        xref = doc[0].get_images()[0][0]
    actions, held = plan_images(source, [{'page': 0, 'region_id': 'scan-word', 'text': 'TARGET',
        'position': [35, 65, 350, 120], 'ocr': {'words': words},
        'image_region': {'xref': xref, 'image_bbox': [0, 0, 600, 400],
                         'estimated_style': {'font_id': 'NotoSans-Regular', 'initial_size': 18}}}])
    if gradient:
        assert not actions and held
    else:
        assert len(actions) == 1 and not held
        with fitz.open(source) as doc:
            apply_actions(doc, actions)
            output = tmp_path/'decorated-translated.pdf'
            doc.save(output, garbage=4, deflate=True)
        validate_output(output, actions)
        with fitz.open(output) as doc:
            pixels = np.array(source_image(doc, doc[0].get_images()[0][0]))
            mask = decode_mask(actions[0])
            assert np.array_equal(pixels[~mask], np.array(image)[~mask])
            assert 'TARGET' in doc[0].get_text() and 'SOURCE' not in doc[0].get_text()


def test_conflicting_targets_hold_one_region_before_rendering(tmp_path):
    source, _, words, held_box = searchable_scan(tmp_path)
    with fitz.open(source) as doc:
        xref = doc[0].get_images()[0][0]
    blocks = [{'page': 0, 'region_id': str(index), 'text': 'TARGET', 'position': target,
               'ocr': {'words': geometry}, 'image_region': {'xref': xref, 'image_bbox': [0, 0, 600, 400],
                   'estimated_style': {'font_id': 'NotoSans-Regular', 'initial_size': 18}}}
              for index, (target, geometry) in enumerate([
                  ([35, 65, 350, 185], words),
                  ([35, 170, 350, 280], [{'text': 'HELD', 'position': held_box, 'confidence': 99}])])]
    actions, held = plan_images(source, blocks)
    assert len(actions) == 1 and held == [{'region_id': '1', 'reason': 'Overlapping target boxes'}]
    with fitz.open(source) as doc:
        apply_actions(doc, actions)
        output = tmp_path/'partial.pdf'
        doc.save(output)
    validate_output(output, actions)
    with fitz.open(output) as doc:
        assert 'HELD' in doc[0].get_text() and 'TARGET' in doc[0].get_text()


def test_unclearable_search_text_holds_the_edit_without_changing_the_original(tmp_path, monkeypatch):
    source, _, words, _ = searchable_scan(tmp_path)
    original = source.read_bytes()
    with fitz.open(source) as doc:
        xref = doc[0].get_images()[0][0]
    monkeypatch.setattr(fitz.Page, 'apply_redactions', lambda *a, **k: True)
    actions, held = plan_images(source, [{'page': 0, 'region_id': 'unclearable', 'text': 'TARGET',
        'position': [35, 65, 350, 120], 'ocr': {'words': words},
        'image_region': {'xref': xref, 'image_bbox': [0, 0, 600, 400],
                         'estimated_style': {'font_id': 'NotoSans-Regular', 'initial_size': 18}}}])
    assert not actions and held == [{'region_id': 'unclearable', 'reason': 'Search text overlaps an unchanged area'}]
    assert source.read_bytes() == original
