"""Provider request boundary: terminal Ollama failures cannot trigger failover."""
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from threading import RLock
import os
import time
from urllib.parse import urlsplit

class ProviderStopped(RuntimeError):
    """Authentication, quota or ambiguous rate limit requires operator action."""
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code

class ProviderUsage:
    def __init__(self, allowed_providers=None, max_requests=None):
        self.lock = RLock()
        self.stop_reason = None
        self.allowed_providers = allowed_providers
        self.max_requests = max_requests
        self.attempts = []

    def check(self):
        if self.stop_reason:
            raise ProviderStopped(self.stop_reason)
        if _run_stop_reason:
            raise ProviderStopped(_run_stop_reason)

    def summary(self):
        with self.lock:
            attempts = [dict(row, tokens=dict(row['tokens'])) for row in self.attempts]
        inputs = [row['tokens']['input'] for row in attempts]
        outputs = [row['tokens']['output'] for row in attempts]
        known_input = sum(value for value in inputs if value is not None)
        known_output = sum(value for value in outputs if value is not None)
        return {
            'request_count': len(attempts),
            'input_tokens': known_input if all(value is not None for value in inputs) else None,
            'output_tokens': known_output if all(value is not None for value in outputs) else None,
            'reported_input_tokens': known_input,
            'reported_output_tokens': known_output,
            'complete': all(value is not None for value in inputs + outputs),
            'latency_ms': sum(row['latency_ms'] for row in attempts),
            'attempts': attempts,
        }

_current = ContextVar('provider_usage', default=None)
_run_stop_reason = None
_purpose = ContextVar('provider_purpose', default=None)

@contextmanager
def usage_scope(allowed_providers=None, max_requests=None):
    existing = _current.get()
    usage = existing or ProviderUsage(allowed_providers, max_requests)
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
    response = provider_post(post, url, provider=kwargs.pop('provider', 'gptoss'),
                             model=kwargs.get('json', {}).get('model', ''),
                             purpose=kwargs.pop('purpose', 'translation'), **kwargs)
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


def reported_tokens(data):
    """Keep provider counters separate; never infer token counts from words."""
    if not isinstance(data, dict): data = {}
    raw = data.get('usageMetadata') or data.get('usage') or data
    if not isinstance(raw, dict): raw = {}
    def get(*keys):
        for key in keys:
            value = raw.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return None
    return {
        'input': get('prompt_eval_count', 'promptTokenCount', 'total_input_tokens'),
        'output': get('eval_count', 'candidatesTokenCount', 'total_output_tokens'),
        'thinking': get('thoughtsTokenCount', 'total_thought_tokens', 'total_reasoning_tokens'),
        'cached_input': get('prompt_eval_cached_count', 'cachedContentTokenCount', 'total_cached_tokens', 'total_cached_input_tokens'),
        'total': get('totalTokenCount', 'total_tokens'),
        'tool_use_input': get('toolUsePromptTokenCount', 'total_tool_use_tokens'),
    }


def provider_post(post, url, *, provider, model, purpose, **kwargs):
    """Record an actual HTTP attempt even if parsing or content validation fails."""
    if _run_stop_reason:
        raise ProviderStopped(_run_stop_reason)
    usage = _current.get()
    row = {'provider': provider, 'model': model, 'requested_model': model, 'purpose': _purpose.get() or purpose,
           'request_id': None, 'status': None, 'outcome': 'pending', 'latency_ms': 0,
           'tokens': reported_tokens({})}
    if usage:
        with usage.lock:
            usage.check()
            if usage.allowed_providers is not None and provider not in usage.allowed_providers:
                usage.stop_reason = 'Provider outside approved run allowlist'
                usage.check()
            if usage.max_requests is not None and len(usage.attempts) >= usage.max_requests:
                usage.stop_reason = 'Approved outbound request budget exhausted'
                usage.check()
            row['sequence'] = len(usage.attempts) + 1
            usage.attempts.append(row)
    started = time.perf_counter()
    try:
        kwargs.setdefault("allow_redirects", False)
        response = post(url, **kwargs)
        row['status'] = response.status_code
        row['outcome'] = 'http_error' if response.status_code >= 400 else 'response'
        try:
            data = response.json()
        except (ValueError, TypeError, AttributeError):
            data = {}
            row['outcome'] = 'invalid_json'
        row['tokens'] = reported_tokens(data)
        if isinstance(data, dict):
            returned_model = data.get('model') or data.get('modelVersion')
            if isinstance(returned_model, str):
                row['model'] = returned_model
            row['provider_timing_ns'] = {key: data[key] for key in
                ('total_duration', 'load_duration', 'prompt_eval_duration', 'eval_duration')
                if isinstance(data.get(key), int)}
        if isinstance(data, dict) and isinstance(data.get('id'), str):
            row['request_id'] = data['id']
        return response
    except Exception:
        row['outcome'] = 'transport_error'
        raise
    finally:
        row['latency_ms'] = round((time.perf_counter() - started) * 1000, 3)


def submit_with_usage(executor, callback, *args, **kwargs):
    return executor.submit(copy_context().run, callback, *args, **kwargs)


def call_with_purpose(purpose, callback, /, *args, **kwargs):
    token = _purpose.set(purpose)
    try:
        return callback(*args, **kwargs)
    finally:
        _purpose.reset(token)
