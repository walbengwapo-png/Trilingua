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
import shutil
import subprocess
import unicodedata


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


def inventory(binary):
    resolved = shutil.which(binary) or (str(Path(binary).resolve()) if Path(binary).is_file() else None)
    if not resolved:
        return {'available': False, 'binary': None, 'installed_packs': None,
                'reason': 'Tesseract executable was not found at the supplied path or on PATH'}
    try:
        version = subprocess.run([resolved, '--version'], capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=15, check=True)
        languages = subprocess.run([resolved, '--list-langs'], capture_output=True, text=True,
                                   encoding='utf-8', errors='replace', timeout=15, check=True)
        output = languages.stdout + languages.stderr
        packs = [line.strip() for line in output.splitlines()
                 if re.fullmatch(r'[A-Za-z0-9_/]+', line.strip())]
        data = {'available': True, 'binary': resolved, 'version': version.stdout.splitlines()[0],
                'installed_packs': packs, 'list_languages_output': output}
        match = re.search(r'"([^"]+)"', output)
        data['pack_sha256'] = {}
        if match:
            for pack in packs:
                path = Path(match[1]) / (pack + '.traineddata')
                if path.is_file(): data['pack_sha256'][pack] = hashlib.sha256(path.read_bytes()).hexdigest()
        return data
    except (OSError, subprocess.SubprocessError) as exc:
        return {'available': False, 'binary': resolved, 'installed_packs': None, 'reason': str(exc)}


def evaluate(manifest_path, binary, minimum):
    if not 0 < minimum <= 100:
        raise ValueError('Minimum accuracy must be greater than 0 and at most 100')
    manifest_path = Path(manifest_path)
    cases = json.loads(manifest_path.read_text(encoding='utf-8'))['cases']
    engine = inventory(binary)
    report = {'minimum_word_accuracy_percent': minimum, 'engine': engine,
              'source_cases': len(cases), 'cases': [], 'categories': {},
              'normalization': 'Unicode NFC and collapsed whitespace only',
              'engine_requests': 0, 'provider_requests': 0}
    for case in cases:
        result = {key: case.get(key) for key in ['id', 'language', 'pack', 'input_category', 'source_url']}
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
                completed = subprocess.run([engine['binary'], str(image), 'stdout', '-l', case['pack'],
                                            '--psm', '3'], capture_output=True, text=True,
                                           encoding='utf-8', errors='replace', timeout=120, check=True)
                result.update(metrics(reference.read_text(encoding='utf-8'), completed.stdout))
                result.update(status='measured', ocr_text=completed.stdout)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
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
            group['decision'] = 'go' if accuracy >= minimum else 'no-go'
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--tesseract', default='tesseract')
    parser.add_argument('--minimum-accuracy', type=float, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.manifest, args.tesseract, args.minimum_accuracy)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"OCR spike: {result['outcome']}; {result['engine_requests']} OCR calls; 0 provider requests")


if __name__ == '__main__':
    main()
