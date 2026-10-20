"""Spike scoring must not turn missing evidence into a pass."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.ocr_feasibility import evaluate, metrics


def test_word_error_and_character_error_are_measured_against_reference():
    score = metrics('read the lesson', 'read this lesson')
    assert score['reference_words'] == 3
    assert score['word_errors'] == 1
    assert 66 < score['word_accuracy_percent'] < 67
    assert score['character_errors'] == 2


def test_whitespace_normalization_preserves_diacritic_errors():
    assert metrics('maó\n  kini', 'maó kini')['word_accuracy_percent'] == 100
    assert metrics('maó kini', 'mao kini')['word_accuracy_percent'] == 50


def test_missing_engine_and_references_remain_hold(tmp_path):
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'cases': [{'id': str(i), 'language': 'Cebuano',
        'pack': 'ceb', 'input_category': 'scan'} for i in range(6)]}))
    report = evaluate(manifest, str(tmp_path/'missing-tesseract'), 95)
    assert report['outcome'] == 'hold'
    assert report['engine_requests'] == 0
    assert report['categories']['Cebuano / scan']['decision'] == 'hold'
    assert 'word_accuracy_percent' not in report['cases'][0]
