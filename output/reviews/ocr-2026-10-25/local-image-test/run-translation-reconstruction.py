"""One-image live translation/reconstruction diagnostic, never an acceptance run."""
import json
import os
from pathlib import Path
import shutil
import sys
import time
from unittest.mock import patch

import fitz

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
root = Path(__file__).resolve().parent
repo = root.parents[3]
sys.path.insert(0, str(repo / 'trilingua-code/Model'))
from config.environment import load_engine_environment
load_engine_environment(repo / 'trilingua-code/.env')

# Bounds apply only to this diagnostic process, not the application configuration.
os.environ['TRANSLATION_CACHE_ENABLED'] = 'false'
os.environ['GPTOSS_MAX_ATTEMPTS'] = '1'
os.environ['GPTOSS_REQUEST_TIMEOUT_SECONDS'] = '60'
from document import ocr_extractor as ocr
from dto.requests import DocumentTranslationRequest
from pipeline.document_pipeline import DocumentPipeline
from pipeline.translation_pipeline import TranslationPipeline
from providers.gptoss import GPTOSSProvider

source = Path('C:/Users/walbe/OneDrive/Desktop/DFS/Facebook Marketing/day-03-five-second-test-1080x1350.png')
folder = root / 'live-cebuano'
folder.mkdir(exist_ok=True)
input_path = folder / 'DFS_5_second_poster.png'
shutil.copy2(source, input_path)
provider = GPTOSSProvider()
budget = {
    'document_limit': 1, 'input': str(source), 'source_language': 'English',
    'target_language': 'Cebuano', 'provider': provider.name, 'model': provider.model_name,
    'billing': 'Existing configured Ollama Cloud account usage; exact incremental charge is not exposed by this API. No purchase or subscription change.',
    'mode': 'fast', 'analysis_and_quality_provider_calls': False,
    'provider_http_attempts_per_request': 1, 'provider_timeout_seconds': 60,
    'release_gate': 'Stubbed only in this isolated diagnostic process; no release acceptance or app upload enabling.',
    'ocr_corrections': 'None. Test the raw extracted text.',
}
(folder / 'preflight.json').write_text(json.dumps(budget, indent=2), encoding='utf-8')

# Record actual requests and reported usage without logging credentials or headers.
post = provider._session.post
requests_observed = []
def recorded_post(*args, **kwargs):
    start = time.monotonic()
    record = {'model': kwargs.get('json', {}).get('model')}
    requests_observed.append(record)
    try:
        response = post(*args, **kwargs)
        record['http_status'] = response.status_code
        if response.ok:
            data = response.json()
            record['prompt_eval_count'] = data.get('prompt_eval_count')
            record['eval_count'] = data.get('eval_count')
        return response
    finally:
        record['elapsed_seconds'] = round(time.monotonic() - start, 3)
        (folder / 'provider-requests.json').write_text(json.dumps(requests_observed, indent=2), encoding='utf-8')
provider._session.post = recorded_post

started = time.monotonic()
try:
    pipeline = DocumentPipeline(TranslationPipeline(provider))
    with patch.object(ocr, 'require_ready', return_value='eng'):
        result = pipeline.translate(DocumentTranslationRequest(
            str(input_path), 'English', 'Cebuano', mode='fast'))
    assert result.success, result.error_message
    assert result.output_validation['status'] == 'passed'
    assert result.blocks and any(b.get('ocr') for b in result.blocks)
    output = Path(result.output_path)
    assert output.suffix == '.pdf' and output.is_file()
    translated = '\n'.join(b.get('text', '') for b in result.blocks)
    (folder / 'translated-text.txt').write_text(translated, encoding='utf-8')
    (folder / 'sidecar.json').write_text(json.dumps(result.sidecar, indent=2, ensure_ascii=False), encoding='utf-8')
    comparisons = [{'index': b['block_index'], 'source': b['source_text'],
                    'translation': b.get('text', ''), 'ocr': b.get('ocr')} for b in result.blocks]
    (folder / 'source-and-translation.json').write_text(json.dumps(comparisons, indent=2, ensure_ascii=False), encoding='utf-8')
    with fitz.open(output) as doc:
        for page in doc:
            page.get_pixmap(dpi=120).save(folder / f'translated-page-{page.number + 1}.png')
        pages = len(doc)
        images = sum(len(page.get_images()) for page in doc)
    report = {**budget, 'status': 'passed_functionally', 'output': str(output),
              'elapsed_seconds': round(time.monotonic() - started, 3), 'blocks': len(result.blocks),
              'pdf_pages': pages, 'embedded_images': images, 'output_validation': result.output_validation,
              'provider_requests': len(requests_observed), 'warnings': result.warnings,
              'limitation': 'Separate text PDF. Original poster graphics and layout are not reconstructed. Translation accuracy needs source comparison.'}
    (folder / 'result.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(translated)
    print(f'OUTPUT: {output}')
except Exception as exc:
    (folder / 'result.json').write_text(json.dumps({**budget, 'status': 'failed',
        'error_type': type(exc).__name__, 'error': str(exc), 'provider_requests': len(requests_observed)}, indent=2), encoding='utf-8')
    raise
