"""HMAC/score contract tests on explicitly non-production synthetic material."""
import json
import pytest
from tests.ocr_fixture_trust import fixture_report
from document import artifact_auth as auth, report_trust as trust, ocr_extractor as ocr


def test_signed_fixture_validates_only_inside_test_owned_harness(tmp_path,monkeypatch):
    report,path,key,manifest,state=fixture_report(tmp_path,monkeypatch)
    assert ocr.require_ready('English','scan')=='eng'
    with monkeypatch.context() as isolated:
        isolated.setattr(auth,'production_key',lambda key: (_ for _ in ()).throw(ValueError('Fixture keys rejected')))
        with pytest.raises(ocr.OCRUnavailable): ocr.require_ready('English','scan')
    assert trust.verify_report(report,key,manifest,state,'English','scan')['English / scan']==100


@pytest.mark.parametrize('fault',['body','wrong_key','reviewer','calibration','fixture','manifest','score','engine','signature'])
def test_invalid_signed_reports_fail_closed(tmp_path,monkeypatch,fault):
    report,path,key,manifest,state=fixture_report(tmp_path,monkeypatch)
    if fault=='body':report['engine']['version']='tampered'
    if fault=='wrong_key':
        data=json.loads(key.read_text());data['secret']='34'*32;key.write_text(json.dumps(data))
    if fault=='reviewer':report['corpus_review']['reviewers']=[]
    if fault=='calibration':report['cases'][-1]['split']='calibration'
    if fault=='fixture':
        # Restore the real production material policy, without changing any configuration.
        monkeypatch.setattr(trust,'real_material',lambda *a: (_ for _ in ()).throw(ValueError('fixture rejected')))
    if fault=='manifest':report['source_manifest_sha256']='bad'
    if fault=='score':
        report['cases'][-1].update(ocr_text='Wrong',word_errors=3,word_accuracy_percent=0)
        report['categories']['English / scan']['word_accuracy_percent']=0
    if fault=='engine':state={**state,'binary_sha256':'different'};monkeypatch.setattr(ocr,'readiness',lambda:state)
    if fault=='signature':report.pop('signature')
    if fault in {'reviewer','calibration','manifest','score'}:
        report=auth.sign(report,key,'acceptance')
    path.write_text(json.dumps(report))
    with pytest.raises(ocr.OCRUnavailable,match='on hold'):ocr.require_ready('English','scan')


def test_production_rejects_fixture_key_and_fixture_material_without_config_switch(tmp_path):
    key=tmp_path/'key.json';key.write_text(json.dumps({'version':1,'purpose':'acceptance','material':'test_fixture','secret':'12'*32}))
    with pytest.raises(ValueError,match='Fixture keys'):auth.sign({},key,'acceptance')
    with pytest.raises(ValueError,match='fixture'):trust.real_material({'material':'test_fixture'},{'material':'test_fixture'})


def test_key_creation_refuses_overwrite_and_repo_paths(tmp_path):
    key=tmp_path/'key.json';auth.generate_key(key,'acceptance')
    assert auth.key_file(key,'acceptance')[0]['material']=='production'
    with pytest.raises(FileExistsError):auth.generate_key(key,'acceptance')
    with pytest.raises(ValueError,match='outside'):auth.generate_key(auth.REPOSITORY/'forbidden.key','acceptance')
    with pytest.raises(ValueError,match='purpose'):auth.key_file(key,'render-plan')
