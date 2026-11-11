"""PDF instructions stay whole and explicitly preserved names never reach translation."""
import pymupdf as fitz
import pytest

from config.processing_modes import FAST
from document.extractor import read_pdf
from document.map import build_document_map, table_headers_for
from document.reconstructor import write_pdf_preserved
from dto.responses import TranslationResponse
from pipeline.translation_pipeline import TranslationPipeline
from providers.base import TranslationProvider


def test_mixed_bold_instruction_keeps_its_continuation(tmp_path):
    source = tmp_path / 'instruction.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=200)
        prefix = 'Once a week, '
        page.insert_text((30, 60), prefix, fontname='hebo', fontsize=12)
        x = 30 + fitz.get_text_length(prefix, fontname='hebo', fontsize=12)
        page.insert_text((x, 60), 'empty water-', fontname='helv', fontsize=12)
        page.insert_text((30, 76), 'filled containers and scrub them.', fontsize=12)
        doc.save(source)
    blocks = read_pdf(str(source), 'single')
    assert len(blocks) == 1
    assert blocks[0]['text'] == 'Once a week, empty water- filled containers and scrub them.'
    assert any(run['bold'] for line in blocks[0]['lines'] for run in line['runs'])
    assert any(not run['bold'] for line in blocks[0]['lines'] for run in line['runs'])


def test_bold_heading_and_body_remain_separate(tmp_path):
    source = tmp_path / 'heading.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=200)
        page.insert_text((30, 60), 'Instructions', fontname='hebo', fontsize=12)
        page.insert_text((30, 76), 'Read the next paragraph.', fontsize=12)
        doc.save(source)
    assert [b['text'] for b in read_pdf(str(source), 'single')] == [
        'Instructions', 'Read the next paragraph.']


@pytest.mark.parametrize('marker', ['\u2022', '\ufffd\ufffd'])
@pytest.mark.parametrize('marker_spans', [1, 2])
def test_native_list_marker_is_preserved_outside_translated_prose(tmp_path, marker, marker_spans):
    from document.image_reconstructor import FONT_ROOT
    source, output = tmp_path / 'bullet.pdf', tmp_path / 'translated.pdf'
    clip = fitz.Rect(28, 45, 65, 65)
    with fitz.open() as doc:
        page = doc.new_page(width=350, height=200)
        page.insert_font(fontname='marker', fontfile=str(FONT_ROOT / 'NotoSans-Regular.ttf'))
        page.insert_text((30, 60), marker, fontname='marker', fontsize=11, color=(1, 0, 0))
        if marker_spans == 2:
            page.insert_font(fontname='marker2', fontfile=str(FONT_ROOT / 'NotoSans-Bold.ttf'))
            page.insert_text((36, 60), marker, fontname='marker2', fontsize=11, color=(1, 0, 0))
        page.insert_text((70, 60), 'Empty the water-', fontsize=11)
        page.insert_text((70, 74), 'filled container.', fontsize=11)
        extracted_marker = page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE |
                                        fitz.TEXT_PRESERVE_LIGATURES)['blocks'][0]['lines'][0]['spans'][0]['text'].strip()
        pixels = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip).samples
        doc.save(source)
    blocks = read_pdf(str(source), 'single')
    prose = [b for b in blocks if not b.get('passthrough')]
    assert [b['text'] for b in prose] == ['Empty the water- filled container.']
    assert any(b.get('passthrough') and b['text'] == extracted_marker for b in blocks)
    prose[0].update(text='Alisin ang tubig sa lalagyan.', _original_text=prose[0]['text'])
    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)
    assert not report['held']
    with fitz.open(output) as doc:
        assert doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip).samples == pixels
        assert 'Alisin ang tubig sa lalagyan.' in ' '.join(doc[0].get_text().split())


def test_separate_marker_spacing_does_not_enlarge_the_prose_box(tmp_path):
    from document.image_reconstructor import FONT_ROOT
    source = tmp_path / 'marker-spacing.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=350, height=200)
        for name, file, x in [('regular', 'NotoSans-Regular.ttf', 34), ('bold', 'NotoSans-Bold.ttf', 30)]:
            page.insert_font(fontname=name, fontfile=str(FONT_ROOT / file))
            page.insert_text((x, 60), '•', fontname=name, fontsize=11, color=(1, 0, 0))
        page.insert_text((34, 60), '  ', fontname='regular', fontsize=11)
        page.insert_text((42, 60), 'Empty the water-', fontsize=11)
        page.insert_text((42, 74), 'filled container.', fontsize=11)
        doc.save(source)
    prose = [b for b in read_pdf(str(source), 'single') if not b.get('passthrough')]
    assert [b['text'] for b in prose] == ['Empty the water- filled container.']
    assert prose[0]['position'][0] == 42


def test_missing_unmapped_marker_still_fails_saved_text_validation(tmp_path):
    from document.image_reconstructor import FONT_ROOT
    from validators.translation_validator import validate_pdf_output
    source = tmp_path / 'missing-marker.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=200, height=200)
        page.insert_font(fontname='marker', fontfile=str(FONT_ROOT / 'NotoSans-Regular.ttf'))
        page.insert_text((30, 60), '\ufffd', fontname='marker', fontsize=11)
        doc.save(source)
    report = validate_pdf_output(source, [{'block_index': 0, 'source_page': 0, 'page': 0,
        'rect': [28, 45, 54, 65], 'text': '\ufffd\ufffd', 'font_size': 11, 'action': 'passthrough'}], 1)
    assert report['status'] == 'failed'
    assert any('missing rendered text' in issue for issue in report['issues'])


def test_pdf_brand_column_retains_structure_and_preserves_name(tmp_path):
    source = tmp_path / 'brands.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=420, height=220)
        for x in (20, 160, 400):
            page.draw_line((x, 30), (x, 160))
        for y in (30, 80, 120, 160):
            page.draw_line((20, y), (400, y))
        for x, y, text in [(30, 55, 'Ingredient'), (170, 55, 'Some brand name examples'),
                           (30, 105, 'Oil'), (170, 105, 'Repel'),
                           (30, 145, 'Cream'), (170, 145, 'Example (for children)')]:
            page.insert_text((x, y), text, fontsize=10)
        doc.save(source)
    blocks = read_pdf(str(source), 'single')
    brand = next(b for b in blocks if b['text'] == 'Repel')
    index = blocks.index(brand)
    assert brand['type'] == 'table_cell'
    assert brand.get('passthrough') is True
    assert 'Some brand name examples' in table_headers_for(build_document_map(blocks), index)
    mixed = next(b for b in blocks if b['text'] == 'Example (for children)')
    assert not mixed.get('passthrough'), 'Descriptive qualifiers still require translation'


class BrandTranslatingProvider(TranslationProvider):
    name, model_name = 'mock', 'identity-regression'

    def __init__(self):
        self.calls = 0

    def translate(self, **kwargs):
        self.calls += 1
        return TranslationResponse('Iwasan', provider=self.name, model=self.model_name)

    def estimate_tokens(self, text):
        return len(text.split())

    def health(self):
        return {'status': 'ok'}


@pytest.mark.parametrize('method', ['batch_translate_blocks', 'batch_translate_units'])
def test_explicit_passthrough_name_bypasses_provider_and_stale_cache(method):
    from unittest.mock import Mock
    provider = BrandTranslatingProvider()
    cache = Mock()
    cache.get.return_value = 'Iwasan'
    pipeline = TranslationPipeline(provider)
    result = getattr(pipeline, method)([{'text': 'Repel', 'passthrough': True}],
        'English', 'Filipino', mode=FAST, translation_cache=cache)
    assert result[0]['text'] == 'Repel'
    assert result[0]['passthrough'] is True
    assert provider.calls == 0
    cache.get.assert_not_called()
