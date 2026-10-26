"""Frozen, bounded reconstruction contract; regeneration never recognizes text."""
import hashlib
import importlib.metadata
import json
import os

import fitz
from document.image_reconstructor import FONT_ROOT, ALGORITHM_VERSION, font_asset, decode_mask

PLAN_VERSION = 3
MAX_PLAN_BYTES = 16_000_000


def runtime_signature():
    versions = {'pymupdf': fitz.VersionBind}
    for package in ('pillow', 'opencv-python-headless'):
        try: versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: versions[package] = None
    return versions


def font_manifest_hash():
    return hashlib.sha256((FONT_ROOT/'manifest.json').read_bytes()).hexdigest()


def check_bounds(plan):
    from document.pixel_budget import check_actions
    if len(json.dumps(plan,ensure_ascii=False).encode('utf-8')) > MAX_PLAN_BYTES:
        raise ValueError('Render plan exceeds 16 MB limit')
    if len(plan.get('pages', [])) > 50 or len(plan.get('regions', [])) > 10_000:
        raise ValueError('Render plan page/region limit exceeded')
    check_actions(plan.get('image_actions', []))
    for action in plan.get('image_actions', []): decode_mask(action)


def make_plan(extraction, entries):
    plan = {'version': PLAN_VERSION, 'algorithm_version': ALGORITHM_VERSION,
            'original_sha256': extraction['original_sha256'],
            'font_manifest_sha256': font_manifest_hash(), 'runtime': runtime_signature(),
            'regions': extraction['regions'], 'pages': extraction['pages'],
            'image_actions': extraction.get('image_actions', []),
            'native_fit_decisions': {b['region_id']:b.get('rendered_layout', {}) for b in entries if b.get('region_id') and not b.get('image_region')}}
    return sign_plan(plan, entries)


def block_digest(entries):
    from document.artifact_auth import canonical
    editable = {'text', 'current_text', 'ai_translated_text'}
    return hashlib.sha256(canonical([{k:v for k,v in b.items() if k not in editable} for b in entries])).hexdigest()


def sign_plan(plan, entries):
    from document.artifact_auth import sign
    plan = dict(plan, blocks_sha256=block_digest(entries))
    plan = sign(plan, os.environ.get('OCR_PLAN_KEY_FILE', ''), 'render-plan')
    check_bounds(plan)
    return plan


def validate_plan(plan, original, entries=None):
    from document.pdf_regions import sha256
    from document.artifact_auth import verify
    check_bounds(plan)
    verify(plan, os.environ.get('OCR_PLAN_KEY_FILE', ''), 'render-plan')
    if plan.get('version') != PLAN_VERSION or plan.get('algorithm_version') != ALGORITHM_VERSION:
        raise ValueError('Unsupported render plan/algorithm version')
    if sha256(original) != plan.get('original_sha256'):
        raise ValueError('Original hash mismatch')
    if entries is not None and block_digest(entries) != plan.get('blocks_sha256'):
        raise ValueError('Signed block metadata mismatch')
    if plan.get('runtime') != runtime_signature():
        raise ValueError('PDF renderer version mismatch')
    if plan.get('font_manifest_sha256') != font_manifest_hash():
        raise ValueError('Font manifest hash mismatch')
    manifest=json.loads((FONT_ROOT/'manifest.json').read_text(encoding='utf-8'))
    for font_id in manifest['fonts']: font_asset(font_id)
