"""Provider request boundary: terminal Ollama failures cannot trigger failover."""
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from threading import RLock
import os
import time
from urllib.parse import urlsplit

from provider_errors import ProviderFailure, ProviderStopped, OperationFailure, classify, safe_excerpt
from functools import wraps
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from uuid import uuid4
import logging
import random
import requests
from providers.request_budget import remaining
from urllib3.util import Timeout

_operation = ContextVar('provider_transport_operation', default=None)
_identity = ContextVar('provider_identity', default={})
_backoff_waiter = ContextVar('provider_backoff_waiter', default=None)


@contextmanager
def backoff_scope(waiter):
    token = _backoff_waiter.set(waiter)
    try:
        yield
    finally:
        _backoff_waiter.reset(token)


def wait_backoff(seconds):
    waiter = _backoff_waiter.get()
    (waiter or time.sleep)(seconds)

@contextmanager
def request_identity(**identity):
    token = _identity.set(identity)
    try:
        yield
    finally:
        _identity.reset(token)


def transport_operation(attempts_env=None):
    """Bound all transport/content retries in one provider operation to three calls."""
    def decorate(callback):
        @wraps(callback)
        def run(*args, **kwargs):
            if _operation.get() is not None:
                return callback(*args, **kwargs)
            limit = min(3, max(1, int(os.environ.get(attempts_env, '3')))) if attempts_env else 3
            token = _operation.set({'attempt': 0, 'limit': limit, 'last': None,
                                    'deadline': time.monotonic() + 59, 'correlation_id': str(uuid4()), 'billing_uncertain': False})
            try:
                return callback(*args, **kwargs)
            finally:
                _operation.reset(token)
        return run
    return decorate


def retry_after(value):
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except (ValueError, TypeError):
        try:
            return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0.0

class ProviderUsage:
    def __init__(self, allowed_providers=None, max_requests=None):
        self.lock = RLock()
        self.stop_reason = None
        self.allowed_providers = allowed_providers
        self.max_requests = max_requests
        self.attempts = []

    def check(self):
        if self.stop_reason:
            raise self.stop_reason if isinstance(self.stop_reason, ProviderFailure) else OperationFailure('operation_cancelled', 409)

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
_purpose = ContextVar('provider_purpose', default=None)
_active_lock = RLock()
_active_requests = 0

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

@transport_operation()
def ollama_post(post, url, **kwargs):
    """One retry boundary. No provider permit or recovery lease spans a sleep."""
    usage = _current.get()
    operation = _operation.get()
    provider = kwargs.pop('provider', 'gptoss')
    purpose = kwargs.pop('purpose', 'translation')
    purpose = _purpose.get() or purpose
    model = kwargs.get('json', {}).get('model', '')
    while operation['attempt'] < operation['limit']:
        if usage:
            usage.check()
        budget = min(59, operation['deadline'] - time.monotonic(), remaining() or 59)
        if budget <= 0:
            raise operation['last'] or OperationFailure('deadline_expired', 408)
        from provider_circuit import acquire, finish
        ticket = None
        started = time.perf_counter()
        details = {**_identity.get(), 'requested_model': model, 'returned_model': None,
                   'purpose': purpose, 'attempt': operation['attempt'] + 1, 'retry_count': operation['attempt'],
                   'retry_after': None, 'correlation_id': operation['correlation_id'],
                   'billing_uncertain': operation['billing_uncertain'], 'original_status': None, 'provider_error_code': None}
        try:
            from provider_request_gate import provider_request_gate
            identity = _identity.get()
            job = identity.get('engine_job_uuid') or identity.get('translation_uuid') or (id(usage) if usage else operation['correlation_id'])
            waiting = time.monotonic()
            with provider_request_gate.permit(job, time.monotonic() + budget, usage.check if usage else lambda: None):
                ticket = acquire()
                budget = min(59, operation['deadline'] - time.monotonic(), remaining() or 59)
                if budget <= 0:
                    raise OperationFailure('deadline_expired', 408)
                operation['attempt'] += 1
                details['provider_wait_ms'] = round((time.monotonic() - waiting) * 1000, 3)
                kwargs['timeout'] = Timeout(total=budget, connect=min(10, budget), read=budget)
                started = time.perf_counter()
                response = provider_post(post, url, provider=provider, model=model, purpose=purpose, diagnostic=details, **kwargs)
            details['original_status'] = response.status_code
            details['retry_after'] = response.headers.get('Retry-After')
            try:
                data = response.json()
            except (ValueError, TypeError):
                data = None
            details.update(safe_excerpt(data, kwargs.get('json')))
            details['returned_model'] = data.get('model') if isinstance(data, dict) else None
            failure = classify(response.status_code, data)
            if failure is None and not isinstance(data, dict):
                failure = OperationFailure('malformed_response', 502)
            if failure is None:
                finish(ticket)
                return response
            details.update({key: value for key, value in failure.details.items()
                            if key in ('provider_error_code',)})
            failure.details.update(details)
        except OperationFailure as error:
            if ticket is not None:
                finish(ticket, error)
            raise
        except (requests.Timeout, requests.ConnectionError) as error:
            operation['billing_uncertain'] |= isinstance(error, requests.Timeout)
            details.update(billing_uncertain=operation['billing_uncertain'],
                           body_excerpt='[no response]', body_redacted=False, body_truncated=False)
            failure = ProviderFailure('timeout' if isinstance(error, requests.Timeout) else 'connection_failed',
                                      504 if isinstance(error, requests.Timeout) else 503, details=details)
        failure.details['latency_ms'] = round((time.perf_counter() - started) * 1000, 3)
        operation['last'] = failure
        logging.getLogger('provider.errors').warning('provider_failure %s', failure.details)
        if isinstance(failure, (ProviderStopped, OperationFailure)):
            finish(ticket, failure)
            if usage and isinstance(failure, ProviderStopped):
                usage.stop_reason = failure
            raise failure
        if ticket.get('probe_lease') or operation['attempt'] >= operation['limit']:
            finish(ticket, failure)
            if usage:
                usage.stop_reason = failure
            raise failure
        delay = max(retry_after(details.get('retry_after')), 2 ** (operation['attempt'] - 1) + random.uniform(0, .25))
        budget = min(operation['deadline'] - time.monotonic(), remaining() or 59)
        if delay >= budget:
            finish(ticket, failure)
            if usage:
                usage.stop_reason = failure
            raise failure
        wait_backoff(delay)
    raise operation['last'] or OperationFailure('request_budget_exhausted', 409)


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


def provider_post(post, url, *, provider, model, purpose, diagnostic=None, **kwargs):
    """Record an actual HTTP attempt even if parsing or content validation fails."""
    usage = _current.get()
    row = {'provider': provider, 'model': model, 'requested_model': model, 'purpose': _purpose.get() or purpose,
           'request_id': None, 'status': None, 'outcome': 'pending', 'latency_ms': 0,
           'tokens': reported_tokens({})}
    if diagnostic is not None:
        row['provider_wait_ms'] = diagnostic.get('provider_wait_ms', 0)
        row['correlation_id'] = diagnostic.get('correlation_id')
    if usage:
        with usage.lock:
            usage.check()
            if usage.allowed_providers is not None and provider not in usage.allowed_providers:
                usage.stop_reason = OperationFailure('disallowed_provider', 403)
                usage.check()
            if usage.max_requests is not None and len(usage.attempts) >= usage.max_requests:
                usage.stop_reason = OperationFailure('request_budget_exhausted', 409)
                usage.check()
            row['sequence'] = len(usage.attempts) + 1
            usage.attempts.append(row)
    global _active_requests
    with _active_lock:
        _active_requests += 1
        row['active_provider_requests'] = _active_requests
        if diagnostic is not None:
            diagnostic['active_provider_requests'] = _active_requests
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
        with _active_lock:
            _active_requests -= 1


def submit_with_usage(executor, callback, *args, **kwargs):
    return executor.submit(copy_context().run, callback, *args, **kwargs)


def call_with_purpose(purpose, callback, /, *args, **kwargs):
    token = _purpose.set(purpose)
    try:
        return callback(*args, **kwargs)
    finally:
        _purpose.reset(token)
