"""Evaluator-issued report verification; no environment switch admits fixtures."""
from datetime import date
import hashlib
from pathlib import Path

from document.artifact_auth import load_json, verify


def real_material(report, manifest):
    if report.get('material') != 'real' or manifest.get('material') != 'real':
        raise ValueError('Diagnostic, legacy and fixture material cannot grant acceptance')


def validate_report(report, manifest_path):
    from benchmarks.ocr_corpus import validate
    from benchmarks.ocr_feasibility import metrics, normalize
    manifest_path = Path(manifest_path)
    manifest = load_json(manifest_path)
    real_material(report, manifest)
    if (report.get('issuer') != 'trilingua-evaluator-v1' or report.get('schema_version') != 2
            or manifest.get('schema_version') != 2):
        raise ValueError('Evaluator schema/issuer required')
    if report.get('source_manifest_sha256') != hashlib.sha256(manifest_path.read_bytes()).hexdigest():
        raise ValueError('Corpus manifest hash mismatch')
    review = manifest.get('corpus_review') or {}
    reviewers = review.get('reviewers')
    if (not isinstance(reviewers, list) or not reviewers or not all(str(x).strip() for x in reviewers)
            or not str(review.get('attestation', '')).strip() or review.get('coverage_reviewed') is not True
            or report.get('corpus_review') != review):
        raise ValueError('Reviewer attestation missing or mismatched')
    if date.fromisoformat(review.get('review_date', '')) > date.today():
        raise ValueError('Review date cannot be in the future')
    issues = validate(manifest, manifest_path.parent)
    if not issues or any(issues.values()):
        raise ValueError('Corpus contract/provenance invalid')
    source = {c['id']: c for c in manifest['cases']}
    measured = {c['id']: c for c in report['cases']}
    if len(measured) != len(report['cases']) or source.keys() != measured.keys():
        raise ValueError('Report case coverage mismatch')
    if {c['split'] for c in source.values()} != {'calibration', 'heldout'}:
        raise ValueError('Disjoint calibration and held-out material required')
    for identity, sample in source.items():
        result = measured[identity]
        for field in ('split', 'language', 'pack', 'input_category', 'content_group_id', 'image_sha256', 'reference_sha256'):
            if result.get(field) != sample.get(field):
                raise ValueError('Report case provenance mismatch')
        reference = (manifest_path.parent / sample['reference']).read_text(encoding='utf-8')
        ordered = '\n'.join(r['text'] for r in sorted(sample['regions'], key=lambda r: r['order']))
        if normalize(reference) != normalize(ordered):
            raise ValueError('Checked regions do not cover the full reference')
        if result.get('status') != 'measured' or result.get('contract_errors'):
            raise ValueError('Every frozen corpus case must be measured without contract errors')
        score = metrics(reference, result['ocr_text'])
        if any(result.get(k) != score[k] for k in ('reference_words', 'word_errors', 'word_accuracy_percent')):
            raise ValueError('Per-case score is not reproducible')
    return manifest, measured


def verify_report(report, key_path, manifest_path, state=None, language=None, category=None):
    from document.ocr_extractor import SETTINGS, PACKS
    verify(report, key_path, 'acceptance')
    manifest, measured = validate_report(report, manifest_path)
    if report.get('settings') != SETTINGS or report.get('minimum_word_accuracy_percent', 0) < 95:
        raise ValueError('OCR settings/95% threshold mismatch')
    engine = report['engine']
    if not engine.get('binary_sha256') or not engine.get('version'):
        raise ValueError('Engine fingerprints missing')
    if state is not None:
        pack = PACKS.get(language)
        if (engine['version'] != state.get('version') or engine['binary_sha256'] != state.get('binary_sha256')
                or not state.get('pack_sha256', {}).get(pack)
                or engine.get('pack_sha256', {}).get(pack) != state['pack_sha256'][pack]):
            raise ValueError('Engine/pack fingerprint mismatch')
    scopes = {f"{c['language']} / {c['input_category']}" for c in manifest['cases']}
    if set(report.get('categories', {})) != scopes:
        raise ValueError('Scope coverage mismatch')
    scores = {}
    for scope in scopes:
        cases = [c for c in manifest['cases'] if f"{c['language']} / {c['input_category']}" == scope]
        heldout = [measured[c['id']] for c in cases if c['split'] == 'heldout']
        if not heldout or not any(c['split'] == 'calibration' for c in cases):
            raise ValueError('Every scope requires separate calibration and held-out cases')
        if any(c.get('pack') != PACKS.get(c['language']) or not c.get('acceptance_eligible') for c in heldout):
            raise ValueError('Held-out-only eligibility/pack mismatch')
        words = sum(c['reference_words'] for c in heldout)
        scores[scope] = 100 * max(0, 1 - sum(c['word_errors'] for c in heldout) / words)
        group = report['categories'][scope]
        if (set(group['cases']) != {c['id'] for c in heldout}
                or len(group['cases']) != len(heldout) or group['word_accuracy_percent'] != scores[scope]):
            raise ValueError('Recomputed per-scope score mismatch')
    if language is not None:
        scope = f'{language} / {category}'
        if scores.get(scope, 0) < max(95, report['minimum_word_accuracy_percent']) or report['categories'][scope]['decision'] != 'go':
            raise ValueError('Scope is below 95% or not accepted')
    return scores

