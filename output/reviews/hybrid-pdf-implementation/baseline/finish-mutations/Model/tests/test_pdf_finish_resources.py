"""Synthetic memory probes and owned process/scratch cleanup, no real scans."""
import os
from pathlib import Path
import time
import tracemalloc
import fitz
import pytest
from document import job_scratch, pdf_worker
from document.image_reconstructor import plan_images, apply_actions
from document.pixel_budget import BUDGET_REASON, DEFAULT_JOB_PIXEL_BUDGET, check_actions
from .test_pdf_image_layout import geometry


def test_many_image_budget_holds_before_decode_and_bounds_peak_memory(tmp_path,monkeypatch):
    import io
    assert DEFAULT_JOB_PIXEL_BUDGET==120_000_000
    monkeypatch.setenv('OCR_JOB_PIXEL_BUDGET',str(600*400*3))
    source=tmp_path/'synthetic-many-images.pdf';blocks=[]
    with fitz.open() as doc:
        for number in range(16):
            image,words=geometry();image.putpixel((599,399),(number,255,255))
            data=io.BytesIO();image.save(data,'PNG')
            page=doc.new_page(width=600,height=400);xref=page.insert_image(page.rect,stream=data.getvalue())
            blocks.append({'page':number,'region_id':str(number),'text':'Fixed target','position':[35,65,350,120],
                'ocr':{'words':words},'image_region':{'xref':xref,'image_bbox':list(page.rect),
                    'estimated_style':{'font_id':'NotoSans-Regular','initial_size':18}}})
        doc.save(source)
    original=fitz.Page.get_image_info
    def guarded(page,*args,**kwargs):
        assert page.number<3 or not kwargs.get('xrefs'), 'Over-budget hash lookup decoded an excluded page'
        return original(page,*args,**kwargs)
    monkeypatch.setattr(fitz.Page,'get_image_info',guarded)
    tracemalloc.start()
    try:
        actions,held=plan_images(source,blocks)
        assert len(actions)==3 and len(held)==13
        assert all(h['reason']==BUDGET_REASON for h in held)
        with fitz.open(source) as doc:
            unchanged={b['image_region']['xref']:doc.xref_stream(b['image_region']['xref']) for b in blocks[3:]}
            apply_actions(doc,actions)
            assert all(doc.xref_stream(x)==raw for x,raw in unchanged.items())
        peak=tracemalloc.get_traced_memory()[1]
    finally:tracemalloc.stop()
    print(f'SYNTHETIC memory probe: 16 x 240000 pixels; 720000-pixel budget; peak={peak} bytes (tracemalloc, excludes MuPDF native heap)')
    assert peak<64_000_000
    with pytest.raises(ValueError,match=BUDGET_REASON):check_actions(actions+[dict(actions[0],page=99)])


def sleeping_scratch_worker(connection,operation,args,scratch):
    pdf_worker._contain_children()
    folder=Path(scratch);(folder/'private-image.tmp').write_bytes(b'synthetic scratch')
    Path(args[0]).write_text('worker reached scratch')
    time.sleep(30)


def test_parent_removes_scratch_after_hard_worker_timeout(tmp_path,monkeypatch):
    root=tmp_path/'scratch';monkeypatch.setenv('OCR_SCRATCH_ROOT',str(root))
    monkeypatch.setattr(pdf_worker,'_execute',sleeping_scratch_worker)
    marker=tmp_path/'started'
    with pytest.raises(TimeoutError):
        pdf_worker.run_pdf('test-owned-worker',str(marker),deadline=time.monotonic()+3)
    assert marker.read_text()=='worker reached scratch'
    assert list(root.iterdir())==[]


def test_stale_sweeper_skips_live_lease_and_unowned_folders(tmp_path,monkeypatch):
    root=tmp_path/'scratch';monkeypatch.setenv('OCR_SCRATCH_ROOT',str(root))
    monkeypatch.setenv('OCR_SCRATCH_MAX_AGE_SECONDS','60')
    with job_scratch.owned_scratch() as active:
        stamp=time.time()-120;os.utime(Path(active)/'lease',(stamp,stamp))
        stale=root/'job-stale';stale.mkdir();(stale/'lease').write_bytes(b'0')
        os.utime(stale/'lease',(stamp,stamp))
        unrelated=root/'unrelated';unrelated.mkdir()
        assert job_scratch.sweep_stale()==['job-stale']
        assert Path(active).exists() and unrelated.exists()
        with pytest.raises(ValueError):job_scratch.remove(tmp_path,root)


def test_failed_lease_creation_cleans_parent_owned_directory(tmp_path,monkeypatch):
    root=tmp_path/'scratch';monkeypatch.setenv('OCR_SCRATCH_ROOT',str(root))
    original=Path.open
    def fail(path,*args,**kwargs):
        if path.name=='lease':raise OSError('Injected disk/open failure')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',fail)
    with pytest.raises(OSError):
        with job_scratch.owned_scratch():pass
    assert list(root.iterdir())==[]


def test_standalone_image_budget_is_checked_before_pdf_conversion(tmp_path,monkeypatch):
    from document.pdf_source import original_pdf
    image,_=geometry();path=tmp_path/'synthetic.png';image.save(path)
    monkeypatch.setenv('OCR_JOB_PIXEL_BUDGET','100000')
    monkeypatch.setattr(fitz.Document,'convert_to_pdf',lambda *a:pytest.fail('Conversion decoded over-budget template'))
    with pytest.raises(ValueError,match=BUDGET_REASON):
        with original_pdf(path):pass
