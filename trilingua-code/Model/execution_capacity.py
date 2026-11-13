"""Shared whole-job admission for API calls and the durable document workers."""
from contextlib import contextmanager
from contextvars import ContextVar
import threading


class ExecutionCapacity:
    def __init__(self, limit):
        if not 1 <= limit <= 3:
            raise ValueError('TRANSLATION_MAX_CONCURRENT must be between 1 and 3')
        self.limit = limit
        self.semaphore = threading.BoundedSemaphore(limit)
        self._owned = ContextVar(f'translation_slot_{id(self)}', default=False)

    @contextmanager
    def slot(self, timeout=0):
        if self._owned.get():
            yield True
            return
        acquired = self.semaphore.acquire(timeout=timeout)
        if not acquired:
            yield False
            return
        token = self._owned.set(True)
        try:
            yield True
        finally:
            self._owned.reset(token)
            self.semaphore.release()
