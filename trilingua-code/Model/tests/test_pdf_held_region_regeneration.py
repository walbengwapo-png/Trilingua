"""A held native region remains an obstacle during signed-plan regeneration."""
import pymupdf as fitz

from document.extractor import read_pdf
from document.pdf_regions import sha256
from document.regenerator import reconstruct_from_sidecar, rich_block_entry
from document.render_plan import make_plan


def test_edit_does_not_overlap_held_native_neighbor(tmp_path):
    source, output = tmp_path / 'source.pdf', tmp_path / 'published.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=140, height=200)
        page.insert_text((30, 64), 'Source\nHeld source', fontsize=12)
        assert len(page.get_text('blocks')) == 1
        doc.save(source)
    lines = [(block, line) for block in read_pdf(str(source), 'single') for line in block['lines']]
    assert len(lines) == 2
    entries = []
    for index, (block, line) in enumerate(lines):
        original = line['text']
        item = dict(block, text='Target' if index == 0 else original,
                    type='paragraph', position=line['bbox'], lines=[line],
                    region_id='translated' if index == 0 else 'held', passthrough=index == 1)
        entries.append(rich_block_entry(index, item, original))
    extraction = {'original_sha256': sha256(source), 'pages': [{'page': 0}], 'regions': [
        {'region_id': 'translated', 'status': 'translated', 'page': 0},
        {'region_id': 'held', 'status': 'held', 'page': 0, 'reason': 'native_fit_hold'}]}
    sidecar = {'version': 3, 'format': '.pdf', 'blocks': entries,
               'render_plan': make_plan(extraction, entries)}
    reconstruct_from_sidecar(sidecar, {0: 'A second line is needed'},
                             str(source), str(output))
    held = fitz.Rect(entries[1]['position'])
    with fitz.open(output) as doc:
        assert 'Held source' in doc[0].get_text()
        translated_words = [word for word in doc[0].get_text('words') if word[4] not in {'Held', 'source'}]
        assert all((fitz.Rect(word[:4]) & held).get_area() < .1 for word in translated_words)
        assert [word[4] for word in translated_words] == ['A', 'second', 'line', 'is', 'needed']
