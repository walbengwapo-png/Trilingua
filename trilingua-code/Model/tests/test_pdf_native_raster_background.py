import pymupdf as fitz
import pytest
from PIL import Image, ImageChops

from document.extractor import read_pdf
from document.reconstructor import write_pdf_preserved
from dto.requests import DocumentTranslationRequest


def illustrated_page(path, *, paint='background', near_margin=False):
    with fitz.open() as document:
        page = document.new_page(width=300, height=220)
        pixels = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 30, 22), False)
        pixels.clear_with(216)
        if paint != 'foreground':
            image = page.insert_image(page.rect, pixmap=pixels)
        page.insert_text((32, 208 if near_margin else 65), 'The giraffe is tall.',
                         fontsize=14, render_mode=3 if paint == 'hidden_text' else 0)
        if paint == 'foreground':
            page.insert_image(page.rect, pixmap=pixels)
        if paint == 'repeated_image':
            page.insert_image(page.rect, xref=image)
        if paint == 'foreground_detail':
            page.insert_image(fitz.Rect(50, 50, 67, 60), xref=image)
        if paint == 'foreground_path':
            page.draw_circle((59, 60), 8, fill=(0, 0, 1), color=None)
        page.insert_text((32, 100), 'Unchanged caption', fontsize=12)
        document.save(path)


def translated_block(path, target):
    block = next(b for b in read_pdf(str(path)) if 'The giraffe is tall.' in b['text'])
    return dict(block, _original_text=block['text'], text=target, region_id='giraffe')


def page_pixels(page):
    pixmap = page.get_pixmap(matrix=fitz.Matrix(3, 3))
    return Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples)


def image_signatures(page):
    return [(item['bbox'], item['digest']) for item in page.get_image_info(hashes=True)]


def test_replace_visible_text_over_background_without_painting_outside_its_box(tmp_path):
    source, output = tmp_path / 'source.pdf', tmp_path / 'translated.pdf'
    illustrated_page(source)
    target = 'Mataas ang dyirap.'
    block = translated_block(source, target)
    result = write_pdf_preserved([block], str(source), str(output), strict=True)
    assert result['held'] == []
    assert result['layout'] == result['content_coverage'] == 'passed'
    box = fitz.Rect(block['position'])
    assert all(box.contains(fitz.Rect(item['rect'])) for item in result['blocks'])
    with fitz.open(source) as original, fitz.open(output) as translated:
        before, after = original[0], translated[0]
        assert 'Unchanged caption' in after.get_text()
        assert target in after.get_text()
        assert 'The giraffe is tall.' not in after.get_text()
        assert image_signatures(before) == image_signatures(after)
        changed_pixels = ImageChops.difference(page_pixels(before), page_pixels(after)).getbbox()
        assert changed_pixels and (box * fitz.Matrix(3, 3)).irect.contains(fitz.IRect(changed_pixels))


@pytest.mark.parametrize('paint', ['foreground', 'repeated_image', 'hidden_text',
                                 'foreground_detail', 'foreground_path'])
def test_do_not_treat_foreground_or_hidden_text_as_a_safe_background(tmp_path, paint):
    source, output = tmp_path / 'source.pdf', tmp_path / 'translated.pdf'
    illustrated_page(source, paint=paint)
    block = translated_block(source, 'Mataas ang dyirap.')
    result = write_pdf_preserved([block], str(source), str(output), strict=True)
    assert result['held'] == [{'block_index': 0, 'region_id': 'giraffe', 'reason': 'native_fit_hold'}]
    with fitz.open(source) as original, fitz.open(output) as translated:
        assert original[0].get_text() == translated[0].get_text()
        assert page_pixels(original[0]).tobytes() == page_pixels(translated[0]).tobytes()


def test_hold_long_text_near_margin_without_clipping_or_removing_source(tmp_path):
    source, output = tmp_path / 'source.pdf', tmp_path / 'translated.pdf'
    illustrated_page(source, near_margin=True)
    block = translated_block(source, 'Napakataas ng dyirap at napakahaba ng leeg nito.')
    result = write_pdf_preserved([block], str(source), str(output), strict=True)
    assert result['held'] == [{'block_index': 0, 'region_id': 'giraffe', 'reason': 'native_fit_hold'}]
    with fitz.open(source) as original, fitz.open(output) as translated:
        assert len(translated) == 1
        assert original[0].get_text() == translated[0].get_text()
        assert page_pixels(original[0]).tobytes() == page_pixels(translated[0]).tobytes()


def test_cannot_publish_translation_over_original_glyphs(tmp_path, monkeypatch):
    source, output = tmp_path / 'source.pdf', tmp_path / 'translated.pdf'
    illustrated_page(source)
    block = translated_block(source, 'Mataas ang dyirap.')
    monkeypatch.setattr(fitz.Page, 'apply_redactions', lambda *args, **kwargs: False)
    with pytest.raises(ValueError, match='orig-spans-remain'):
        write_pdf_preserved([block], str(source), str(output), strict=True)
    assert not output.exists()


def test_document_job_translates_native_text_independently_of_image_ocr(tmp_path, document_pipeline, monkeypatch):
    source = tmp_path / 'source.pdf'
    illustrated_page(source)
    translations = {'The giraffe is tall.': 'Mataas ang dyirap.', 'Unchanged caption': 'Orihinal na teksto'}

    def translate(blocks, *args, **kwargs):
        return [dict(block, _original_text=block['text'], text=translations[block['text']])
                for block in blocks]

    monkeypatch.setattr('pipeline.document_pipeline.unit_pipeline_enabled', lambda: False)
    monkeypatch.setattr(document_pipeline.translation_pipeline, 'batch_translate_blocks', translate)
    response = document_pipeline.translate(DocumentTranslationRequest(str(source), 'English', 'Filipino', mode='fast'))
    assert response.output_validation['held'] == []
    assert response.content_summary['translated'] == len(translations)
    with fitz.open(response.output_path) as document:
        assert document[0].get_text().splitlines() == list(translations.values())
