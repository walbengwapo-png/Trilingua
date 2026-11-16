"""Regressions from the survey and illustrated contact-tracing documents."""
from collections import Counter
from zipfile import ZipFile

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.section import WD_SECTION_START
from PIL import Image
from lxml import etree

from document.reconstructor import _translate_docx_inplace_with_translator
from document.regenerator import reconstruct_from_sidecar


def test_drawings_lists_links_nested_tables_and_shared_headers_survive(tmp_path):
    image = tmp_path/'art.png'
    Image.new('RGB', (20, 20), 'red').save(image)
    doc = Document()
    doc.sections[0].header.paragraphs[0].text = 'Shared header'
    p = doc.add_paragraph()
    run = p.add_run('Before image')
    run.bold = True
    run.add_picture(str(image))
    legacy = OxmlElement('w:pict')
    run._r.append(legacy)
    p.add_run(' after image')
    p = doc.add_paragraph('Contact ')
    link = OxmlElement('w:hyperlink')
    link.set(qn('r:id'), doc.part.relate_to('mailto:test@example.org',
             'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink', is_external=True))
    r, t = OxmlElement('w:r'), OxmlElement('w:t')
    t.text = 'test@example.org'
    r.append(t); link.append(r); p._p.append(link)
    cell = doc.add_table(rows=1, cols=2).cell(0, 0).merge(doc.tables[0].cell(0, 1))
    cell.paragraphs[0].text = 'First question'
    cell.add_paragraph('Second question', style='List Number')
    cell.add_table(rows=1, cols=1).cell(0, 0).text = 'Nested answer'
    doc.add_section(WD_SECTION_START.NEW_PAGE)
    source, output = tmp_path/'in.docx', tmp_path/'out.docx'
    doc.save(source)
    calls = []
    def translate(text, block_type):
        calls.append(text)
        return 'T:' + text
    _translate_docx_inplace_with_translator(source, output, translate)
    assert Counter(calls)['Shared header'] == 1
    assert Counter(calls)['First question'] == 1
    assert Counter(calls)['Nested answer'] == 1
    assert 'test@example.org' not in calls
    after = Document(output)
    assert after.tables[0].cell(0, 0).paragraphs[1].text == 'T:Second question'
    assert after.tables[0].cell(0, 0).paragraphs[1].style.name == 'List Number'
    with ZipFile(source) as before, ZipFile(output) as after_zip:
        a = etree.fromstring(before.read('word/document.xml'))
        b = etree.fromstring(after_zip.read('word/document.xml'))
        for tag in ('w:drawing', 'w:pict', 'w:hyperlink', 'w:tbl', 'w:p', 'w:br'):
            assert len(list(a.iter(qn(tag)))) == len(list(b.iter(qn(tag))))
        assert b.xpath('count(//*[local-name()="t" and text()="test@example.org"])') == 1
        for name in before.namelist():
            if name.startswith('word/media/') or name.endswith('.rels'):
                assert before.read(name) == after_zip.read(name)


def test_new_and_legacy_sidecars_replay_their_own_walk_order(tmp_path):
    doc = Document()
    cell = doc.add_table(rows=1, cols=1).cell(0, 0)
    cell.paragraphs[0].text = 'First'
    cell.add_paragraph('Second')
    original, output = tmp_path/'in.docx', tmp_path/'out.docx'
    doc.save(original)
    new = {'version': 2, 'format': '.docx', 'docx_walk_version': 2, 'blocks': [
        {'block_index': 0, 'text': 'Una'}, {'block_index': 1, 'text': 'Ikaduha'}]}
    reconstruct_from_sidecar(new, {1: 'Edited'}, original, output)
    assert [p.text for p in Document(output).tables[0].cell(0, 0).paragraphs] == ['Una', 'Edited']
    legacy = {'version': 2, 'format': '.docx', 'blocks': [{'block_index': 0, 'text': 'Legacy whole cell'}]}
    reconstruct_from_sidecar(legacy, {}, original, output)
    assert Document(output).tables[0].cell(0, 0).text == 'Legacy whole cell\n'


def test_pipeline_sidecar_can_regenerate_without_blanking_unedited_text(document_pipeline, tmp_path):
    from dto.requests import DocumentTranslationRequest
    doc = Document()
    doc.add_paragraph('First paragraph')
    doc.add_paragraph('Second paragraph')
    original = tmp_path/'source.docx'
    doc.save(original)
    result = document_pipeline.translate(DocumentTranslationRequest(str(original), 'English', 'Cebuano', mode='fast'))
    assert result.success, result.error_message
    out = tmp_path/'edited.docx'
    reconstruct_from_sidecar(result.sidecar, {0: 'Admin edit'}, str(original), str(out))
    assert [p.text for p in Document(out).paragraphs] == ['Admin edit', result.blocks[1]['current_text']]
