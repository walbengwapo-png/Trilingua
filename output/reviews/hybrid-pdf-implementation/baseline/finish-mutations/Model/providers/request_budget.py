"""Request-local transport limits; no global session or timeout mutation."""
from contextlib import contextmanager
from contextvars import ContextVar
import time
from urllib3.util import Timeout

_deadline = ContextVar('pdf_provider_deadline', default=None)


@contextmanager
def request_deadline(deadline):
    token = _deadline.set(deadline)
    try:
        yield
    finally:
        _deadline.reset(token)


def remaining():
    deadline = _deadline.get()
    if deadline is None:
        return None
    value = deadline-time.monotonic()
    if value <= 0:
        raise TimeoutError('Document deadline expired before provider transport')
    return value


def transport_timeout(connect, read):
    budget = remaining()
    if budget is None:
        return (connect, read)
    return Timeout(total=budget, connect=min(connect,budget), read=min(read,budget))


def retry_sleep(seconds):
    budget = remaining()
    if budget is not None and seconds >= budget:
        raise TimeoutError('Provider retry would exceed document deadline')
    time.sleep(seconds)
