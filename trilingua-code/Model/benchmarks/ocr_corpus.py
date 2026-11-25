"""Evidence contract v2. Validation does not create or attest corpus material."""
import hashlib
import math
from pathlib import Path

ACQUISITIONS = {'scan': 'real_scan', 'photo': 'real_photo', 'screenshot': 'real_screenshot'}


def validate(manifest, directory):
    cases = manifest.get('cases', [])
    ids = [c['id'] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError('OCR case IDs must be unique')
    if manifest.get('schema_version') != 2:
        return {c['id']: ['Legacy manifest is diagnostic only; schema v2 required'] for c in cases}
    groups, hashes = {}, {}
    errors = {}
    for c in cases:
        issues = []
        if c.get('split') not in {'calibration', 'heldout'}: issues.append('Invalid split')
        if not c.get('content_group_id') or not c.get('document_id'): issues.append('Missing document/content group')
        for key in ('content_group_id', 'document_id'):
            if c.get(key):
                group = (key, c[key])
                if group in groups and groups[group] != c.get('split'):
                    raise ValueError('Document/content leakage across splits')
                groups[group] = c.get('split')
        if c.get('input_category') not in ACQUISITIONS: issues.append('Unsupported capture class')
        provenance = c.get('provenance') or {}
        if (provenance.get('acquisition') != ACQUISITIONS.get(c.get('input_category'))
                or not provenance.get('source') or not provenance.get('acquired_by')):
            issues.append('Real acquisition provenance unavailable')
        if c.get('reference_check_status') != 'verified' or not c.get('reference_reviewer'):
            issues.append('Independent reference check unavailable')
        elif c['reference_reviewer'] == provenance.get('acquired_by'):
            issues.append('Reference checker must be independent of acquisition')
        if c.get('rights_verified') is not True or c.get('representative') is not True:
            issues.append('Rights/representativeness attestation unavailable')
        for key in ('image', 'reference'):
            path = Path(directory) / c.get(key, '__missing__')
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            if not digest or digest != c.get(key + '_sha256'): issues.append(key + ' hash missing or mismatched')
            if key == 'image' and digest:
                if digest in hashes: raise ValueError('Duplicate image bytes cannot inflate corpus coverage')
                hashes[digest] = c.get('split')
        regions = c.get('regions', [])
        if not regions: issues.append('Expected regions unavailable')
        orders, region_ids = [], []
        for r in regions:
            box = r.get('bbox', [])
            if (len(box) != 4 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in box)
                    or box[2] <= box[0] or box[3] <= box[1] or min(box) < 0):
                issues.append('Invalid expected region geometry')
            if not r.get('text', '').strip() or not r.get('id'): issues.append('Expected region text/id required')
            orders.append(r.get('order'))
            region_ids.append(r.get('id'))
        if (len(set(orders)) != len(orders) or len(set(region_ids)) != len(region_ids)
                or any(not isinstance(x, int) or x < 0 for x in orders)):
            issues.append('Expected region IDs/orders must be unique')
        errors[c['id']] = issues
    return errors


def region_metrics(expected, blocks):
    """Geometry matching is independent from spelling and recognition confidence."""
    from document.pdf_regions import overlap
    candidates = sorted(((overlap(e['bbox'], b['position']), i, j)
                         for i, e in enumerate(expected) for j, b in enumerate(blocks)), reverse=True)
    matched, used = {}, set()
    for score, i, j in candidates:
        if score >= .5 and i not in matched and j not in used:
            matched[i] = j
            used.add(j)
    order = [matched[i] for i in sorted(matched, key=lambda i: expected[i]['order'])]
    pairs = len(order) * (len(order) - 1) // 2
    correct = sum(a < b for n, a in enumerate(order) for b in order[n + 1:])
    return {'region_recall': len(matched) / len(expected) if expected else None,
            'expected_regions': len(expected), 'matched_regions': len(matched),
            'missed_region_ids': [r['id'] for i, r in enumerate(expected) if i not in matched],
            'false_positive_regions': len(blocks) - len(used),
            'reading_order_accuracy': correct / pairs if pairs else None,
            'reading_order_pairs': pairs}
