"""Native text replacement must not paint over nearby table borders."""
import pymupdf as fitz
import pytest

from document.extractor import read_pdf
from document.reconstructor import write_pdf_preserved


@pytest.mark.parametrize('filled_rule', [False, True])
def test_native_redaction_preserves_pixels_of_nearby_table_rule(tmp_path, filled_rule):
    source, output = tmp_path / 'source.pdf', tmp_path / 'output.pdf'
    clip = fitz.Rect(35, 98.5, 140, 99.5)
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=200)
        page.draw_rect(page.rect, fill=(1, .95, .90), color=None)
        page.insert_text((30, 94), 'Source cell text', fontsize=12)
        if filled_rule:
            page.draw_rect(fitz.Rect(25, 98.7, 275, 99.3), fill=(0, 0, 0), color=None)
        else:
            page.draw_line((25, 99), (275, 99), color=(0, 0, 0), width=.6)
        before = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=clip).samples
        doc.save(source)
    blocks = read_pdf(str(source), 'single')
    assert len(blocks) == 1
    blocks[0].update(text='Target cell text', _original_text=blocks[0]['text'])
    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)
    assert report['status'] == 'passed' and not report['held']
    with fitz.open(output) as doc:
        assert 'Target cell text' in doc[0].get_text()
        assert 'Source cell text' not in doc[0].get_text()
        after = doc[0].get_pixmap(matrix=fitz.Matrix(4, 4), clip=clip).samples
        assert after == before, 'Native redaction damaged the nearby table border'
