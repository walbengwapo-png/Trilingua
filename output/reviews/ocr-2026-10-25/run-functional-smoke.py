"""Local functional evidence only: real OCR, mock translation, isolated gate stub."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

import fitz

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
root = Path(__file__).resolve().parent
repo = root.parents[2]
sys.path.insert(0, str(repo / 'trilingua-code/Model'))
from config.environment import load_engine_environment
load_engine_environment(repo / 'trilingua-code/.env')
from document import ocr_extractor as ocr
from dto.requests import DocumentTranslationRequest
from pipeline.document_pipeline import DocumentPipeline
from pipeline.translation_pipeline import TranslationPipeline
from tests.mock_providers import MockTranslationProvider
from document.regenerator import reconstruct_from_sidecar

state = ocr.readiness()
assert state['ready'] and {'eng', 'fil', 'ceb'} <= set(state['installed_packs'])
(root / 'runtime-readiness.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
source = root / 'mixed-live-ocr-source.pdf'
with fitz.open() as doc:
    page = doc.new_page()
    page.insert_text((60, 100), 'This native page must remain in the translated document.')
    page = doc.new_page(width=640*72/150, height=480*72/150)
    page.insert_image(page.rect, filename=str(root / 'phototest-preview.png'))
    doc.save(source)
pipeline = DocumentPipeline(TranslationPipeline(MockTranslationProvider()))
# Isolated functional smoke only: no release gate or application setting changes.
with patch.object(ocr, 'require_ready', return_value='eng'):
    result = pipeline.translate(DocumentTranslationRequest(str(source), 'English', 'Cebuano', mode='fast'))
assert result.success and result.sidecar['extraction']['pages'][1]['classification'] == 'ocr'
assert 'quick brown dog' in ' '.join(b['source_text'] for b in result.blocks)
(root / 'mixed-live-ocr-sidecar.json').write_text(json.dumps(result.sidecar, indent=2, ensure_ascii=False), encoding='utf-8')
regenerated = root / 'mixed-mock-regenerated.pdf'
index = next(b['block_index'] for b in result.blocks if b.get('ocr'))
reconstruct_from_sidecar(result.sidecar, {index: 'Edited OCR block: ñ, á, é.'}, str(source), str(regenerated))
with fitz.open(regenerated) as doc:
    assert 'Edited OCR block: ñ, á, é.' in ''.join(p.get_text() for p in doc)
    doc[1].get_pixmap(dpi=110).save(root / 'mixed-mock-regenerated-preview.png')
(root / 'functional-smoke.json').write_text(json.dumps({
    'status': 'passed', 'recognition': 'actual local Tesseract',
    'translation': 'mock provider; no translation quality claim',
    'gate': 'overridden only inside this isolated test process',
    'blocks': len(result.blocks), 'output': result.output_path,
    'regenerated': str(regenerated), 'validation': result.output_validation,
}, indent=2), encoding='utf-8')
print('Actual OCR -> mock translation -> saved sidecar -> edited PDF regeneration: passed.')
