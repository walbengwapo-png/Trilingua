import json
from pathlib import Path

import pytest

from document.artifact_auth import REPOSITORY, generate_key, key_file, sign, verify
from document.plan_key import require_plan_key, _secret_file


def test_missing_plan_key_is_explicit_not_a_repository_path_error(monkeypatch):
    monkeypatch.delenv('OCR_PLAN_KEY_FILE', raising=False)
    monkeypatch.delenv('OCR_PLAN_KEY_JSON', raising=False)
    with pytest.raises(ValueError, match='PDF signing is not configured'):
        require_plan_key()


@pytest.mark.parametrize('path,message', [('', 'not configured'), ('relative.json', 'absolute path'),
    (str(REPOSITORY / 'forbidden.json'), 'outside the repository')])
def test_bad_key_paths_fail_before_loading(path, message):
    with pytest.raises(ValueError, match=message):
        key_file(path, 'render-plan')


def test_secret_recreation_keeps_existing_signatures_valid(tmp_path, monkeypatch):
    source = tmp_path / 'source.json'
    generate_key(source, 'render-plan')
    monkeypatch.delenv('OCR_PLAN_KEY_FILE', raising=False)
    monkeypatch.setenv('OCR_PLAN_KEY_JSON', source.read_text())
    first = require_plan_key()
    assert not Path(first).is_relative_to(REPOSITORY)
    assert Path(first) != source
    body = sign({'version': 3, 'text': 'Saved plan'}, first, 'render-plan')
    _secret_file.cache_clear()  # A new worker/restart materializes the same secret.
    second = require_plan_key()
    assert second != first
    verify(body, second, 'render-plan')
    with pytest.raises(ValueError, match='signature'):
        verify(dict(body, text='Tampered'), second, 'render-plan')


@pytest.mark.parametrize('data', ['{}', 'not-json', '[]', json.dumps({
    'version': 1, 'purpose': 'acceptance', 'material': 'production', 'secret': '12' * 32})])
def test_invalid_or_wrong_purpose_secret_fails_closed(monkeypatch, data):
    monkeypatch.delenv('OCR_PLAN_KEY_FILE', raising=False)
    monkeypatch.setenv('OCR_PLAN_KEY_JSON', data)
    with pytest.raises(ValueError, match='secret is invalid'):
        require_plan_key()


def test_missing_configuration_stops_before_translation(monkeypatch, document_pipeline, tmp_path):
    from dto.requests import DocumentTranslationRequest
    from unittest.mock import Mock
    monkeypatch.delenv('OCR_PLAN_KEY_FILE', raising=False)
    monkeypatch.delenv('OCR_PLAN_KEY_JSON', raising=False)
    translate = Mock(side_effect=AssertionError('Provider must not be called'))
    monkeypatch.setattr(document_pipeline.translation_pipeline, 'batch_translate_blocks', translate)
    with pytest.raises(ValueError, match='PDF signing is not configured'):
        document_pipeline.translate(DocumentTranslationRequest(str(tmp_path / 'source.pdf'), 'English', 'Filipino', mode='fast'))
    translate.assert_not_called()
