"""Materialize a stable deployment secret outside source control, never mint it on boot."""
from functools import lru_cache
import json
import os
from pathlib import Path
import tempfile

from document.artifact_auth import REPOSITORY, key_file, production_key


@lru_cache(maxsize=1)
def _secret_file(material):
    try:
        data = json.loads(material)
        if not isinstance(data, dict):
            raise ValueError
        if data.get('version') != 1 or data.get('purpose') != 'render-plan':
            raise ValueError
        production_key(data)
        if len(bytes.fromhex(data.get('secret', ''))) != 32:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('Render-plan signing secret is invalid') from None
    directory = Path(tempfile.mkdtemp(prefix='trilingua-plan-key-')).resolve()
    if directory.is_relative_to(REPOSITORY):
        raise ValueError('Signing key temporary directory must be outside the repository')
    path = directory / 'render-plan.json'
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
        json.dump(data, stream)
    return str(path)


def require_plan_key():
    path = os.environ.get('OCR_PLAN_KEY_FILE', '').strip()
    if not path:
        material = os.environ.get('OCR_PLAN_KEY_JSON', '').strip()
        if not material:
            raise ValueError('PDF signing is not configured. An operator must configure the render-plan key before retrying.')
        path = _secret_file(material)
    key, _ = key_file(path, 'render-plan')
    production_key(key)
    return path
