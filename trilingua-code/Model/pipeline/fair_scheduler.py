"""Fair, process-wide scheduler for document translation batches.

One Python service owns the GPT-OSS quota.  Documents submit callable batches
here instead of each creating an independent eight-worker burst.  Workers pick
the next document round-robin, so two active documents share the configured
capacity rather than one starving the other.
"""

from __future__ import annotations

import os
from contextvars import copy_context
import threading
import time
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Callable, TypeVar
from provider_usage import backoff_scope

T = TypeVar("T")


@dataclass
class _Task:
    document_id: str
    future: Future
    submitted_at: float
    callback: Callable[[], object]


class FairDocumentBatchScheduler:
    def __init__(self, slots: int | None = None):
        self.slots = max(1, slots or int(os.environ.get("GPTOSS_TRANSLATION_SLOTS", "3")))
        self._queues: dict[str, deque[_Task]] = {}
        self._round_robin: deque[str] = deque()
        self._last_document_id: str | None = None
        self._running_documents: set[str] = set()
        self._condition = threading.Condition()
        self._active = 0
        self._resuming = 0
        # One bounded standby can serve pending batches while a callback backs off.
        # Active callbacks still use exactly the configured number of slots.
        for number in range(self.slots + 1):
            threading.Thread(
                target=self._run, name=f"gptoss-document-slot-{number + 1}", daemon=True
            ).start()

    def submit(self, document_id: str, callback: Callable[[], T]) -> Future:
        context = copy_context()
        original_callback = callback
        def invoke():
            with backoff_scope(self.backoff):
                return original_callback()
        callback = lambda: context.run(invoke)
        future: Future = Future()
        task = _Task(document_id=document_id, future=future, submitted_at=time.monotonic(), callback=callback)
        with self._condition:
            queue = self._queues.setdefault(document_id, deque())
            was_empty = not queue
            queue.append(task)
            if was_empty and document_id not in self._round_robin:
                self._round_robin.append(document_id)
            self._condition.notify()
        return future

    def _next_task(self) -> _Task:
        with self._condition:
            while not any(doc not in self._running_documents for doc in self._round_robin) or self._active >= self.slots or self._resuming:
                self._condition.wait()
            self._active += 1
            # Prefer a different ready document after the previous dispatch.
            # This also stays fair when a second document arrives while all
            # slots were already executing work for the first document.
            document_id = self._round_robin.popleft()
            while document_id in self._running_documents:
                self._round_robin.append(document_id)
                document_id = self._round_robin.popleft()
            if document_id == self._last_document_id:
                alternate = next((doc for doc in self._round_robin if doc not in self._running_documents), None)
                if alternate is not None:
                    self._round_robin.remove(alternate)
                    self._round_robin.append(document_id)
                    document_id = alternate
            self._running_documents.add(document_id)
            queue = self._queues[document_id]
            task = queue.popleft()
            if queue:
                self._round_robin.append(document_id)
            else:
                del self._queues[document_id]
            self._last_document_id = document_id
            return task

    def backoff(self, seconds: float) -> None:
        with self._condition:
            self._active -= 1
            self._condition.notify_all()
        try:
            time.sleep(seconds)
        finally:
            with self._condition:
                self._resuming += 1
                try:
                    while self._active >= self.slots:
                        self._condition.wait()
                    self._active += 1
                finally:
                    self._resuming -= 1
                    self._condition.notify_all()

    def _run(self) -> None:
        while True:
            task = self._next_task()
            try:
                if not task.future.set_running_or_notify_cancel():
                    continue
                # Local timing only; never source content.
                task.future.scheduler_wait_ms = (time.monotonic() - task.submitted_at) * 1000
                task.future.set_result(task.callback())
            except BaseException as error:
                task.future.set_exception(error)
            finally:
                with self._condition:
                    self._active -= 1
                    self._running_documents.remove(task.document_id)
                    self._condition.notify_all()


document_batch_scheduler = FairDocumentBatchScheduler()
