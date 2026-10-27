"""Synthetic fixtures only; no real acquisition, sign-off or acceptance output."""
import csv
import json
from pathlib import Path
import pytest
from tools.ocr_kit.corpus import intake,reference_sheet,ingest_checks,build_manifest,checked_page_regions
from tools.ocr_kit.feasibility import feasibility,band,preprocess,transformed
from .test_pdf_image_layout import geometry


def sample(tmp_path):
    image,words=geometry();image.save(tmp_path/'fixture.png')
    (tmp_path/'fixture.txt').write_text('SOURCE',encoding='utf-8')
    (tmp_path/'fixture.regions.json').write_text(json.dumps([{'id':'r','page':0,'order':0,'bbox':words[0]['position'],'text':'SOURCE'}]))
    with (tmp_path/'info.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=['file','language','capture_class','content_group_id','split','author','rights_note','material'])
        writer.writeheader();writer.writerow({'file':'fixture.png','language':'English','capture_class':'screenshot',
            'content_group_id':'synthetic-only','split':'calibration','author':'TEST CREATOR',
            'rights_note':'SYNTHETIC UNIT FIXTURE, NOT REAL ACQUISITION','material':'test_fixture'})
    return intake(tmp_path)


def test_intake_hashes_and_group_split_leakage(tmp_path):
    saved=sample(tmp_path)
    assert not saved['gaps'] and len(saved['samples'][0]['image_sha256'])==64
    with (tmp_path/'info.csv').open('a',encoding='utf-8') as stream:
        stream.write('fixture.png,English,screenshot,synthetic-only,heldout,TEST,fixture,test_fixture\n')
    with pytest.raises(ValueError):intake(tmp_path)


def test_blank_second_review_sheet_and_unchanged_source_binding(tmp_path):
    saved=sample(tmp_path);sheet=tmp_path/'review.csv';reference_sheet(saved,sheet)
    rows=list(csv.DictReader(sheet.open(encoding='utf-8')))
    assert rows[0]['reviewer']==rows[0]['decision']==''
    with pytest.raises(ValueError):ingest_checks(saved,sheet,tmp_path/'checks.json')
    rows[0].update(reviewer='AUTOMATED TEST, NOT HUMAN REVIEW',decision='corrected',corrected_text='SOURCE',
        review_date='2026-01-01',attestation='AUTOMATED FIXTURE ASSERTION ONLY',
        rights_verified='false',representative='false',real_capture_confirmed='false')
    with sheet.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    checked=ingest_checks(saved,sheet,tmp_path/'checks.json')
    assert Path(checked['checks'][0]['checked_reference']).read_text()=='SOURCE'
    approval={'coverage_reviewed':True,'reviewers':[rows[0]['reviewer']],
              'review_date':'2026-01-01','attestation':'TEST ONLY'}
    with pytest.raises(ValueError,match='Fixtures'):build_manifest(saved,checked,approval,tmp_path/'forbidden-corpus')
    assert not (tmp_path/'forbidden-corpus').exists()
    checked['checks'][0]['decision']=''
    with pytest.raises(ValueError,match='Incomplete'):build_manifest(saved,checked,approval,tmp_path/'forbidden-corpus')
    (tmp_path/'fixture.txt').write_text('changed')
    with pytest.raises(ValueError,match='changed'):ingest_checks(saved,sheet,tmp_path/'other.json')


def test_feasibility_scores_without_issuing_acceptance_or_inventing_geometry(tmp_path,monkeypatch):
    import tools.ocr_kit.feasibility as experiments
    saved=sample(tmp_path)
    monkeypatch.setattr(experiments,'recognize_image',lambda *a,**k:[{'text':'SOURCE','position':[40,70,140,95]}])
    report=feasibility(saved)
    assert report['material']=='diagnostic' and 'signature' not in report and 'categories' not in report
    assert report['samples'][0]['word_accuracy_percent']==100
    (tmp_path/'fixture.regions.json').unlink()
    report=feasibility(intake(tmp_path))
    assert report['samples'][0]['layout_metrics_reason']
    assert next(iter(report['slices'].values()))['region_recall'] is None
    assert [band(x) for x in (95,90,84)]==['>=95 reachable','85-95 try preprocessing','<85 engine problem']


def test_variant_geometry_uses_the_same_scale_as_raster(tmp_path):
    image,words=geometry();processed,matrix=preprocess(image,400,binarize=True)
    box=words[0]['position'];result=transformed([{'bbox':box}],matrix)[0]['bbox']
    assert result==pytest.approx([v*4/3 for v in box])
    assert processed.mode=='L'


def test_checked_geometry_cannot_escape_source_or_invent_missing_pages():
    regions=[{'page':0,'bbox':[1,2,20,30]}]
    assert checked_page_regions(regions,0,(600,400))==regions
    with pytest.raises(ValueError):checked_page_regions(regions,1,(600,400))
    for box in ([0,0,601,400],[20,2,1,30],[0,0,float('nan'),30]):
        with pytest.raises(ValueError):checked_page_regions([{'bbox':box}],0,(600,400))
