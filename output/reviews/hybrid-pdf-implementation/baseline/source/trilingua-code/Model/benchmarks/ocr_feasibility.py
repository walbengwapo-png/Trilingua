"""Offline OCR spike runner. Never enables application OCR or calls an LLM.

Manifest cases require image, reference, language, pack, input_category,
reference_checked and source_url. Relative file paths resolve from the manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unicodedata
from document.ocr_extractor import inventory


def distance(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for i, expected in enumerate(reference, 1):
        current = [i]
        for j, actual in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (expected != actual)))
        previous = current
    return previous[-1]


def normalize(text):
    # Whitespace and Unicode normalization only. Keep punctuation, case and
    # diacritics: do not improve scores by deleting recognition mistakes.
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip()


def metrics(reference, hypothesis):
    reference, hypothesis = normalize(reference), normalize(hypothesis)
    if not reference:
        raise ValueError('A nonempty checked reference is required')
    words, actual = reference.split(), hypothesis.split()
    word_errors = distance(words, actual)
    char_errors = distance(reference, hypothesis)
    return {'reference_words': len(words), 'word_errors': word_errors,
            'reference_characters': len(reference), 'character_errors': char_errors,
            'wer': word_errors / len(words), 'cer': char_errors / len(reference),
            'word_accuracy_percent': 100 * max(0, 1 - word_errors / len(words))}


def evaluate(manifest_path, binary, minimum):
    import os
    from PIL import Image
    from document.ocr_extractor import recognize_image, SETTINGS, PACKS
    if not 0 < minimum <= 100:
        raise ValueError('Minimum accuracy must be greater than 0 and at most 100')
    manifest_path = Path(manifest_path)
    cases = json.loads(manifest_path.read_text(encoding='utf-8'))['cases']
    if len({case['id'] for case in cases}) != len(cases):
        raise ValueError('OCR case IDs must be unique')
    engine = inventory(binary)
    report = {'minimum_word_accuracy_percent': minimum, 'engine': engine,
              'source_cases': len(cases), 'cases': [], 'categories': {},
              'normalization': 'Unicode NFC and collapsed whitespace only',
              'engine_requests': 0, 'provider_requests': 0, 'settings': SETTINGS}
    for case in cases:
        result = {key: case.get(key) for key in ['id', 'language', 'pack', 'input_category', 'source_url']}
        result['acceptance_eligible'] = bool(
            case.get('representative') and case.get('reference_checked')
            and case.get('reference_reviewer') and case.get('rights_verified')
            and case.get('acquisition') == {'scan': 'real_scan', 'photo': 'real_photo'}.get(case.get('input_category'), '__unsupported__')
            and case.get('pack') == PACKS.get(case.get('language')))
        missing = []
        image = manifest_path.parent / case.get('image', '__missing_image__')
        reference = manifest_path.parent / case.get('reference', '__missing_reference__')
        if not image.is_file(): missing.append('Image not downloaded')
        if not reference.is_file() or not case.get('reference_checked'): missing.append('Checked reference unavailable')
        if not engine['available']: missing.append('OCR engine unavailable')
        elif case.get('pack') not in engine['installed_packs']: missing.append('Required language pack unavailable')
        if missing:
            result.update(status='hold', reasons=missing)
        else:
            try:
                report['engine_requests'] += 1
                # Use the same preprocessing and text assembly as application OCR.
                previous = os.environ.get('OCR_TESSERACT_CMD')
                try:
                    os.environ['OCR_TESSERACT_CMD'] = engine['binary']
                    with Image.open(image) as source:
                        blocks = recognize_image(source, case['pack'])
                finally:
                    if previous is None:
                        os.environ.pop('OCR_TESSERACT_CMD', None)
                    else:
                        os.environ['OCR_TESSERACT_CMD'] = previous
                text = '\n'.join(block['text'] for block in blocks)
                result.update(metrics(reference.read_text(encoding='utf-8'), text))
                result.update(status='measured', ocr_text=text,
                              image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                              reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest())
            except (OSError, ValueError, subprocess.SubprocessError, Image.DecompressionBombError) as exc:
                result.update(status='hold', reasons=[str(exc)])
        report['cases'].append(result)
    for result in report['cases']:
        key = f"{result['language']} / {result['input_category']}"
        group = report['categories'].setdefault(key, {'cases': [], 'decision': 'hold'})
        group['cases'].append(result['id'])
    for group in report['categories'].values():
        entries = [c for c in report['cases'] if c['id'] in group['cases']]
        if all(c['status'] == 'measured' for c in entries):
            total = sum(c['reference_words'] for c in entries)
            accuracy = 100 * max(0, 1 - sum(c['word_errors'] for c in entries) / total)
            group['word_accuracy_percent'] = accuracy
            group['measurement_decision'] = 'go' if accuracy >= minimum else 'no-go'
            group['decision'] = group['measurement_decision'] if all(c['acceptance_eligible'] for c in entries) else 'hold'
    valid_count = 5 <= len(cases) <= 10
    report['sample_count_valid'] = valid_count
    decisions = [group['decision'] for group in report['categories'].values()]
    report['outcome'] = ('go' if decisions and all(x == 'go' for x in decisions) and valid_count
                         else 'no-go' if 'no-go' in decisions and 'hold' not in decisions and valid_count
                         else 'hold')
    report['alternatives_if_no_go'] = ['Evaluate another OCR engine and repeat the spike',
        'Owner restricts supported language/input scope', 'Defer OCR for the failing language/input category']
    return report


def main():
    from config.environment import load_engine_environment
    from document.ocr_extractor import tesseract_command
    load_engine_environment(Path(__file__).resolve().parents[2] / '.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--tesseract', default=tesseract_command())
    parser.add_argument('--minimum-accuracy', type=float, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.manifest, args.tesseract, args.minimum_accuracy)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"OCR spike: {result['outcome']}; {result['engine_requests']} OCR calls; 0 provider requests")


if __name__ == '__main__':
    main()
