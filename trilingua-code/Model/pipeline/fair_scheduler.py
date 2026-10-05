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

T = TypeVar("T")


@dataclass
class _Task:
    future: Future
    submitted_at: float
    callback: Callable[[], object]


class FairDocumentBatchScheduler:
    def __init__(self, slots: int | None = None):
        self.slots = max(1, slots or int(os.environ.get("GPTOSS_TRANSLATION_SLOTS", "8")))
        self._queues: dict[str, deque[_Task]] = {}
        self._round_robin: deque[str] = deque()
        self._last_document_id: str | None = None
        self._condition = threading.Condition()
        for number in range(self.slots):
            threading.Thread(
                target=self._run, name=f"gptoss-document-slot-{number + 1}", daemon=True
            ).start()

    def submit(self, document_id: str, callback: Callable[[], T]) -> Future:
        context = copy_context()
        original_callback = callback
        callback = lambda: context.run(original_callback)
        future: Future = Future()
        task = _Task(future=future, submitted_at=time.monotonic(), callback=callback)
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
            while not self._round_robin:
                self._condition.wait()
            # Prefer a different ready document after the previous dispatch.
            # This also stays fair when a second document arrives while all
            # slots were already executing work for the first document.
            document_id = self._round_robin.popleft()
            if len(self._round_robin) and document_id == self._last_document_id:
                alternate = self._round_robin.popleft()
                self._round_robin.append(document_id)
                document_id = alternate
            queue = self._queues[document_id]
            task = queue.popleft()
            if queue:
                self._round_robin.append(document_id)
            else:
                del self._queues[document_id]
            self._last_document_id = document_id
            return task

    def _run(self) -> None:
        while True:
            task = self._next_task()
            if not task.future.set_running_or_notify_cancel():
                continue
            # Future metadata is deliberately local/diagnostic; it never
            # includes source content.
            task.future.scheduler_wait_ms = (time.monotonic() - task.submitted_at) * 1000
            try:
                task.future.set_result(task.callback())
            except BaseException as error:
                task.future.set_exception(error)


document_batch_scheduler = FairDocumentBatchScheduler()
