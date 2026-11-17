"""Markdown delimiters and executable examples must never enter translation."""
import re

import pytest

from document.extractor import read_md
from document.reconstructor import reconstruct_document
from document.regenerator import reconstruct_from_sidecar, rich_block_entry
from dto.requests import DocumentTranslationRequest


@pytest.mark.parametrize("source", [
    '# Heading\n\n- First\n  + Nested\n1. Second\n> Quote\n',
    '```python\n>>> print("hello")\n```\n\n~~~js\nlet x = 1;\n~~~\n',
    '````python\n```\ntext inside longer fence\n````\n\n```unclosed\nkeep this\n',
    '\ufeff# Title\r\n\r\n- [x] Done  \r\nUse `python -V` today.\r\n    print("keep")',
    'Use ``a`b`` with [**documentation**](https://example.org/path?q=2).\n',
])
def test_extract_write_round_trip_retains_literal_bytes(tmp_path, source):
    original, output = tmp_path / 'input.md', tmp_path / 'output.md'
    original.write_bytes(source.encode('utf-8'))
    blocks = read_md(original)
    reconstruct_document(blocks, output, original_file=original)
    assert output.read_bytes() == original.read_bytes()


def test_prose_changes_without_changing_code_or_markers_and_regenerates(tmp_path):
    source = '# Title\n\n- One\n2) Two\nUse `x = "yes"` here.\n\n```py\n>>> print("hello")\n```\n'
    original, output = tmp_path / 'input.md', tmp_path / 'output.md'
    original.write_text(source, encoding='utf-8')
    blocks = read_md(original)
    entries = []
    for i, block in enumerate(blocks):
        translated = dict(block)
        if not block.get('passthrough'):
            translated['text'] = 'T:' + block['text']
        entries.append(rich_block_entry(i, translated, block['text']))
    reconstruct_from_sidecar({'version': 2, 'format': '.md', 'blocks': entries}, {}, original, output)
    text = output.read_text(encoding='utf-8')
    assert text.startswith('# T:Title\n\n- T:One\n2) T:Two\n')
    assert '`x = "yes"`' in text
    assert '```py\n>>> print("hello")\n```' in text
    assert 'T:print' not in text
    assert len(re.findall(r'^```', text, re.M)) == 2


def test_inline_code_urls_and_link_delimiters_are_never_sent_to_provider(tmp_path):
    original, output = tmp_path / 'input.md', tmp_path / 'output.md'
    original.write_text('Read [**docs**](https://example.org/x) and ``a`b``.\n', encoding='utf-8')
    blocks = read_md(original)
    for block in blocks:
        if not block.get('passthrough'):
            assert 'https://' not in block['text']
            assert '`' not in block['text']
            assert '[' not in block['text'] and '*' not in block['text']
            block['text'] = 'salin'
    reconstruct_document(blocks, output, original_file=original)
    text = output.read_text(encoding='utf-8')
    assert '[**salin**](https://example.org/x)' in text
    assert '``a`b``' in text


@pytest.mark.parametrize('units', [False, True])
def test_document_pipeline_keeps_code_and_list_markers(document_pipeline, tmp_path, monkeypatch, units):
    monkeypatch.setattr('pipeline.document_pipeline.unit_pipeline_enabled', lambda: units)
    original = tmp_path / 'input.md'
    original.write_text('# Hello\n\n- Read this\n\n```python\n>>> print("hello")\n```\n', encoding='utf-8')
    result = document_pipeline.translate(DocumentTranslationRequest(str(original), 'English', 'Cebuano', mode='fast'))
    assert result.success, result.error_message
    text = open(result.output_path, encoding='utf-8').read()
    assert text.startswith('# ')
    assert '\n- ' in text
    assert '```python\n>>> print("hello")\n```' in text
