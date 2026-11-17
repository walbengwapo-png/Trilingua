"""Guard the evidence/scoring boundary against false completion claims."""
import pytest
from docx import Document

from benchmarks.complete_internal_evaluation import (
    diagnostic_bleu, digest, structural_metrics, verify_hash,
)


def test_hash_validation_distinguishes_missing_and_changed_evidence(tmp_path):
    path = tmp_path / 'artifact.txt'
    assert verify_hash(path, 'anything') == 'MISSING'
    path.write_text('original', encoding='utf-8')
    expected = digest(path)
    assert verify_hash(path, expected) == 'MATCH'
    path.write_text('changed', encoding='utf-8')
    assert verify_hash(path, expected) == 'MISMATCH'


def test_corpus_bleu_is_reproducible_and_never_a_formal_acceptance_rating():
    candidate = ['The pupils read their books every morning.']
    a = diagnostic_bleu(candidate, candidate)
    b = diagnostic_bleu(candidate, candidate)
    assert a == b
    assert a['diagnostic_bleu'] == pytest.approx(100)
    assert 'tok:13a' in a['signature']
    assert a['status'].startswith('DIAGNOSTIC_ONLY')
    with pytest.raises(ValueError):
        diagnostic_bleu([], [])
    with pytest.raises(ValueError):
        diagnostic_bleu(candidate, [])


def test_structural_measurement_detects_removed_table(tmp_path):
    original, damaged = tmp_path / 'original.docx', tmp_path / 'damaged.docx'
    doc = Document()
    doc.add_paragraph('A numbered task', style='List Number')
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = 'Response'
    doc.save(original)
    table._element.getparent().remove(table._element)
    doc.save(damaged)
    before, after = structural_metrics(original), structural_metrics(damaged)
    assert before['tables'] == 1 and after['tables'] == 0
    assert before['cells'] == 4 and after['cells'] == 0
    assert 'overall_score' not in before  # Counts alone never imply visual fidelity.
