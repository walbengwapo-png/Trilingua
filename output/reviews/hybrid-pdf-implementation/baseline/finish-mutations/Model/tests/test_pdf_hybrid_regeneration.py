"""Frozen geometry tests. No OCR acceptance evidence and no provider calls."""
import json
import shutil
import time
from unittest.mock import Mock

import fitz
import pytest

from document.image_reconstructor import FONT_ROOT, ImageHold
from document.pdf_regions import sha256
from document.regenerator import reconstruct_from_sidecar, rich_block_entry
from document.render_plan import make_plan
from document.pdf_worker import job_budget, run_pdf
from .test_pdf_image_layout import geometry, document, action_for


@pytest.fixture
def frozen(tmp_path):
    image,words=geometry();source=document(tmp_path,image)
    action=action_for(image,words)
    with fitz.open(source) as doc: action.update(page=0,xref=doc[0].get_images()[0][0],region_id='fixed')
    block=rich_block_entry(0,{'text':action['fit']['text'],'region_id':'fixed','page':0,
        'position':action['fit']['bbox'],'image_region':{'xref':action['xref']},'ocr':{'words':words}},'SOURCE')
    extraction={'original_sha256':sha256(source),'regions':[{'region_id':'fixed','status':'translated','page':0}],
                'pages':[{'page':0}],'image_actions':[action]}
    sidecar={'version':3,'format':'.pdf','blocks':[block], 'render_plan':make_plan(extraction,[block]),
             'content_summary':{'status':'complete','translated':1,'held':0,'passthrough':0}}
    return source,json.loads(json.dumps(sidecar))


def test_persisted_masks_reconstruct_edited_text_with_zero_ocr_or_provider_calls(tmp_path,frozen,monkeypatch):
    import document.ocr_extractor as ocr
    poison=Mock(side_effect=AssertionError('Regeneration cannot OCR'))
    monkeypatch.setattr(ocr,'recognize_image',poison)
    monkeypatch.setattr(ocr,'require_ready',poison)
    monkeypatch.setattr('pipeline.translation_pipeline.TranslationPipeline.batch_translate_blocks',poison)
    monkeypatch.setattr('pipeline.translation_pipeline.TranslationPipeline.batch_translate_units',poison)
    source,sidecar=frozen;out=tmp_path/'published.pdf'
    reconstruct_from_sidecar(sidecar,{0:'Bag-ong teksto: maó, ñ.'},str(source),str(out))
    assert not poison.called
    assert sidecar['render_plan']['image_actions'][0]['fit']['text'] == 'Bag-ong teksto: maó, ñ.'
    with fitz.open(out) as doc: assert 'Bag-ong teksto: maó, ñ.' in doc[0].get_text()
    assert sha256(source)==sidecar['render_plan']['original_sha256']


@pytest.mark.parametrize('mismatch',['source','version','algorithm','runtime','font_manifest','sidecar'])
def test_mismatch_rejects_without_replacing_published_file(tmp_path,frozen,mismatch):
    source,sidecar=frozen;out=tmp_path/'published.pdf';out.write_bytes(b'last-published')
    plan=sidecar['render_plan']
    if mismatch=='source':plan['original_sha256']='0'*64
    if mismatch=='version':plan['version']=99
    if mismatch=='algorithm':plan['algorithm_version']=99
    if mismatch=='runtime':plan['runtime']={}
    if mismatch=='font_manifest':plan['font_manifest_sha256']='0'*64
    if mismatch=='sidecar':sidecar['version']=99
    with pytest.raises(ValueError):reconstruct_from_sidecar(sidecar,{},str(source),str(out))
    assert out.read_bytes()==b'last-published'


def test_changed_font_file_is_rejected(tmp_path,frozen,monkeypatch):
    import document.image_reconstructor as images
    import document.render_plan as plans
    root=tmp_path/'fonts';shutil.copytree(FONT_ROOT,root)
    with (root/'NotoSans-Regular.ttf').open('ab') as f:f.write(b'changed')
    monkeypatch.setattr(images,'FONT_ROOT',root);monkeypatch.setattr(plans,'FONT_ROOT',root)
    source,sidecar=frozen;out=tmp_path/'published.pdf';out.write_bytes(b'old')
    with pytest.raises(ImageHold,match='hash'):reconstruct_from_sidecar(sidecar,{},str(source),str(out))
    assert out.read_bytes()==b'old'


@pytest.mark.parametrize('fault',['unsigned','wrong_key','retarget','stale','metadata'])
def test_plan_provenance_rejects_untrusted_input_before_publication(tmp_path,frozen,monkeypatch,fault):
    from document.artifact_auth import generate_key, sign
    source,sidecar=frozen;out=tmp_path/'published.pdf';out.write_bytes(b'old')
    plan=sidecar['render_plan']
    if fault=='unsigned':plan.pop('signature')
    if fault=='wrong_key':
        key=tmp_path/'other-key';generate_key(key,'render-plan');monkeypatch.setenv('OCR_PLAN_KEY_FILE',str(key))
    if fault=='retarget':
        different=tmp_path/'other.pdf'
        with fitz.open() as doc:doc.new_page();doc.save(different)
        source=different
    if fault=='stale':
        import os
        plan['version']=2;sidecar['render_plan']=sign(plan,os.environ['OCR_PLAN_KEY_FILE'],'render-plan')
    if fault=='metadata':sidecar['blocks'][0]['position']=[1,1,2,2]
    with pytest.raises(ValueError):reconstruct_from_sidecar(sidecar,{},str(source),str(out))
    assert out.read_bytes()==b'old'


def test_php_json_roundtrip_preserves_signed_plan_provenance(tmp_path,frozen):
    import subprocess
    php=shutil.which('php')
    if not php:pytest.skip('PHP runtime required for the cross-language JSON boundary')
    source,sidecar=frozen
    result=subprocess.run([php,'-r','echo json_encode(json_decode(stream_get_contents(STDIN), true));'],
        input=json.dumps(sidecar).encode('utf-8'),stdout=subprocess.PIPE,check=True)
    restored=json.loads(result.stdout)
    output=tmp_path/'php-roundtrip.pdf'
    reconstruct_from_sidecar(restored,{0:'Edited target'},str(source),str(output))
    with fitz.open(output) as doc:assert 'Edited target' in doc[0].get_text()


def test_unfittable_edit_preserves_last_published_file(tmp_path,frozen):
    source,sidecar=frozen;out=tmp_path/'published.pdf';out.write_bytes(b'last-published')
    with pytest.raises(ImageHold,match='fit'):
        reconstruct_from_sidecar(sidecar,{0:'Much longer translation '*1000},str(source),str(out))
    assert out.read_bytes()==b'last-published'


def test_spawned_worker_reconstructs_without_extraction(tmp_path,frozen):
    source,sidecar=frozen;out=tmp_path/'worker.pdf'
    result=run_pdf('regenerate',sidecar,{0:'Edited target'},str(source),str(out))
    assert result['output_path']==str(out)
    assert result['sidecar']['render_plan']['image_actions'][0]['fit']['text']=='Edited target'
    with fitz.open(out) as doc:assert 'Edited target' in doc[0].get_text()


def test_resource_limits_and_timeout_ladder(tmp_path):
    assert job_budget({})==900
    assert job_budget({'PYTHON_SERVICE_TIMEOUT':300,'TRANSLATION_JOB_TIMEOUT':500,'QUEUE_WORKER_TIMEOUT':700})==240
    with pytest.raises(ValueError,match='budgets'):job_budget({'PYTHON_SERVICE_TIMEOUT':1500})
    with pytest.raises(TimeoutError):run_pdf('inspect',deadline=time.monotonic()-1)
    source=tmp_path/'too-many.pdf'
    with fitz.open() as doc:
        for _ in range(51):doc.new_page()
        doc.save(source)
    with pytest.raises(ValueError,match='50 pages'):run_pdf('extract',str(source),'English','auto')


def test_compressed_mask_expansion_is_bounded():
    import base64,zlib
    from document.image_reconstructor import decode_mask
    action={'image_size':[2,2],'mask':base64.b64encode(zlib.compress(b'1'*100_000)).decode()}
    with pytest.raises(ImageHold,match='unbounded'):decode_mask(action)


def test_concurrent_pdf_requests_use_at_most_one_isolated_worker(frozen):
    import multiprocessing
    from concurrent.futures import ThreadPoolExecutor
    source,_=frozen
    maximum=0
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(run_pdf,'inspect',str(source),'English','auto') for _ in range(2)]
        while not all(f.done() for f in futures):
            maximum=max(maximum,len(multiprocessing.active_children()))
            time.sleep(.01)
        results=[f.result() for f in futures]
    assert maximum==1 and results[0]==results[1]


@pytest.mark.parametrize('operation', ['render', 'preserve', 'regenerate'])
@pytest.mark.parametrize('limit', ['pages', 'pixels'])
def test_all_strict_pdf_operations_validate_the_actual_template(tmp_path, operation, limit):
    source, output = tmp_path/'oversized.pdf', tmp_path/'published.pdf'
    with fitz.open() as doc:
        for _ in range(51 if limit == 'pages' else 1):
            doc.new_page(width=2500 if limit == 'pixels' else 100, height=2500 if limit == 'pixels' else 100)
        doc.save(source)
    output.write_bytes(b'last-published')
    if operation == 'regenerate':
        extraction = {'original_sha256':sha256(source), 'regions':[], 'pages':[], 'image_actions':[]}
        sidecar = {'version':3, 'format':'.pdf', 'blocks':[], 'render_plan':make_plan(extraction, [])}
        args = (sidecar, {}, str(source), str(output))
    elif operation == 'render':
        args = (str(source), [], str(output), 'English', 'Cebuano')
    else:
        args = (str(source), str(output))
    with pytest.raises(ValueError, match='50 pages|40 MP'):
        run_pdf(operation, *args)
    assert output.read_bytes() == b'last-published'


@pytest.mark.parametrize('close_failure', [False, True])
def test_startup_timeout_terminates_owned_process_and_releases_locks(tmp_path, monkeypatch, close_failure):
    import document.pdf_worker as worker
    from types import SimpleNamespace
    from unittest.mock import Mock
    process = Mock(pid=123)
    alive = [True]
    process.is_alive.side_effect = lambda:alive[0]
    process.terminate.side_effect = lambda:alive.__setitem__(0, False)
    if close_failure: process.close.side_effect = OSError('Simulated close failure')
    receiving, sending = Mock(), Mock()
    receiving.poll.return_value = False
    context = SimpleNamespace(Pipe=lambda **kwargs:(receiving,sending), Process=lambda **kwargs:process)
    monkeypatch.setattr(worker.multiprocessing, 'get_context', lambda *args:context)
    monkeypatch.setattr(worker, '_LOCK', __import__('threading').Lock())
    # Exercise the pre-setsid POSIX race without starting or signalling a process.
    fake_os = SimpleNamespace(name='posix', killpg=Mock(side_effect=ProcessLookupError), environ={})
    monkeypatch.setattr(worker, 'os', fake_os)
    monkeypatch.setattr(__import__('signal'), 'SIGKILL', 9, raising=False)
    real_open = open
    actual_lockfile = real_open(tmp_path/'lock', 'a+b')
    lockfile = Mock(wraps=actual_lockfile)
    monkeypatch.setattr(worker, 'open', lambda *args:lockfile, raising=False)
    fake_fcntl = SimpleNamespace(LOCK_EX=2, LOCK_NB=4, flock=lambda *args:None)
    monkeypatch.setitem(__import__('sys').modules, 'fcntl', fake_fcntl)
    with pytest.raises((TimeoutError, OSError)):
        worker.run_pdf('inspect', deadline=time.monotonic()+10)
    process.terminate.assert_called_once()
    receiving.close.assert_called_once()
    sending.close.assert_called()
    assert actual_lockfile.closed
    assert worker._LOCK.acquire(blocking=False)
    worker._LOCK.release()


def test_oversized_image_metadata_is_rejected_before_any_pixel_decode(tmp_path, monkeypatch):
    import io
    from PIL import Image
    from document.pdf_source import original_pdf
    from document.image_reconstructor import occurrence_safety
    stream = io.BytesIO()
    Image.new('RGB', (2,2), 'white').save(stream, 'PNG')
    source = tmp_path/'oversized-image.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=100)
        xref = page.insert_image(page.rect, stream=stream.getvalue())
        doc.xref_set_key(xref, 'Width', '10000')
        doc.xref_set_key(xref, 'Height', '5000')
        doc.save(source)
    # The declared bitmap exceeds40MP; do not decode this malformed tiny stream.
    decode = Mock(side_effect=AssertionError('Image info decoding ran before the metadata limit'))
    monkeypatch.setattr(fitz.Page, 'get_image_info', decode)
    with pytest.raises(ValueError, match='40 MP'):
        with original_pdf(source):
            raise AssertionError('Oversized source reached the rendering body')
    with fitz.open(source) as doc:
        with pytest.raises(ImageHold, match='40 MP'):
            occurrence_safety(doc, 0, xref)
    from document.pdf_regions import inventory_pdf
    with pytest.raises(ValueError, match='40 MP'):
        inventory_pdf(source, [], 'English')
    assert not decode.called


def _contained_sleeping_descendant(connection):
    import subprocess
    import sys
    from document.pdf_worker import _contain_children
    containment = _contain_children()
    child = subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],
                             stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    connection.send(child.pid)
    time.sleep(30)


@pytest.mark.skipif(__import__('os').name != 'nt',reason='Actual Windows job containment check')
def test_windows_worker_exit_terminates_its_owned_descendant():
    import ctypes
    import multiprocessing
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    context=multiprocessing.get_context('spawn')
    receiving,sending=context.Pipe(duplex=False)
    process=context.Process(target=_contained_sleeping_descendant,args=(sending,))
    handle=None
    try:
        process.start();sending.close()
        assert receiving.poll(15), 'Diagnostic worker did not start its child'
        pid=receiving.recv()
        # Hold this exact owned process handle so cleanup cannot hit a reused PID.
        handle=kernel.OpenProcess(0x00100001,False,pid)
        assert handle
        process.terminate();process.join(timeout=3)
        assert kernel.WaitForSingleObject(handle,5000)==0
    finally:
        if handle:
            if kernel.WaitForSingleObject(handle,0)!=0:kernel.TerminateProcess(handle,1)
            kernel.CloseHandle(handle)
        if process.pid is not None:
            if process.is_alive():process.kill();process.join(timeout=3)
            process.close()
        receiving.close();sending.close()


def test_serialized_render_plan_cap_is_enforced_before_mask_work():
    from document.render_plan import check_bounds
    with pytest.raises(ValueError,match='16 MB'):
        check_bounds({'diagnostic_padding':'x'*16_000_001})
