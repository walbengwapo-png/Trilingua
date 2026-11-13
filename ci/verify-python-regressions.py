"""Reject new Python regressions; compare three unchanged PDF failures to production."""
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
app = root / 'trilingua-code'
baseline = root / 'baseline-verification/trilingua-code'
nodes = [
    'test_pdf_instruction_identity.py::test_pdf_brand_column_retains_structure_and_preserves_name',
    'test_regression.py::test_overflow_continuation_stops_at_occupied_row',
    'test_regression.py::test_run_level_emission_no_midword_splits',
]

def failures(path):
    return {c.get('classname').split('.tests.')[-1] + '::' + c.get('name')
            for c in ET.parse(path).iter('testcase')
            if c.find('failure') is not None or c.find('error') is not None}

result = subprocess.run([sys.executable, '-m', 'pytest', 'Model/tests', '-q', '--tb=short',
    '--show-capture=no', '--junitxml=native-python-results.xml', '-p', 'no:cacheprovider', '--maxfail=20'], cwd=app)
if result.returncode == 0:
    sys.exit(0)
if result.returncode != 1:
    sys.exit(result.returncode)
expected = {n.replace('.py::', '::') for n in nodes}
release_failed = failures(app / 'native-python-results.xml')
if release_failed != expected:
    print('Unexpected release failures:', sorted(release_failed - expected), flush=True)
    sys.exit(1)
# Only accept established failures with byte-identical production renderers/tests.
for directory in ['Model/document', 'Model/validators/translation_validator.py']:
    source = app / directory
    files = source.rglob('*.py') if source.is_dir() else [source]
    for file in files:
        if file.read_bytes() != (baseline / file.relative_to(app)).read_bytes():
            raise RuntimeError('Baseline renderer comparison is invalid: ' + str(file))
for node in nodes:
    name = 'Model/tests/' + node.split('::')[0]
    assert (app / name).read_bytes() == (baseline / name).read_bytes(), name
env = os.environ.copy()
env['PYTHONPATH'] = str(baseline / 'Model')
report = app / 'native-python-baseline-results.xml'
prior = subprocess.run([sys.executable, '-m', 'pytest', *['Model/tests/' + n for n in nodes],
    '-q', '--tb=short', '--show-capture=no', '--junitxml=' + str(report), '-p', 'no:cacheprovider'],
    cwd=baseline, env=env)
if prior.returncode != 1 or failures(report) != release_failed:
    raise RuntimeError('A release failure was not reproduced on the production baseline')
print('No new Python regressions. Three existing PDF failures reproduced on identical production source.', flush=True)
