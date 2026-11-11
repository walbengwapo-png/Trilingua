"""Workflow plumbing with synthetic fixtures; never actual review/acceptance evidence."""
import csv
import json
from unittest.mock import Mock
import pytest
from tools.ocr_kit import workflow
from tools.ocr_kit.corpus import reference_sheet, ingest_checks, current, save
from .test_ocr_kit import sample
from .test_pdf_image_layout import geometry, document


def test_prepare_is_unreviewed_calibration_and_does_not_overwrite(tmp_path,monkeypatch):
    image,words=geometry();source=tmp_path/'fixture.png';image.save(source)
    original=source.read_bytes()
    monkeypatch.setattr(workflow,'recognize_image',lambda *a,**k:[{'text':'SOURCE & <script>',
                        'position':words[0]['position']}])
    output=tmp_path/'review'
    result=workflow.prepare_review(source,output,'English')
    assert result['stage']=='needs_source_metadata' and not result['acceptance_ready']
    provenance=json.loads((output/'draft-provenance.json').read_text())
    assert provenance['acceptance_eligible'] is False and provenance['pages']==1
    assert json.loads((output/'corpus-review.json').read_text())=={
        'reviewers':[],'review_date':'','attestation':'','coverage_reviewed':False}
    rows=list(csv.DictReader((output/'incoming/info.csv').open()))
    assert rows[0]['split']=='calibration' and rows[0]['author']==rows[0]['rights_note']==rows[0]['capture_class']==''
    assert '&lt;script&gt;' in (output/'review.html').read_text() and '<script>' not in (output/'review.html').read_text()
    assert 'advance --workspace' in (output/'START_HERE.md').read_text()
    assert source.read_bytes()==original and not (output/'second-review.csv').exists()
    with pytest.raises(FileExistsError):workflow.prepare_review(source,output,'English')
    assert (output/'incoming/fixture.txt').read_text().strip()=='SOURCE & <script>'


def workspace(tmp_path):
    incoming=tmp_path/'incoming';incoming.mkdir()
    saved=sample(incoming)
    save(tmp_path/'workflow.json',{'version':1,'language':'English',
         'calibration_source_sha256':saved['samples'][0]['image_sha256']})
    save(tmp_path/'corpus-review.json',{'reviewers':[],'coverage_reviewed':False})
    return saved


def test_advance_stops_at_blank_review_without_scoring_or_signing(tmp_path,monkeypatch):
    workspace(tmp_path)
    poison=Mock(side_effect=AssertionError('No evaluation without human material'))
    monkeypatch.setattr(workflow,'evaluate',poison);monkeypatch.setattr(workflow,'sign',poison)
    result=workflow.advance(tmp_path)
    assert result['stage']=='needs_independent_review' and len(result['missing_splits'])==3
    rows=list(csv.DictReader((tmp_path/'second-review.csv').open()))
    assert rows[0]['reviewer']==rows[0]['decision']=='' and rows[0]['regions_sha256']
    assert workflow.advance(tmp_path)['stage']=='needs_independent_review'
    assert not poison.called


def test_prepared_source_cannot_be_relabelled_as_unseen(tmp_path):
    workspace(tmp_path)
    info=tmp_path/'incoming/info.csv'
    info.write_text(info.read_text().replace('calibration','heldout'))
    result=workflow.advance(tmp_path)
    assert result['stage']=='needs_samples' and 'calibration' in result['blockers'][0]


def test_prepare_reserves_source_and_raster_pixels_before_rendering(tmp_path,monkeypatch):
    image,_=geometry();source=document(tmp_path,image)
    monkeypatch.setenv('OCR_JOB_PIXEL_BUDGET','4300000')
    poison=Mock(side_effect=AssertionError('No rendering before budget admission'))
    monkeypatch.setattr(workflow,'pages',poison)
    with pytest.raises(ValueError,match='pixel budget'):workflow.prepare_review(source,tmp_path/'review','English')
    assert not poison.called and not (tmp_path/'review').exists()


def test_region_edits_invalidate_review_binding(tmp_path):
    saved=sample(tmp_path);sheet=tmp_path/'review.csv'
    reference_sheet(saved,sheet)
    regions=tmp_path/'fixture.regions.json'
    original=regions.read_text();regions.write_text(original.replace('40','41'))
    with pytest.raises(ValueError,match='changed'):current(saved)
    fresh=workflow.intake(tmp_path)
    with pytest.raises(ValueError,match='hash mismatch'):ingest_checks(fresh,sheet,tmp_path/'checks.json')


@pytest.mark.parametrize('outcome,key,expected',[
    ('hold',True,'evaluation_hold'),('no-go',True,'evaluation_hold'),
    ('contract-error',True,'evaluation_hold'),('verify-error',True,'evaluation_hold'),
    ('go',False,'needs_signing_key'),('go',True,'report_verified')])
def test_resume_uses_existing_validation_before_signing(tmp_path,monkeypatch,outcome,key,expected):
    """Fake dependencies test stage order only; emit no real acceptance material."""
    saved=workspace(tmp_path)
    # Explicitly mocked review/coverage, never a corpus created from attestations.
    fresh=dict(saved,samples=[dict(saved['samples'][0],capture_class=category,split=split,
                 image_sha256=category+split) for category in ['scan','photo','screenshot'] for split in ['calibration','heldout']])
    monkeypatch.setattr(workflow,'intake',lambda *a:fresh)
    monkeypatch.setattr(workflow,'current',lambda *a:fresh)
    monkeypatch.setattr(workflow,'ingest_checks',lambda *a:{'checks':[]})
    save(tmp_path/'intake.json',fresh);(tmp_path/'second-review.csv').write_text('MOCK DEPENDENCY ONLY')
    save(tmp_path/'corpus-review.json',{'reviewers':['AUTOMATED FIXTURE'],
        'review_date':'2026-01-01','attestation':'MOCK INPUT, NOT REVIEW','coverage_reviewed':True})
    calls=[]
    def build(*args):calls.append('build')
    def validate(*args):
        calls.append('validate')
        if outcome=='contract-error':raise ValueError('TEST contract rejection')
    def sign(*args):calls.append('sign');return {'fixture_marker':True}
    def verify(*args):
        calls.append('verify')
        if outcome=='verify-error':raise ValueError('TEST signature rejection')
    monkeypatch.setattr(workflow,'build_manifest',build)
    monkeypatch.setattr(workflow,'evaluate',lambda *a:{'outcome':outcome if outcome in {'hold','no-go'} else 'go',
                           'categories':{'English / scan':{'word_accuracy_percent':99}}})
    monkeypatch.setattr(workflow,'validate_report',validate)
    monkeypatch.setattr(workflow,'sign',sign);monkeypatch.setattr(workflow,'verify_report',verify)
    monkeypatch.setattr(workflow,'readiness',lambda:{})
    result=workflow.advance(tmp_path,'NONEXISTENT MOCK KEY' if key else None)
    assert result['stage']==expected and result['live_configuration_changed'] is False
    assert result['acceptance_ready'] is (expected=='report_verified')
    expected_calls=(['build'] if outcome in {'hold','no-go'} else ['build','validate']
                    if outcome=='contract-error' or not key else ['build','validate','sign','verify'])
    assert calls==expected_calls
    assert bool(list((tmp_path/'runs').glob('*/signed-report.json'))) is (expected=='report_verified')
