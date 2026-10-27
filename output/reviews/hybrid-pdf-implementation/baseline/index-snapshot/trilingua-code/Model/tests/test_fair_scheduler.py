import threading
import time

from pipeline.fair_scheduler import FairDocumentBatchScheduler


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
