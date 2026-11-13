"""Complete publisher instructions survive hanging indents across native blocks."""
import json
from pathlib import Path

import pymupdf as fitz
import pytest

from document.extractor import read_pdf


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/et01_complete_instructions.json').read_text())


@pytest.mark.parametrize('instruction', FIXTURE['instructions'])
def test_complete_hanging_instruction_is_one_block(tmp_path, instruction):
    source = tmp_path / 'complete-source.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        for x, y, text in instruction['lines']:
            page.insert_text((x, y), text, fontsize=11)
        # Neither a neighboring column nor a new list item is a continuation.
        page.insert_text((445, 585), 'Neighbor caption.', fontsize=6)
        page.insert_text((142.72, 663), '-- Next independent instruction.', fontsize=11)
        doc.save(source)
    blocks = read_pdf(str(source), 'single')
    assert instruction['complete_text'] in [b['text'] for b in blocks]
    complete = next(b for b in blocks if b['text'] == instruction['complete_text'])
    assert len(complete['lines']) == len(instruction['lines'])
    assert any(b['text'] == '-- Next independent instruction.' for b in blocks)
    assert any(b['text'] == 'Neighbor caption.' for b in blocks)


def test_complete_source_et01_instructions_are_not_fragmented():
    source = Path(__file__).resolve().parents[3] / 'test_corpus_v6/originals/ET01/eng.pdf'
    if not source.is_file():
        pytest.skip('Optional publisher corpus is not distributed in the public repository.')
    blocks = read_pdf(str(source), 'single')
    for instruction in FIXTURE['instructions']:
        assert instruction['complete_text'] in [b['text'] for b in blocks]


def test_finished_list_item_does_not_absorb_indented_paragraph(tmp_path):
    source = tmp_path / 'separate.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((30, 60), '-- Complete instruction.', fontsize=11)
        page.insert_text((41, 74), 'An independent paragraph.', fontsize=11)
        doc.save(source)
    assert [b['text'] for b in read_pdf(str(source), 'single')] == [
        '-- Complete instruction.', 'An independent paragraph.']
