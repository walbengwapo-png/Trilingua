"""Cell padding uses the available cell interior without crossing ruled borders."""
from pathlib import Path

import pytest
import pymupdf as fitz

from document.extractor import read_pdf
from document.reconstructor import write_pdf_preserved


def test_et01_table_note_fits_at_existing_readability_floor(tmp_path):
    source = Path(__file__).resolve().parents[3] / 'test_corpus_v6/originals/ET01/eng.pdf'
    if not source.is_file():
        pytest.skip('Optional publisher corpus is not distributed in the public repository.')
    blocks = read_pdf(str(source), 'single')
    note = next(b for b in blocks if b['text'].startswith('* Insect repellent brand names'))
    note.update(_original_text=note['text'], text=(
        '* Ang mga pangalan ng tatak ng pantaboy-insekto ay ibinigay lamang para sa iyong impormasyon. '
        'Ang Centers for Disease Control and Prevention at ang U.S. Department of Health and Human '
        'Services ay hindi maaaring irekomenda o suportahan ang anumang tatak na produkto.'))
    for block in blocks:
        if block is not note:
            block['passthrough'] = True
    output = tmp_path / 'table-note-partial.pdf'
    result = write_pdf_preserved(blocks, str(source), str(output), strict=True)
    assert result['held'] == []
    fitted = [b for b in result['blocks'] if b['action'] == 'fit']
    assert fitted and min(b['font_size'] for b in fitted) >= 8
    assert result['content_coverage'] == result['layout'] == 'passed'
    # The bottom rule still has identical rendered pixels after transparent redaction.
    clip = fitz.Rect(46, 404.1, 406, 405.1)
    with fitz.open(source) as original, fitz.open(output) as rendered:
        assert original[1].get_pixmap(clip=clip, matrix=fitz.Matrix(3, 3)).samples == rendered[1].get_pixmap(clip=clip, matrix=fitz.Matrix(3, 3)).samples
