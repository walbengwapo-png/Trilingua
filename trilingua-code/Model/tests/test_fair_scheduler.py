import threading
import time

from pipeline.fair_scheduler import FairDocumentBatchScheduler
from provider_usage import wait_backoff
import pytest


def test_scheduler_round_robins_pending_documents():
    scheduler = FairDocumentBatchScheduler(slots=1)
    started = []
    release_first = threading.Event()

    def first():
        started.append("a1")
        release_first.wait(2)
        return "a1"

    a1 = scheduler.submit("a", first)
    deadline = time.time() + 2
    while not started and time.time() < deadline:
        time.sleep(0.01)
    a2 = scheduler.submit("a", lambda: started.append("a2") or "a2")
    b1 = scheduler.submit("b", lambda: started.append("b1") or "b1")
    release_first.set()

    assert a1.result(timeout=2) == "a1"
    assert b1.result(timeout=2) == "b1"
    assert a2.result(timeout=2) == "a2"
    assert started == ["a1", "b1", "a2"]


def test_slot_is_free_during_backoff_and_another_batch_runs(monkeypatch):
    scheduler = FairDocumentBatchScheduler(slots=1)
    sleeping = threading.Event()
    resume = threading.Event()
    def sleep(_):
        sleeping.set()
        assert resume.wait(2)
    monkeypatch.setattr('pipeline.fair_scheduler.time.sleep', sleep)
    first = scheduler.submit('first', lambda: wait_backoff(1) or 'first')
    try:
        assert sleeping.wait(2)
        assert scheduler._active == 0
        assert scheduler.submit('second', lambda: 'second').result(timeout=2) == 'second'
        assert not first.done()
        assert scheduler.slots == 1
    finally:
        resume.set()
    assert first.result(timeout=2) == 'first'


@pytest.mark.parametrize('during_backoff', [False, True])
def test_exception_releases_slot_including_interrupted_backoff(monkeypatch, during_backoff):
    scheduler = FairDocumentBatchScheduler(slots=1)
    def fail(*args):
        raise InterruptedError('cancelled')
    if during_backoff:
        monkeypatch.setattr('pipeline.fair_scheduler.time.sleep', fail)
    failed = scheduler.submit('failed', lambda: wait_backoff(1) if during_backoff else fail())
    with pytest.raises(InterruptedError):
        failed.result(timeout=2)
    assert scheduler.submit('next', lambda: 'ok').result(timeout=2) == 'ok'


def test_cancelled_pending_batch_does_not_leak_a_slot():
    scheduler = FairDocumentBatchScheduler(slots=1)
    started, release = threading.Event(), threading.Event()
    def first():
        started.set()
        assert release.wait(2)
    active = scheduler.submit('first', first)
    assert started.wait(2)
    cancelled = scheduler.submit('cancelled', lambda: pytest.fail('Cancelled work executed'))
    assert cancelled.cancel()
    following = scheduler.submit('following', lambda: 'ok')
    release.set()
    active.result(timeout=2)
    assert following.result(timeout=2) == 'ok'
    assert cancelled.cancelled()
