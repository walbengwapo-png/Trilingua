"""Provider request boundary: terminal Ollama failures cannot trigger failover."""
from contextlib import contextmanager
from contextvars import ContextVar
from threading import RLock
import os
from urllib.parse import urlsplit

class ProviderStopped(RuntimeError):
    """Authentication, quota or ambiguous rate limit requires operator action."""
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code

class ProviderUsage:
    def __init__(self):
        self.lock = RLock()
        self.stop_reason = None

    def check(self):
        if self.stop_reason:
            raise ProviderStopped(self.stop_reason)
        if _run_stop_reason:
            raise ProviderStopped(_run_stop_reason)

_current = ContextVar('provider_usage', default=None)
_run_stop_reason = None

@contextmanager
def usage_scope():
    existing = _current.get()
    usage = existing or ProviderUsage()
    token = _current.set(usage)
    try:
        usage.check()
        yield usage
        usage.check()
    finally:
        _current.reset(token)

def ollama_headers(url):
    headers = {'Content-Type': 'application/json'}
    endpoint = urlsplit(url)
    if endpoint.hostname == 'ollama.com':
        if endpoint.scheme != 'https':
            raise ValueError('Direct Ollama Cloud API access requires HTTPS')
        key = os.environ.get('OLLAMA_API_KEY', '').strip()
        if not key:
            raise ValueError('OLLAMA_API_KEY is required for direct Ollama Cloud API access')
        headers['Authorization'] = f'Bearer {key}'
    return headers

def ollama_post(post, url, **kwargs):
    global _run_stop_reason
    usage = _current.get()
    if usage:
        usage.check()
    elif _run_stop_reason:
        raise ProviderStopped(_run_stop_reason)
    response = post(url, **kwargs)
    reason = None
    if response.status_code in (401, 403, 429):
        reason = f'Ollama request stopped: HTTP {response.status_code}; no retry or fallback permitted'
    try:
        data = response.json()
        error = data.get('error', '') if isinstance(data, dict) else ''
        if error and any(marker in str(error).lower() for marker in ('quota', 'allowance', 'limit', 'unauthorized', 'authentication')):
            reason = 'Ollama request stopped: provider reported authentication/quota/allowance failure'
    except (ValueError, TypeError, AttributeError):
        pass
    if reason:
        if usage:
            usage.stop_reason = reason
        # Remain stopped across requests/cases until the process is deliberately restarted.
        _run_stop_reason = reason
        raise ProviderStopped(reason, response.status_code)
    return response
