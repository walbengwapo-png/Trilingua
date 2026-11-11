"""A URL's native underline follows reflow without erasing unrelated rules."""
import pymupdf as fitz

from document.extractor import read_pdf
from document.reconstructor import write_pdf_preserved


def test_reflow_relocates_url_underline_and_preserves_table_rule(tmp_path):
    source, output = tmp_path / 'source.pdf', tmp_path / 'output.pdf'
    url = 'https://example.org/a'
    clip = fitz.Rect(20, 144, 220, 146)
    with fitz.open() as doc:
        page = doc.new_page(width=240, height=210)
        page.insert_text((30, 52), 'More information:', fontsize=12)
        page.insert_text((30, 70), url, fontsize=12, color=(0, 0, 1))
        page.draw_line((30, 71), (30 + fitz.get_text_length(url, fontsize=12), 71),
                       color=(0, 0, 1), width=.5)
        page.draw_line((20, 145), (220, 145), color=(0, 0, 0), width=.6)
        rule_pixels = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=clip).samples
        doc.save(source)
    blocks = read_pdf(str(source), 'single')
    assert len(blocks) == 1
    target = 'Karagdagang detalye tungkol sa mga hakbang na ito: ' + url
    blocks[0].update(text=target, _original_text=blocks[0]['text'])
    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)
    assert not report['held']
    with fitz.open(output) as doc:
        page = doc[0]
        blue_lines = [d['rect'] for d in page.get_drawings() if d.get('color') == (0, 0, 1)]
        assert not any(abs(r.y0 - 71) < .1 for r in blue_lines), 'Old underline crosses reflowed prose'
        assert any(r.y0 > 80 for r in blue_lines), 'Reflowed URL lost its underline'
        assert page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=clip).samples == rule_pixels
        assert url in ''.join(page.get_text().split())
