"""A text-bearing footer is a protected panel, not spare layout space."""
import pymupdf as fitz

from document.extractor import read_pdf
from document.reconstructor import write_pdf_preserved


def test_translation_never_expands_into_another_text_bearing_panel(tmp_path):
    source, output = tmp_path / 'source.pdf', tmp_path / 'output.pdf'
    footer = fitz.Rect(0, 205, 320, 280)
    with fitz.open() as doc:
        page = doc.new_page(width=320, height=280)
        page.draw_rect(footer, fill=(.8, .9, 1), color=None)
        page.insert_text((25, 165), 'Neighbor above stays', fontsize=12)
        page.insert_text((25, 192), 'Label', fontsize=14)
        page.insert_text((25, 255), 'Footer stays', fontsize=10)
        before = page.get_pixmap(clip=footer, matrix=fitz.Matrix(2, 2)).samples
        doc.save(source)
    blocks = read_pdf(str(source), 'single')
    for block in blocks:
        if block['text'] == 'Label':
            block.update(_original_text=block['text'], text=(
                'A longer translated label needs several lines and must stay outside the colored footer.'))
        else:
            block['passthrough'] = True
    report = write_pdf_preserved(blocks, str(source), str(output), strict=True)
    with fitz.open(output) as doc:
        after = doc[0].get_pixmap(clip=footer, matrix=fitz.Matrix(2, 2)).samples
        assert after == before, 'Translated label painted over the footer background'
    assert report['layout'] == 'passed'
