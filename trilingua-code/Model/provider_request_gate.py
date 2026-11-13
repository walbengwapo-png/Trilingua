"""FIFO permits for the single Python process: three account calls, one per job."""
from collections import deque
from contextlib import contextmanager
import os
import threading
import time

from provider_errors import OperationFailure


class ProviderRequestGate:
    def __init__(self, limit=1):
        if not 1 <= limit <= 3:
            raise ValueError('OLLAMA_MAX_CONCURRENT_REQUESTS must be between 1 and 3')
        self.limit = limit
        self._condition = threading.Condition()
        self._waiting = deque()
        self._active_jobs = set()

    @contextmanager
    def permit(self, job, deadline, check=lambda: None):
        ticket = (object(), job)
        admitted = False
        with self._condition:
            self._waiting.append(ticket)
            try:
                while True:
                    check()
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise OperationFailure('deadline_expired', 408)
                    first = next((row for row in self._waiting if row[1] not in self._active_jobs), None)
                    if first is ticket and len(self._active_jobs) < self.limit:
                        self._waiting.remove(ticket)
                        self._active_jobs.add(job)
                        admitted = True
                        break
                    self._condition.wait(min(left, .1))
            finally:
                if not admitted:
                    self._waiting.remove(ticket)
                    self._condition.notify_all()
        try:
            yield
        finally:
            with self._condition:
                self._active_jobs.remove(job)
                self._condition.notify_all()


provider_request_gate = ProviderRequestGate(int(os.environ.get('OLLAMA_MAX_CONCURRENT_REQUESTS', '1')))
