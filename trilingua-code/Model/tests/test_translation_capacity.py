"""Offline concurrency proofs: count transport calls and claims, not UI labels."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from document_jobs import DocumentJobWorker
from execution_capacity import ExecutionCapacity
from pipeline.fair_scheduler import FairDocumentBatchScheduler
from provider_errors import OperationFailure
from provider_request_gate import ProviderRequestGate
from provider_usage import ollama_post, request_identity, usage_scope


def wait_until(predicate):
    deadline = time.monotonic() + 3
    while not predicate():
        assert time.monotonic() < deadline, 'Concurrent operation did not reach its checkpoint'
        time.sleep(.005)


def test_three_provider_jobs_overlap_all_purposes_and_fourth_waits(monkeypatch):
    gate = ProviderRequestGate(3)
    monkeypatch.setattr('provider_request_gate.provider_request_gate', gate)
    release = threading.Event()
    lock = threading.Lock()
    active, peaks, purposes = set(), [], []

    def run(job, purpose):
        def post(*args, **kwargs):
            with lock:
                assert job not in active
                active.add(job)
                peaks.append(len(active))
                purposes.append(purpose)
            try:
                assert release.wait(3)
                return SimpleNamespace(status_code=200, headers={}, json=lambda: {'message': {'content': 'mock'}})
            finally:
                with lock:
                    active.remove(job)
        with request_identity(engine_job_uuid=job), usage_scope() as usage:
            ollama_post(post, 'https://provider.invalid', purpose=purpose, json={'model': 'mock-model'})
        assert usage.summary()['request_count'] == 1

    with ThreadPoolExecutor(max_workers=5) as pool:
        try:
            first = [pool.submit(run, job, purpose) for job, purpose in
                     [('a', 'translation'), ('b', 'analysis'), ('c', 'quality_review')]]
            wait_until(lambda: len(active) == 3)
            fourth = pool.submit(run, 'd', 'repair')
            same_job = pool.submit(run, 'a', 'analysis')
            wait_until(lambda: len(gate._waiting) == 2)
            assert set(purposes) == {'translation', 'analysis', 'quality_review'}
            assert not fourth.done() and not same_job.done()
        finally:
            release.set()
        for future in first + [fourth, same_job]:
            future.result(timeout=3)
    assert max(peaks) == 3
    assert 'repair' in purposes
    assert not gate._active_jobs and not gate._waiting


def test_gate_fifo_skips_busy_job_without_starving_other_jobs():
    gate = ProviderRequestGate(1)
    order = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        def run(job):
            with gate.permit(job, time.monotonic() + 3):
                order.append(job)
        with gate.permit('a', time.monotonic() + 3):
            b = pool.submit(run, 'b')
            wait_until(lambda: len(gate._waiting) == 1)
            a = pool.submit(run, 'a')
            wait_until(lambda: len(gate._waiting) == 2)
        b.result(timeout=3)
        a.result(timeout=3)
    assert order == ['b', 'a']


def test_gate_cancel_deadline_and_exception_do_not_leak():
    gate = ProviderRequestGate(1)
    with gate.permit('active', time.monotonic() + 3):
        with pytest.raises(OperationFailure):
            with gate.permit('expired', time.monotonic() - 1):
                pytest.fail('Expired request admitted')
        def cancel():
            raise InterruptedError('cancelled')
        with pytest.raises(InterruptedError):
            with gate.permit('cancelled', time.monotonic() + 3, cancel):
                pytest.fail('Cancelled request admitted')
    with pytest.raises(ValueError):
        with gate.permit('failed', time.monotonic() + 3):
            raise ValueError('transport callback failed')
    with gate.permit('next', time.monotonic() + 3):
        assert gate._active_jobs == {'next'}
    assert not gate._waiting and not gate._active_jobs


def test_transport_backoff_releases_provider_permit(monkeypatch):
    gate = ProviderRequestGate(1)
    monkeypatch.setattr('provider_request_gate.provider_request_gate', gate)
    calls = []
    def reply(status):
        return SimpleNamespace(status_code=status, headers={}, json=lambda: {'error': 'rate limit'} if status == 429 else {})
    def backoff(_):
        assert not gate._active_jobs
        with request_identity(engine_job_uuid='other'):
            ollama_post(lambda *a, **k: calls.append('other') or reply(200), 'https://provider.invalid', json={})
    monkeypatch.setattr('provider_usage.wait_backoff', backoff)
    post = Mock(side_effect=[reply(429), reply(200)])
    with request_identity(engine_job_uuid='first'):
        ollama_post(post, 'https://provider.invalid', json={})
    assert post.call_count == 2 and calls == ['other']
    assert not gate._active_jobs


def test_circuit_refusal_releases_permit_without_transport(monkeypatch):
    gate = ProviderRequestGate(1)
    monkeypatch.setattr('provider_request_gate.provider_request_gate', gate)
    monkeypatch.setattr('provider_circuit.acquire', Mock(side_effect=OperationFailure('circuit_storage_unavailable', 503)))
    post = Mock()
    with pytest.raises(OperationFailure):
        ollama_post(post, 'https://provider.invalid', json={})
    post.assert_not_called()
    assert not gate._active_jobs


def test_scheduler_runs_one_batch_per_document_but_three_distinct_documents():
    scheduler = FairDocumentBatchScheduler(slots=3)
    release = threading.Event()
    active = set()
    lock = threading.Lock()
    def run(job):
        with lock:
            assert job not in active
            active.add(job)
        try:
            assert release.wait(3)
        finally:
            with lock:
                active.remove(job)
    a = scheduler.submit('a', lambda: run('a'))
    wait_until(lambda: 'a' in active)
    a2 = scheduler.submit('a', lambda: run('a'))
    b = scheduler.submit('b', lambda: run('b'))
    c = scheduler.submit('c', lambda: run('c'))
    try:
        wait_until(lambda: len(active) == 3)
        assert not a2.running()
    finally:
        release.set()
    for future in (a, a2, b, c):
        future.result(timeout=3)


@pytest.mark.parametrize('texts', [0, 1, 2, 3])
def test_worker_claims_only_available_whole_job_slots_in_mixed_load(texts):
    capacity = ExecutionCapacity(3)
    release, stop_text = threading.Event(), threading.Event()
    held = []
    def hold_text():
        with capacity.slot() as acquired:
            assert acquired
            held.append(True)
            assert stop_text.wait(4)
    with ThreadPoolExecutor(max_workers=3) as pool:
        text_futures = [pool.submit(hold_text) for _ in range(texts)]
        wait_until(lambda: len(held) == texts)
        claimed = []
        lock = threading.Lock()
        store = Mock()
        def claim():
            with lock:
                claimed.append(len(claimed) + 1)
                return {'id': claimed[-1]}
        store.claim.side_effect = claim
        worker = DocumentJobWorker(store, Mock(), workers=3, admission=capacity.slot)
        def run_one(row):
            # Real nested pipeline call must reuse the reserved job slot.
            with capacity.slot() as acquired:
                assert acquired
                assert release.wait(4)
        worker.run_one = run_one
        worker.start()
        try:
            wait_until(lambda: len(claimed) == 3 - texts)
            with capacity.slot() as admitted:
                assert not admitted
            assert len(claimed) == 3 - texts
        finally:
            worker.stop.set()
            worker.wake.set()
            release.set()
            stop_text.set()
            worker.join()
        for future in text_futures:
            future.result(timeout=3)
    assert all(not thread.is_alive() for thread in worker.threads)
    assert all(capacity.semaphore.acquire(blocking=False) for _ in range(3))
    assert not capacity.semaphore.acquire(blocking=False)
    for _ in range(3):
        capacity.semaphore.release()


def test_execution_exception_releases_owned_capacity():
    capacity = ExecutionCapacity(1)
    with pytest.raises(ValueError):
        with capacity.slot() as acquired:
            assert acquired
            raise ValueError('pipeline failed')
    with capacity.slot() as acquired:
        assert acquired


@pytest.mark.parametrize('limit', [0, 4])
def test_capacity_rejects_unsupported_configuration(limit):
    with pytest.raises(ValueError):
        ExecutionCapacity(limit)
    with pytest.raises(ValueError):
        ProviderRequestGate(limit)


@pytest.mark.parametrize('module_name,class_name', [
    ('pipeline.translation_pipeline', 'TranslationPipeline'),
    ('pipeline.document_pipeline', 'DocumentPipeline'),
])
def test_shared_cache_initializes_once_under_concurrent_first_use(monkeypatch, module_name, class_name):
    import importlib
    module = importlib.import_module(module_name)
    instance = object.__new__(getattr(module, class_name))
    instance._shared_cache = None
    instance._cache_init_lock = threading.Lock()
    instance.provider = SimpleNamespace(name='mock', model_name='mock')
    cache = object()
    def create(**kwargs):
        time.sleep(.02)  # Expose the original check-then-create race.
        return cache
    factory = Mock(side_effect=create)
    monkeypatch.setattr(module, 'SQLiteTranslationCache', factory)
    monkeypatch.setattr(module, '_TRANSLATION_CACHE_ENABLED', True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: instance._get_cache(), range(3)))
    assert all(result is cache for result in results)
    factory.assert_called_once()


def test_three_docx_jobs_share_real_pipeline_without_overwriting_sources(document_pipeline, tmp_path, monkeypatch):
    import hashlib
    from docx import Document
    from dto.requests import DocumentTranslationRequest
    from provider_usage import _identity
    monkeypatch.setattr('pipeline.document_pipeline._TRANSLATION_CACHE_ENABLED', False)
    monkeypatch.setattr('pipeline.translation_pipeline._TRANSLATION_CACHE_ENABLED', False)
    barrier = threading.Barrier(3)
    seen = set()
    lock = threading.Lock()
    original = document_pipeline.translation_pipeline.provider.translate
    def translate(*args, **kwargs):
        job = _identity.get()['engine_job_uuid']
        with lock:
            first = job not in seen
            seen.add(job)
        if first:
            barrier.wait(timeout=5)
        return original(*args, **kwargs)
    monkeypatch.setattr(document_pipeline.translation_pipeline.provider, 'translate', translate)
    inputs = []
    for i, word in enumerate(['water', 'fire', 'earth']):
        directory = tmp_path / str(i)
        directory.mkdir()
        path = directory / 'input.docx'
        document = Document()
        document.add_paragraph(f'Please explain the meaning of {word} in this lesson.')
        document.save(path)
        inputs.append((path, hashlib.sha256(path.read_bytes()).hexdigest()))
    capacity = ExecutionCapacity(3)
    def run(item):
        path, digest = item
        with capacity.slot() as admitted, request_identity(engine_job_uuid=str(path.parent)), usage_scope():
            assert admitted
            result = document_pipeline.translate(DocumentTranslationRequest(str(path), 'English', 'Cebuano', mode='fast'))
        assert result.success, result.error_message
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert result.output_path != str(path)
        assert Document(result.output_path).paragraphs[0].text != Document(path).paragraphs[0].text
        assert result.sidecar['blocks']
        return result.output_path
    with ThreadPoolExecutor(max_workers=3) as pool:
        outputs = list(pool.map(run, inputs))
    assert len(set(outputs)) == len(seen) == 3
