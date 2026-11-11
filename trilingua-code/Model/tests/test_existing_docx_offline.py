"""Exercise an existing publisher DOCX through the real pipeline with a fake provider."""
from pathlib import Path
import shutil

from docx import Document

from dto.requests import DocumentTranslationRequest


def test_existing_survey_docx_keeps_paragraph_and_table_structure(tmp_path, document_pipeline):
    original = Path(__file__).resolve().parents[3] / 'test_corpus_v7/originals/EDU01/eng.docx'
    source = tmp_path / 'survey-offline-fixture.docx'
    shutil.copy2(original, source)
    before = Document(source)
    result = document_pipeline.translate(DocumentTranslationRequest(
        str(source), 'English', 'Filipino', mode='fast'))
    assert result.success, result.error_message
    after = Document(result.output_path)
    assert len(after.paragraphs) == len(before.paragraphs)
    assert [[len(row.cells) for row in table.rows] for table in after.tables] == [
        [len(row.cells) for row in table.rows] for table in before.tables]
    assert result.sidecar['blocks']
    assert any(b['source_text'] != b['current_text'] for b in result.sidecar['blocks'])
