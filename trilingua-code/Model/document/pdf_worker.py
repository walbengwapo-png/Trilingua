"""One isolated PDF process at a time; only paths and plain records cross it."""
import json
import multiprocessing
import os
from pathlib import Path
import threading
import time
import tempfile

_LOCK = threading.Lock()
MAX_RESULT_BYTES = 24_000_000


def _contain_children():
    # OCR subprocesses must die with this task's worker on a hard deadline.
    if os.name != 'nt':
        os.setsid()
        return None
    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_=[('process_time',c.c_int64),('job_time',c.c_int64),('flags',w.DWORD),
                  ('min_ws',c.c_size_t),('max_ws',c.c_size_t),('active',w.DWORD),
                  ('affinity',c.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
    class IO(c.Structure):
        _fields_=[(name,c.c_uint64) for name in ('read','write','other','read_bytes','write_bytes','other_bytes')]
    class Extended(c.Structure):
        _fields_=[('basic',Basic),('io',IO),('process_memory',c.c_size_t),('job_memory',c.c_size_t),
                  ('peak_process',c.c_size_t),('peak_job',c.c_size_t)]
    kernel=c.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.restype=w.HANDLE
    kernel.GetCurrentProcess.restype=w.HANDLE
    kernel.SetInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
    handle=kernel.CreateJobObjectW(None,None)
    limits=Extended();limits.basic.flags=0x2000
    if not handle or not kernel.SetInformationJobObject(handle,9,c.byref(limits),c.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle,kernel.GetCurrentProcess()):
        raise OSError('Cannot contain PDF/OCR worker subprocesses')
    return handle  # Held open until worker exit; KILL_ON_JOB_CLOSE contains descendants.


def job_budget(values=None):
    defaults = {'PYTHON_SERVICE_TIMEOUT': 1200, 'TRANSLATION_JOB_TIMEOUT': 1300, 'QUEUE_WORKER_TIMEOUT': 1500}
    if values is None:
        values = {}
        path = Path(__file__).resolve().parents[2]/'.env'
        if path.is_file():
            for line in path.read_text(encoding='utf-8-sig').splitlines():
                key, sep, value = line.partition('=')
                if sep and key.strip() in defaults:
                    values[key.strip()] = value.strip().strip('\"\'')
        values.update({k: os.environ[k] for k in defaults if k in os.environ})
    service, job, worker = [int(values.get(k,v)) for k,v in defaults.items()]
    if not 120 < service < job < worker:
        raise ValueError('PDF deadline requires valid service < job < worker budgets')
    return min(900, service-60, job-120, worker-180)


def check_deadline(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError('Whole PDF job deadline exceeded; no output published')


def _execute(connection, operation, args, scratch=None):
    from document.pdf_source import original_pdf
    from contextlib import ExitStack
    stack=ExitStack()
    try:
        containment = _contain_children()
        if scratch:
            os.environ['OCR_JOB_SCRATCH'] = scratch
        original = args[0] if operation != 'regenerate' else None
        if operation in {'extract','inspect','render','preserve'}:
            args=(stack.enter_context(original_pdf(original)),*args[1:])
        if operation in {'extract', 'inspect'}:
            from document.extractor import analyze_document
            path, language, column_mode = args[:3]
            blocks, ext = analyze_document(path, pdf_column_mode=column_mode)
            if operation == 'inspect':
                result = blocks, ext
            else:
                from document.pdf_regions import inventory_pdf
                from document.pdf_regions import sha256
                result = inventory_pdf(path, blocks, language, column_mode, source_identity=sha256(original),
                                       ocr_mode=args[3] if len(args)>3 else 'strict')
        elif operation == 'preserve':
            import shutil
            shutil.copyfile(args[0],args[1])
            result=args[1]
        elif operation == 'render':
            from document.reconstructor import write_pdf_preserved
            from document.image_reconstructor import plan_images
            path, blocks, output, source, target = args
            actions, held = plan_images(path, blocks)
            native = [b for b in blocks if not b.get('image_region')]
            report = write_pdf_preserved(native, path, output, source_lang=source, target_lang=target,
                                         strict=True, image_actions=actions)
            report['held'].extend(held)
            result = report, actions, native
        elif operation == 'regenerate':
            from document.regenerator import reconstruct_from_sidecar
            if args[0].get('version') != 3 and Path(args[2] or '').suffix.lower() == '.pdf':
                from document.pdf_source import _check_pdf_limits
                _check_pdf_limits(args[2])
            output = reconstruct_from_sidecar(*args)
            result = {'output_path':output, 'sidecar':args[0]}
        else:
            raise ValueError('Unsupported PDF worker operation')
        if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > MAX_RESULT_BYTES:
            raise ValueError('PDF worker result exceeds bounded payload')
        connection.send({'result': result})
    except Exception as exc:
        connection.send({'error': type(exc).__name__, 'message': str(exc), 'report': getattr(exc, 'report', None)})
    finally:
        stack.close()
        connection.close()


def run_pdf(operation, *args, deadline=None):
    if deadline is None: deadline = time.monotonic()+job_budget()
    check_deadline(deadline)
    if not _LOCK.acquire(timeout=max(.001,deadline-time.monotonic())):
        raise TimeoutError('PDF worker queue deadline exceeded')
    process = None
    receiving = sending = None
    lockfile = None
    scratch = None
    try:
        check_deadline(deadline)
        lockfile = open(Path(tempfile.gettempdir())/'trilingua-pdf-worker.lock','a+b')
        if lockfile.tell() == 0: lockfile.write(b'0'); lockfile.flush()
        while True:
            check_deadline(deadline)
            try:
                lockfile.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lockfile.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(lockfile.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                time.sleep(min(.05,max(.001,deadline-time.monotonic())))
        context = multiprocessing.get_context('spawn')
        from document.job_scratch import owned_scratch
        scratch = owned_scratch()
        directory = scratch.__enter__()
        receiving, sending = context.Pipe(duplex=False)
        process = context.Process(target=_execute, args=(sending, operation, args, directory), daemon=True)
        process.start()
        sending.close()
        if not receiving.poll(max(.001,deadline-time.monotonic())):
            raise TimeoutError('Isolated PDF operation deadline exceeded')
        response = receiving.recv()
        check_deadline(deadline)
        if 'error' in response:
            if response['error'] == 'PDFValidationError':
                from validators.translation_validator import PDFValidationError
                raise PDFValidationError(response['report'])
            raise ValueError(response['message'])
        return response['result']
    finally:
        try:
            if process is not None and process.pid is not None:
                process.join(timeout=.2)
                if process.is_alive():
                    if os.name != 'nt':
                        import signal
                        try: os.killpg(process.pid,signal.SIGKILL)
                        except ProcessLookupError: process.terminate()
                    else:
                        process.terminate()
                    process.join(timeout=2)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=2)
                process.close()
        finally:
            try:
                if receiving is not None: receiving.close()
            finally:
                try:
                    if sending is not None: sending.close()
                finally:
                    try:
                        if lockfile is not None: lockfile.close()
                    finally:
                        try:
                            if scratch is not None: scratch.__exit__(None, None, None)
                        finally:
                            _LOCK.release()
