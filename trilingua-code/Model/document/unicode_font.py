"""Checked native PDF fallback; the existing signed OCR font manifest stays unchanged."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'native-symbol-fonts'


@lru_cache(maxsize=4)
def fallback_font(bold=False, italic=False):
    style = 'BoldItalic' if bold and italic else 'Bold' if bold else 'Italic' if italic else 'Regular'
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    item = manifest['fonts'][style]
    path = ROOT / item['file']
    if path.parent != ROOT:
        raise ValueError('Invalid native PDF font path')
    contents = path.read_bytes()
    if hashlib.sha256(contents).hexdigest() != item['sha256']:
        raise ValueError('Native PDF font hash mismatch')
    return 'trilinguaUnicode' + style, fitz.Font(fontbuffer=contents)
