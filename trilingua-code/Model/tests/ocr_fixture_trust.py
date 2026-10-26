"""Synthetic-only trust harness. Production config cannot install these patches."""
import hashlib
import json
from datetime import date
from PIL import Image


def fixture_report(tmp_path, monkeypatch, categories=('scan',)):
    from document import artifact_auth as auth, report_trust as trust, ocr_extractor as ocr
    from benchmarks import ocr_corpus, ocr_feasibility as evaluator
    state = {'ready': True, 'available': True, 'version': 'SYNTHETIC-TEST-ENGINE',
             'binary_sha256': 'fixture-not-a-real-engine', 'binary': 'fixture',
             'installed_packs': ['eng'], 'pack_sha256': {'eng': 'fixture-not-a-real-pack'}}
    key = tmp_path/'fixture-key.json'
    key.write_text(json.dumps({'version': 1, 'purpose': 'acceptance', 'material': 'test_fixture',
                               'secret': '12'*32}))
    manifest = {'schema_version': 2, 'material': 'test_fixture', 'cases': [],
                'corpus_review': {'reviewers': ['AUTOMATED TEST, NOT A HUMAN REVIEWER'],
                    'reviewer': 'AUTOMATED TEST', 'review_date': date.today().isoformat(),
                    'frozen_at': date.today().isoformat(), 'coverage_reviewed': True,
                    'attestation': 'SYNTHETIC FIXTURE ASSERTION ONLY; NO REAL REFERENCE SIGN-OFF'}}
    for category in categories:
        for split in ('calibration', 'heldout'):
            identity = category+'-'+split
            image = tmp_path/(identity+'.png');reference = tmp_path/(identity+'.txt')
            Image.new('RGB',(300+len(manifest['cases']),300),'white').save(image)
            reference.write_text('Fixed fixture words',encoding='utf-8')
            manifest['cases'].append({'id': identity, 'image': image.name, 'reference': reference.name,
                'language': 'English', 'pack': 'eng', 'input_category': category,
                'split': split, 'content_group_id': identity, 'document_id': identity,
                'provenance': {'acquisition': 'synthetic_geometry', 'source': 'test code'},
                'rights_verified': False, 'representative': False,
                'reference_check_status': 'test_fixture', 'reference_checked': True,
                'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                'reference_sha256': hashlib.sha256(reference.read_bytes()).hexdigest(),
                'regions': [{'id': 'r', 'order': 0, 'bbox': [0,0,100,20], 'text': 'Fixed fixture words'}]})
    path=tmp_path/'fixture-manifest.json';path.write_text(json.dumps(manifest))
    # Explicit test-owned replacements, never a flag, environment mode or runtime branch.
    def fixture_only(*objects):
        assert all(o.get('material') == 'test_fixture' for o in objects)
    monkeypatch.setattr(auth,'production_key',fixture_only)
    monkeypatch.setattr(trust,'real_material',fixture_only)
    monkeypatch.setattr(ocr_corpus,'validate',lambda m,p: {c['id']:[] for c in m['cases']})
    monkeypatch.setattr(evaluator,'inventory',lambda b: state)
    monkeypatch.setattr(ocr,'readiness',lambda: state)
    monkeypatch.setattr(ocr,'recognize_image',lambda *a,**k: [{'text':'Fixed fixture words','position':[0,0,100,20]}])
    report=evaluator.evaluate(path,'fixture',95)
    report=auth.sign(report,key,'acceptance')
    output=tmp_path/'fixture-report.json';output.write_text(json.dumps(report))
    monkeypatch.setenv('OCR_ACCEPTANCE_REPORT',str(output))
    monkeypatch.setenv('OCR_ACCEPTANCE_KEY_FILE',str(key))
    monkeypatch.setenv('OCR_CORPUS_MANIFEST',str(path))
    return report,output,key,path,state
