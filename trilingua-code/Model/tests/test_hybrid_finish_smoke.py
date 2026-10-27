"""Upload-equivalent service smoke. Synthetic geometry; no real OCR evidence."""
import base64
import io
import json
import shutil
from unittest.mock import Mock
import fitz
import pytest
from fastapi import UploadFile
from document import ocr_extractor as ocr
from document.pdf_regions import inventory_pdf
from document.extractor import analyze_document
from document.image_reconstructor import plan_images,image_digest,source_image
from document.reconstructor import write_pdf_preserved
from tests.ocr_fixture_trust import fixture_report
from .test_pdf_image_layout import geometry


def synthetic_pdf(tmp_path,caption=False):
    image,words=geometry();data=io.BytesIO();image.save(data,'PNG')
    source=tmp_path/'synthetic.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=600,height=600)
        page.insert_image(fitz.Rect(0,150,600,550),stream=data.getvalue())
        if caption:page.insert_text((40,70),'This is a native caption with selectable source words.',fontsize=14)
        doc.save(source)
    return source,image,words


def invoke(source,pipeline,monkeypatch):
    import server
    monkeypatch.setattr(server,'_document_pipeline',pipeline)
    return server.translate_document(UploadFile(filename=source.name,file=io.BytesIO(source.read_bytes())),
        'English','Cebuano','auto','fast','strict')


@pytest.mark.parametrize('caption',[False,True])
def test_no_report_keeps_raster_original_through_service(tmp_path,document_pipeline,monkeypatch,caption):
    source,image,words=synthetic_pdf(tmp_path,caption)
    monkeypatch.setenv('OCR_ACCEPTANCE_REPORT',str(tmp_path/'no-report.json'))
    poison=Mock(side_effect=AssertionError('Held recognition cannot run'))
    monkeypatch.setattr(ocr,'recognize_image',poison)
    result=invoke(source,document_pipeline,monkeypatch)
    summary=result['content_summary']
    assert summary['held']>=1 and summary['status']==('partial' if caption else 'untranslated')
    if not caption:assert summary['translated']==0
    assert all(r['status']!='translated' for r in result['sidecar']['render_plan']['regions'] if r['source_kind'].startswith('raster'))
    output=tmp_path/'returned.pdf';output.write_bytes(base64.b64decode(result['file_base64']))
    with fitz.open(output) as doc:
        assert image_digest(source_image(doc,doc[0].get_images()[0][0]))==image_digest(image)
    assert summary['status'] in result['download_filename']
    assert result['sidecar']['extraction']['warnings'] and not poison.called


def inline_fixture_worker(operation,*args,deadline=None):
    """Test-owned in-process dependency: fixture trust patches cannot enter spawn."""
    if operation in {'inspect','extract'}:
        source,language,column=args[:3]
        native,ext=analyze_document(source,pdf_column_mode=column)
        return (native,ext) if operation=='inspect' else inventory_pdf(source,native,language,column,
                                                                    ocr_mode=args[3] if len(args)>3 else 'strict')
    if operation=='render':
        source,blocks,output,language,target=args
        actions,held=plan_images(source,blocks)
        native=[b for b in blocks if not b.get('image_region')]
        report=write_pdf_preserved(native,source,output,source_lang=language,target_lang=target,strict=True,image_actions=actions)
        report['held'].extend(held)
        return report,actions,native
    if operation=='preserve':shutil.copyfile(args[0],args[1]);return args[1]
    raise AssertionError(operation)


def test_signed_fixture_exercises_service_replacement_and_tamper_holds(tmp_path,document_pipeline,monkeypatch):
    report,report_path,key,manifest,state=fixture_report(tmp_path,monkeypatch,('scan','photo','screenshot'))
    source,image,words=synthetic_pdf(tmp_path)
    monkeypatch.setattr('document.pdf_worker.run_pdf',inline_fixture_worker)
    monkeypatch.setattr('pipeline.document_pipeline.unit_pipeline_enabled',lambda:False)
    monkeypatch.setattr(ocr,'recognize_image',lambda *a,**k:[{'type':'paragraph','page':0,'text':'SOURCE',
        'position':words[0]['position'],'ocr':{'words':words,'confidence':99},'style':{}}])
    monkeypatch.setattr(document_pipeline.translation_pipeline,'batch_translate_blocks',
        lambda blocks,*a,**k:[dict(b,text='TARGET') for b in blocks])
    result=invoke(source,document_pipeline,monkeypatch)
    assert result['content_summary']['translated']==1 and result['content_summary']['held']==0
    output=tmp_path/'translated.pdf';output.write_bytes(base64.b64decode(result['file_base64']))
    with fitz.open(output) as doc:
        assert 'TARGET' in doc[0].get_text()
        assert image_digest(source_image(doc,doc[0].get_images()[0][0]))!=image_digest(image)
    report['corpus_review']['attestation']+=' tampered';report_path.write_text(json.dumps(report))
    assert invoke(source,document_pipeline,monkeypatch)['content_summary']['translated']==0
