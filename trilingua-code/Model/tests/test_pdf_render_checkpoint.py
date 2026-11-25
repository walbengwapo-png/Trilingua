from dataclasses import replace
import io
from shutil import copyfile
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi import HTTPException, UploadFile
import pymupdf as fitz
import pytest

from cache import pdf_checkpoint
from document import pdf_worker
from dto.requests import DocumentTranslationRequest


def test_pdf_retry_reuses_translation_after_reconstruction_failure(tmp_path, document_pipeline, monkeypatch):
    source = tmp_path / 'source.pdf'
    with fitz.open() as document:
        page = document.new_page(width=300, height=200)
        page.insert_text((35, 65), 'The children found a treasure chest.', fontsize=12)
        document.save(source)

    checkpoint_db = tmp_path / 'checkpoints.db'
    monkeypatch.setattr(pdf_checkpoint, 'DB_PATH', checkpoint_db)
    monkeypatch.setattr('pipeline.document_pipeline.unit_pipeline_enabled', lambda: False)
    translate = Mock(side_effect=lambda blocks, *args, **kwargs: [
        dict(block, text='Nakakita ang mga bata og bahandi.', _original_text=block['text'])
        for block in blocks
    ])
    monkeypatch.setattr(document_pipeline.translation_pipeline, 'batch_translate_blocks', translate)
    run_pdf = pdf_worker.run_pdf

    def fail_render(operation, *args, **kwargs):
        if operation == 'render':
            assert checkpoint_db.exists()
            raise ValueError('Synthetic PDF reconstruction failure')
        return run_pdf(operation, *args, **kwargs)

    monkeypatch.setattr(pdf_worker, 'run_pdf', fail_render)
    request = DocumentTranslationRequest(str(source), 'English', 'Cebuano',
                                         mode='fast', render_checkpoint_id=str(uuid4()))
    with pytest.raises(pdf_checkpoint.PDFRenderCheckpointError, match='Translation saved'):
        document_pipeline.translate(request)
    key = pdf_checkpoint.checkpoint_key(request)
    assert pdf_checkpoint.load_checkpoint(key)['blocks'][0]['text'] == 'Nakakita ang mga bata og bahandi.'
    for changed in (replace(request, target_lang='Filipino'), replace(request, mode='thorough'),
                    replace(request, ocr_mode='preview'), replace(request, render_checkpoint_id=str(uuid4()))):
        assert pdf_checkpoint.load_checkpoint(pdf_checkpoint.checkpoint_key(changed)) is None

    fresh_upload = tmp_path / 'retry.pdf'
    copyfile(source, fresh_upload)

    def render_only(operation, *args, **kwargs):
        assert operation == 'render'
        return run_pdf(operation, *args, **kwargs)

    monkeypatch.setattr(pdf_worker, 'run_pdf', render_only)
    result = document_pipeline.translate(replace(request, file_path=str(fresh_upload)))
    translate.assert_called_once()
    assert result.metrics['llm_calls'] == 0
    assert result.metrics['reused_translation_checkpoint'] is True
    assert result.sidecar['render_plan']['regions'][0]['status'] == 'translated'
    assert result.sidecar['blocks'][0]['rendered_layout']['status'] == 'passed'
    with fitz.open(result.output_path) as rendered:
        assert rendered[0].get_text().strip() == 'Nakakita ang mga bata og bahandi.'

    fresh_upload.write_bytes(b'different original')
    changed = replace(request, file_path=str(fresh_upload))
    assert pdf_checkpoint.load_checkpoint(pdf_checkpoint.checkpoint_key(changed)) is None
    after_expiry = pdf_checkpoint.time.time() + pdf_checkpoint.TTL_SECONDS + 1
    monkeypatch.setattr(pdf_checkpoint, 'time', SimpleNamespace(time=lambda: after_expiry))
    assert pdf_checkpoint.load_checkpoint(key) is None


def test_pdf_endpoint_passes_checkpoint_id_and_reports_saved_translation(monkeypatch):
    import server

    job_id = uuid4()

    def fail(request):
        assert request.render_checkpoint_id == str(job_id)
        raise pdf_checkpoint.PDFRenderCheckpointError('Translation saved. The PDF layout could not be rebuilt.')

    monkeypatch.setattr(server, '_run_pipeline_guarded', lambda operation: operation())
    monkeypatch.setattr(server._document_pipeline, 'translate', fail)
    upload = UploadFile(filename='document.pdf', file=io.BytesIO(b'local test'))
    with pytest.raises(HTTPException) as error:
        server.translate_document(upload, 'English', 'Cebuano', 'auto', 'fast', 'strict', job_id)
    assert error.value.status_code == 422
    assert error.value.detail['code'] == 'pdf_render_checkpoint_saved'
    assert error.value.detail['message'].startswith('Translation saved.')
