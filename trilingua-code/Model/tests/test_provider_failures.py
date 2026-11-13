"""R1: offline HTTP classification, deadline and safe-envelope regressions."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import Mock

import pytest
import requests

from provider_errors import ProviderFailure, ProviderStopped, OperationFailure
from provider_usage import ollama_post, retry_after, usage_scope, transport_operation, request_identity


def response(status, error=None):
    result = Mock(status_code=status, headers={})
    result.json.return_value = {'error': error} if error else {'model': 'returned', 'message': {'content': 'ok'}}
    return result


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr('provider_usage.time.sleep', lambda _: None)


@pytest.mark.parametrize('status,category', [(401, 'credentials'), (402, 'billing'), (403, 'permission'), (429, 'quota_exhausted')])
def test_hard_errors_preserve_status_and_make_exactly_one_call(status, category):
    post = Mock(return_value=response(status, {'code': 'insufficient_quota', 'message': 'quota exhausted'}))
    with pytest.raises(ProviderStopped) as error:
        ollama_post(post, 'http://mock', json={'model': 'requested'})
    assert post.call_count == 1
    assert error.value.category == category
    assert error.value.details['original_status'] == status
    assert error.value.status_code == status


@pytest.mark.parametrize('status', [429, 500, 502, 503, 504])
def test_transient_errors_are_bounded(status):
    post = Mock(return_value=response(status, 'rate limit'))
    with pytest.raises(ProviderFailure) as error:
        ollama_post(post, 'http://mock', json={'model': 'requested'})
    assert not isinstance(error.value, ProviderStopped)
    assert post.call_count == 3
    assert error.value.details['retry_count'] == 2


@pytest.mark.parametrize('exception,uncertain', [(requests.Timeout, True), (requests.ConnectionError, False)])
def test_transport_failures_keep_uncertain_billing(exception, uncertain):
    post = Mock(side_effect=exception('secret must not be logged'))
    with pytest.raises(ProviderFailure) as error:
        ollama_post(post, 'http://mock', json={})
    assert post.call_count == 3
    assert error.value.details['billing_uncertain'] is uncertain
    assert 'secret' not in str(error.value.details)


def test_limit_text_is_not_a_credential_stop_and_context_only_fails_operation():
    post = Mock(return_value=response(400, 'context length limit exceeded'))
    with pytest.raises(OperationFailure) as error:
        ollama_post(post, 'http://mock', json={})
    assert error.value.category == 'input_limit'
    assert post.call_count == 1
    assert ollama_post(Mock(return_value=response(200)), 'http://mock', json={}).status_code == 200


def test_content_retries_cannot_multiply_transport_attempts():
    post = Mock(return_value=response(200))
    @transport_operation()
    def operation():
        for _ in range(10):
            ollama_post(post, 'http://mock', json={})
    with pytest.raises(OperationFailure):
        operation()
    assert post.call_count == 3


def test_retry_after_numeric_date_and_deadline_cap():
    assert retry_after('12') == 12
    assert 8 <= retry_after(format_datetime(datetime.now(timezone.utc) + timedelta(seconds=10))) <= 10
    limited = response(429, 'busy')
    limited.headers['Retry-After'] = '120'
    post = Mock(return_value=limited)
    with pytest.raises(ProviderFailure):
        ollama_post(post, 'http://mock', json={})
    assert post.call_count == 1


def test_malformed_response_is_typed_not_retried():
    broken = response(200)
    broken.json.side_effect = ValueError('bad json')
    post = Mock(return_value=broken)
    with pytest.raises(OperationFailure) as error:
        ollama_post(post, 'http://mock', json={})
    assert error.value.category == 'malformed_response'
    assert post.call_count == 1


def test_safe_record_contains_identity_but_no_prompt_or_auth(caplog):
    post = Mock(return_value=response(401, 'PROMPT Authorization=abc ' + 'x' * 1200))
    with request_identity(translation_uuid='translation', engine_job_uuid='engine'):
        with pytest.raises(ProviderStopped) as error:
            ollama_post(post, 'http://mock', json={'model': 'requested', 'messages': [{'content': 'PROMPT'}]})
    details = error.value.details
    assert details['translation_uuid'] == 'translation'
    assert len(details['body_excerpt']) == 1024
    assert details['body_redacted'] and details['body_truncated']
    assert 'PROMPT' not in caplog.text and 'abc' not in caplog.text
    assert 'Reference:' in str(error.value)


@pytest.mark.parametrize('budget,allowlist,category', [(0, None, 'request_budget_exhausted'), (None, {'other'}, 'disallowed_provider')])
def test_local_budget_failures_never_call_http(budget, allowlist, category):
    post = Mock()
    with pytest.raises(OperationFailure) as error:
        with usage_scope(max_requests=budget, allowed_providers=allowlist):
            ollama_post(post, 'http://mock', json={})
    assert error.value.category == category
    post.assert_not_called()
