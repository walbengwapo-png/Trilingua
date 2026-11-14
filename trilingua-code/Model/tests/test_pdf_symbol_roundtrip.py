import pymupdf as fitz
import pytest

from document.extractor import read_pdf
from document.reconstructor import write_pdf_preserved
from document.unicode_font import fallback_font


@pytest.mark.parametrize('bold,italic', [(False, False), (True, False), (False, True), (True, True)])
def test_symbol_fallback_preserves_symbols_and_words(tmp_path, bold, italic):
    source, output = tmp_path / 'source.pdf', tmp_path / 'output.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 80), 'Original sentence with room for translation.', fontsize=11)
        doc.save(source)
    blocks = read_pdf(str(source))
    text = '\u26a0 Maayong buntag \u2705 Kompleto \u26d4 Hunong \u2715 Wala'
    blocks[0].update(text=text, _original_text=blocks[0]['text'])
    blocks[0]['style'].update(bold=bold, italic=italic)
    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)
    assert report['status'] == 'passed'
    with fitz.open(output) as doc:
        assert ''.join(text.split()) == ''.join(doc[0].get_text().split())


def test_packaged_fallback_reports_actual_glyph_coverage():
    _, font = fallback_font()
    assert all(font.has_glyph(ord(c)) for c in '\u26a0\u2705\u26d4\u2715\u00f1\u2019')
