"""One fresh balanced translation per original; no application source changes."""
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests
import fitz

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'trilingua-code' / 'Model'
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / 'evidence'
OUTPUT = HERE / 'translated'
sys.path.insert(0, str(ENGINE))
from config.environment import load_engine_environment
from benchmarks.phase6_unit_pipeline_gptoss import sha256, write_json, pdf_structure, pdf_text, score, span_checks

PAIRS = [('English', 'Cebuano'), ('English', 'Cebuano'), ('English', 'Filipino'),
         ('Filipino', 'Cebuano'), ('Filipino', 'English'), ('Filipino', 'Cebuano'),
         ('Filipino', 'English'), ('Cebuano', 'English')]

def main():
    files = sorted(HERE.glob('[0-9][0-9]_*.pdf'))
    assert len(files) == 8 and len(set(PAIRS)) == 5 and all(a != b for a, b in PAIRS)
    EVIDENCE.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)
    assert not (EVIDENCE / 'results.json').exists(), 'Existing run: inspect it instead of repeating translations.'
    load_engine_environment(ENGINE.parent / '.env')
    secrets = [v for k, v in os.environ.items() if any(s in k for s in ('API_KEY', 'TOKEN', 'SECRET')) and len(v) > 6]
    def sanitize(value):
        if isinstance(value, dict): return {k: sanitize(v) for k, v in value.items()}
        if isinstance(value, list): return [sanitize(v) for v in value]
        if isinstance(value, str):
            for secret in secrets: value = value.replace(secret, '[REDACTED]')
        return value
    def save(path, value): write_json(path, sanitize(value))
    keys = ['TRANSLATION_PROVIDER', 'TRANSLATION_FALLBACK_PROVIDER', 'ANALYSIS_PROVIDER',
            'ANALYSIS_FALLBACK_PROVIDER', 'OLLAMA_CLOUD_MODEL', 'GEMINI_MODEL', 'GEMINI_ANALYSIS_MODEL',
            'TRANSLATION_UNIT_PIPELINE', 'TRANSLATION_ANALYZER_MODE', 'GPTOSS_MAX_ATTEMPTS',
            'GPTOSS_REQUEST_TIMEOUT_SECONDS', 'GPTOSS_TRANSLATION_SLOTS', 'TRANSLATION_CACHE_ENABLED']
    config = {k: os.environ.get(k, '<unset; code default>') for k in keys}
    env = os.environ.copy()
    env.update(TRANSLATION_CACHE_ENABLED='false', MODEL_SERVICE_RELOAD='false', PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    server_url = f'http://127.0.0.1:{port}'
    manifest = {'started_utc': datetime.now(timezone.utc).isoformat(), 'mode': 'balanced',
                'scope': 'Direct current FastAPI document endpoint; no Laravel queue/UI test',
                'configuration': config, 'overrides': {'TRANSLATION_CACHE_ENABLED': 'false', 'MODEL_SERVICE_RELOAD': 'false'},
                'unit_pipeline_default': False, 'interpreter': sys.executable,
                'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'git_status': subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True),
                'engine_py_hashes': {str(p.relative_to(ENGINE)): sha256(p) for p in ENGINE.rglob('*.py') if '__pycache__' not in str(p)},
                'files': [{'file': p.name, 'source': a, 'target': b, 'sha256': sha256(p), 'pages': len(fitz.open(p))} for p, (a, b) in zip(files, PAIRS)]}
    save(EVIDENCE / 'manifest.json', manifest)
    headers = {'X-Service-Token': os.environ.get('PYTHON_SERVICE_TOKEN', os.environ.get('MODEL_SERVICE_TOKEN', ''))}
    results = []
    log_path = EVIDENCE / 'server.log'
    with log_path.open('w', encoding='utf-8') as log:
        proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', str(port)],
                                cwd=ENGINE, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(180):
                if proc.poll() is not None: raise RuntimeError('Test server exited at startup; inspect server.log')
                try:
                    health = requests.get(server_url + '/health', timeout=3)
                    if health.ok:
                        save(EVIDENCE / 'health.json', health.json())
                        break
                except requests.RequestException: pass
                time.sleep(2)
            else: raise RuntimeError('Test server startup exceeded 6 minutes')
            for index, (source, (a, b)) in enumerate(zip(files, PAIRS), 1):
                print(f'START {index}/8 {source.name}: {a} -> {b}', flush=True)
                item = {'id': index, 'file': source.name, 'source': a, 'target': b, 'started_utc': datetime.now(timezone.utc).isoformat()}
                started = time.perf_counter()
                try:
                    with source.open('rb') as stream:
                        response = requests.post(server_url + '/translate/document', headers=headers,
                            data={'source_lang': a, 'target_lang': b, 'mode': 'balanced', 'pdf_column_mode': 'auto'},
                            files={'file': (source.name, stream, 'application/pdf')}, timeout=(10, 7200))
                    item['http_status'] = response.status_code
                    payload = response.json()
                    encoded = payload.pop('file_base64', None)
                    save(EVIDENCE / f'{index:02d}_response.json', payload)
                    if not response.ok or not encoded:
                        raise RuntimeError(str(payload))
                    output = OUTPUT / (source.stem + '_to_' + b + '.pdf')
                    output.write_bytes(base64.b64decode(encoded, validate=True))
                    item.update(status='OUTPUT_CREATED', output=str(output.relative_to(HERE)), output_sha256=sha256(output),
                                structure=pdf_structure(output, manifest['files'][index-1]['pages']),
                                protected_spans=span_checks(source, output), metrics=payload.get('metrics', {}))
                    if index in (3, 7): item['reference_metrics'] = score(output, files[6 if index == 3 else 2])
                    (EVIDENCE / f'{index:02d}_source.txt').write_text(pdf_text(source), encoding='utf-8')
                    (EVIDENCE / f'{index:02d}_output.txt').write_text(pdf_text(output), encoding='utf-8')
                except Exception as error:
                    item.update(status='FAILED', error=sanitize(str(error)))
                item['wall_seconds'] = round(time.perf_counter() - started, 2)
                results.append(item)
                save(EVIDENCE / 'results.json', results)
                print(f"END {index}/8 {item['status']} {item['wall_seconds']}s", flush=True)
                # ponytail: serial batch, no replay; inspect failures before any future rerun.
        finally:
            proc.terminate()
            try: proc.wait(timeout=15)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
    log_path.write_text(sanitize(log_path.read_text(encoding='utf-8', errors='replace')), encoding='utf-8')
    manifest['finished_utc'] = datetime.now(timezone.utc).isoformat()
    manifest['originals_unchanged'] = all(sha256(HERE / r['file']) == r['sha256'] for r in manifest['files'])
    save(EVIDENCE / 'manifest.json', manifest)

if __name__ == '__main__': main()
