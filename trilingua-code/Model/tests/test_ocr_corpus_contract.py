"""Contract tests only; no acceptance corpus or passing evidence is generated."""
import json
import pytest

from benchmarks.ocr_corpus import validate, region_metrics
from benchmarks.ocr_feasibility import evaluate


def test_no_upper_case_count_limit_but_missing_evidence_is_still_hold(tmp_path):
    cases = [{'id': str(i), 'language': 'English', 'pack': 'eng',
              'input_category': 'screenshot'} for i in range(25)]
    path = tmp_path/'diagnostic.json'
    path.write_text(json.dumps({'schema_version': 2, 'cases': cases}), encoding='utf-8')
    report = evaluate(path, str(tmp_path/'missing-engine'), 95)
    assert report['source_cases'] == 25
    assert not report['sample_count_valid'] and report['outcome'] == 'hold'
    assert all(not c['acceptance_eligible'] for c in report['cases'])


def test_calibration_is_not_eligible_even_with_diagnostic_perfect_recognition(tmp_path, monkeypatch):
    from PIL import Image
    import document.ocr_extractor as ocr
    import benchmarks.ocr_feasibility as evaluator
    Image.new('RGB', (300, 300), 'white').save(tmp_path/'geometry.png')
    (tmp_path/'reference.txt').write_text('Fixed test words', encoding='utf-8')
    path = tmp_path/'diagnostic.json'
    path.write_text(json.dumps({'schema_version': 2, 'cases': [{
        'id': 'diagnostic-only', 'language': 'English', 'pack': 'eng', 'input_category': 'screenshot',
        'split': 'calibration', 'image': 'geometry.png', 'reference': 'reference.txt',
        'reference_check_status': 'verified', 'representative': False, 'rights_verified': False,
        'regions': [{'id': 'a', 'text': 'Fixed test words', 'bbox': [0, 0, 100, 20], 'order': 0}],
    }]}), encoding='utf-8')
    monkeypatch.setattr(evaluator, 'inventory', lambda b: {'available': True, 'binary': b, 'installed_packs': ['eng']})
    monkeypatch.setattr(ocr, 'recognize_image', lambda *a, **k: [{'text': 'Fixed test words', 'position': [0, 0, 100, 20]}])
    report = evaluate(path, 'mock-diagnostic-engine', 95)
    assert report['cases'][0]['word_accuracy_percent'] == 100
    assert report['cases'][0]['region_recall'] == 1
    assert not report['cases'][0]['acceptance_eligible']
    assert report['categories']['English / screenshot']['decision'] == report['outcome'] == 'hold'


def test_document_and_content_groups_cannot_leak_between_splits(tmp_path):
    cases = [{'id': str(i), 'split': split, 'document_id': 'same', 'content_group_id': 'same'}
             for i, split in enumerate(['calibration', 'heldout'])]
    with pytest.raises(ValueError, match='leakage'):
        validate({'schema_version': 2, 'cases': cases}, tmp_path)


def test_missing_regions_and_wrong_order_are_separate_from_spelling():
    expected = [{'id': str(i), 'order': i, 'bbox': [0, i*100, 90, i*100+20], 'text': 'same'} for i in range(3)]
    blocks = [{'position': expected[i]['bbox'], 'text': 'same'} for i in [1, 0]]
    score = region_metrics(expected, blocks)
    assert score['region_recall'] == 2/3
    assert score['missed_region_ids'] == ['2']
    assert score['reading_order_accuracy'] == 0


def test_hashes_and_independent_reference_attestation_are_required(tmp_path):
    issues = validate({'schema_version': 2, 'cases': [{'id': 'missing', 'split': 'heldout',
        'input_category': 'screenshot', 'document_id': 'a', 'content_group_id': 'a',
        'provenance': {'source': 'test', 'acquired_by': 'same', 'acquisition': 'real_screenshot'},
        'reference_check_status': 'verified', 'reference_reviewer': 'same'}]}, tmp_path)['missing']
    assert 'Reference checker must be independent of acquisition' in issues
    assert 'image hash missing or mismatched' in issues
    assert 'Expected regions unavailable' in issues
