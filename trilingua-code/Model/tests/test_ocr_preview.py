"""Explicit unverified preview; synthetic fixtures never qualify strict OCR."""
import base64
import io
import fitz
import pytest
from fastapi import UploadFile
from document import ocr_extractor as ocr
from document.pdf_regions import inventory_pdf
from document.image_reconstructor import image_digest,source_image
from document.render_plan import validate_plan
from document.regenerator import reconstruct_from_sidecar
from .test_hybrid_finish_smoke import synthetic_pdf,inline_fixture_worker


def runtime(monkeypatch):
    monkeypatch.setattr(ocr,'readiness',lambda:{'ready':True,'installed_packs':['eng']})
    monkeypatch.setenv('OCR_ACCEPTANCE_REPORT','MISSING-PREVIEW-TEST-REPORT')


def test_preview_skips_only_report_not_runtime_or_language_checks(monkeypatch):
    runtime(monkeypatch)
    with pytest.raises(ocr.OCRUnavailable,match='95%'):ocr.require_ready('English','scan')
    assert ocr.require_ready('English','scan',preview=True)=='eng'
    with pytest.raises(ocr.OCRUnavailable,match='pack'):ocr.require_ready('Cebuano','scan',preview=True)
    monkeypatch.setattr(ocr,'readiness',lambda:{'ready':False,'installed_packs':['eng']})
    with pytest.raises(ocr.OCRUnavailable,match='runtime'):ocr.require_ready('English','scan',preview=True)


def test_default_strict_holds_and_preview_extracts_without_acceptance(tmp_path,monkeypatch):
    runtime(monkeypatch);source,image,words=synthetic_pdf(tmp_path)
    monkeypatch.setattr(ocr,'recognize_image',lambda *a,**k:[{'type':'paragraph','page':0,'text':'SOURCE',
        'position':words[0]['position'],'ocr':{'words':words,'confidence':99},'style':{}}])
    strict,report=inventory_pdf(source,[],'English')
    assert not strict and report['regions'][0]['reason']=='ocr_acceptance_hold'
    preview,report=inventory_pdf(source,[],'English',ocr_mode='preview')
    assert len(preview)==1 and preview[0]['image_region']
    assert report['ocr_mode']=='preview' and 'Unverified' in report['warnings'][0]


def test_preview_service_replaces_pixels_labels_and_regenerates_without_ocr(tmp_path,document_pipeline,monkeypatch):
    import server
    runtime(monkeypatch);source,image,words=synthetic_pdf(tmp_path)
    monkeypatch.setattr(server,'_document_pipeline',document_pipeline)
    monkeypatch.setattr('document.pdf_worker.run_pdf',inline_fixture_worker)
    monkeypatch.setattr('pipeline.document_pipeline.unit_pipeline_enabled',lambda:False)
    monkeypatch.setattr(ocr,'recognize_image',lambda *a,**k:[{'type':'paragraph','page':0,'text':'SOURCE',
        'position':words[0]['position'],'ocr':{'words':words,'confidence':99},'style':{}}])
    monkeypatch.setattr(document_pipeline.translation_pipeline,'batch_translate_blocks',
        lambda blocks,*a,**k:[dict(b,text='TARGET') for b in blocks])
    result=server.translate_document(UploadFile(filename=source.name,file=io.BytesIO(source.read_bytes())),
                                    'English','Cebuano','auto','fast','preview')
    assert result['content_summary']['translated']==1
    assert result['content_summary']['ocr_mode']=='preview' and result['content_summary']['ocr_verified'] is False
    assert '_ocr_preview_' in result['download_filename']
    plan=result['sidecar']['render_plan'];validate_plan(plan,str(source),result['sidecar']['blocks'])
    assert plan['ocr_mode']=='preview' and plan['ocr_verified'] is False
    output=tmp_path/'output.pdf';output.write_bytes(base64.b64decode(result['file_base64']))
    with fitz.open(output) as doc:
        assert 'TARGET' in doc[0].get_text()
        assert image_digest(source_image(doc,doc[0].get_images()[0][0]))!=image_digest(image)
    def poison(*a,**k):raise AssertionError('Regeneration must not recognize text')
    monkeypatch.setattr(ocr,'recognize_image',poison)
    reconstruct_from_sidecar(result['sidecar'],{0:'EDITED'},str(source),str(tmp_path/'regenerated.pdf'))
    assert result['sidecar']['content_summary']['ocr_verified'] is False
    assert result['sidecar']['render_plan']['ocr_mode']=='preview'


def test_invalid_preview_mode_rejected_before_extraction(tmp_path):
    with pytest.raises(ValueError,match='Invalid OCR mode'):
        inventory_pdf(tmp_path/'nonexistent.pdf',[],'English',ocr_mode='approve')


@pytest.mark.parametrize('overlay',[False,True])
def test_background_before_opaque_image_is_safe_but_overlay_holds(tmp_path,overlay):
    from .test_pdf_image_layout import geometry
    from document.image_reconstructor import occurrence_safety,ImageHold
    image,_=geometry();data=io.BytesIO();image.save(data,'PNG')
    source=tmp_path/'layered.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=600,height=600)
        if not overlay:page.draw_rect(page.rect,fill=(.9,.9,.9),color=None)
        xref=page.insert_image(fitz.Rect(0,150,600,550),stream=data.getvalue())
        if overlay:page.draw_rect(page.rect,fill=(.9,.9,.9),color=None)
        doc.save(source)
    with fitz.open(source) as doc:
        if overlay:
            with pytest.raises(ImageHold,match='Drawing'):occurrence_safety(doc,0,xref)
        else:
            assert occurrence_safety(doc,0,xref)['xref']==xref
