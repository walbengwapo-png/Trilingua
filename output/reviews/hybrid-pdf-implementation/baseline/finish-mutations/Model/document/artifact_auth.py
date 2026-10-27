"""Local HMAC trust. An administrator possessing the key can issue artifacts."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets

REPOSITORY = Path(__file__).resolve().parents[3]
MAX_ARTIFACT_BYTES = 24_000_000


def canonical(value):
    def normalized(item):
        # Laravel's associative JSON decoding coalesces empty containers and
        # integral floats; these representations must have the same signature.
        if isinstance(item, dict):
            return {k:normalized(v) for k,v in item.items()} if item else []
        if isinstance(item, (list, tuple)):
            return [normalized(v) for v in item]
        if isinstance(item, float) and item.is_integer():
            return int(item)
        return item
    return json.dumps(normalized(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def load_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError('Trust artifact exceeds 24 MB limit')
    return json.loads(path.read_text(encoding='utf-8'))


def key_file(path, purpose):
    path = Path(path).resolve()
    if path.is_relative_to(REPOSITORY):
        raise ValueError('Signing keys must be outside the repository')
    key = load_json(path)
    if key.get('version') != 1 or key.get('purpose') != purpose:
        raise ValueError('Signing key purpose/version mismatch')
    secret = bytes.fromhex(key['secret'])
    if len(secret) != 32:
        raise ValueError('Signing key must contain 32 random bytes')
    return key, secret


def production_key(key):
    if key.get('material') != 'production':
        raise ValueError('Fixture keys cannot be loaded by the application')


def generate_key(path, purpose):
    path = Path(path).resolve()
    if path.is_relative_to(REPOSITORY):
        raise ValueError('Signing keys must be outside the repository')
    if purpose not in {'acceptance', 'render-plan'}:
        raise ValueError('Unsupported key purpose')
    data = {'version': 1, 'purpose': purpose, 'material': 'production',
            'secret': secrets.token_hex(32)}
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
        json.dump(data, stream)


def sign(body, path, purpose):
    key, secret = key_file(path, purpose)
    production_key(key)
    body = {k: v for k, v in body.items() if k != 'signature'}
    message = ('trilingua:' + purpose + ':v1\0').encode() + canonical(body)
    return {**body, 'signature': {'algorithm': 'HMAC-SHA256', 'purpose': purpose,
            'value': hmac.new(secret, message, hashlib.sha256).hexdigest()}}


def verify(body, path, purpose):
    signature = body.get('signature') or {}
    expected = sign(body, path, purpose)['signature']
    if (signature.get('algorithm') != expected['algorithm'] or signature.get('purpose') != purpose
            or not hmac.compare_digest(str(signature.get('value', '')), expected['value'])):
        raise ValueError('Invalid or missing artifact signature')
