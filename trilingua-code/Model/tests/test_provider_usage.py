"""F16 counts HTTP attempts, including discarded and threaded responses."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
import pytest
from provider_usage import provider_post, usage_scope, submit_with_usage, call_with_purpose, ProviderStopped


def response(data, status=200):
    result = Mock(status_code=status, headers={})
    result.json.return_value = data
    return result


def test_all_attempts_count_before_content_validation():
    post = Mock(side_effect=[response({'prompt_eval_count': 8, 'eval_count': 5, 'message': {'content': ''}}), response({'prompt_eval_count': 9, 'eval_count': 7})])
    with usage_scope() as usage:
        for _ in range(2):
            provider_post(post, 'http://test', provider='gptoss', model='20b', purpose='translation')
    summary = usage.summary()
    assert summary['request_count'] == 2
    assert summary['input_tokens'] == 17
    assert summary['output_tokens'] == 12
    assert summary['complete'] is True


def test_missing_usage_is_unknown_and_transport_attempt_is_counted():
    with usage_scope() as usage:
        provider_post(Mock(return_value=response({})), 'http://test', provider='gemini', model='test', purpose='review')
        with pytest.raises(TimeoutError):
            provider_post(Mock(side_effect=TimeoutError()), 'http://test', provider='gemini', model='test', purpose='translation')
    summary = usage.summary()
    assert summary['request_count'] == 2
    assert summary['input_tokens'] is None
    assert summary['output_tokens'] is None
    assert summary['complete'] is False
    assert summary['attempts'][1]['outcome'] == 'transport_error'


@pytest.mark.parametrize('data', [
    {'usageMetadata': {'promptTokenCount': 11, 'candidatesTokenCount': 7, 'thoughtsTokenCount': 3, 'cachedContentTokenCount': 4, 'totalTokenCount': 21}},
    {'usage': {'total_input_tokens': 11, 'total_output_tokens': 7, 'total_thought_tokens': 3, 'total_cached_tokens': 4, 'total_tokens': 21}},
])
def test_gemini_reported_usage_keeps_thinking_cached_and_total_distinct(data):
    with usage_scope() as usage:
        provider_post(Mock(return_value=response(data)), 'http://test', provider='gemini', model='test', purpose='review')
    result = usage.summary()
    assert result['input_tokens'] == 11
    assert result['output_tokens'] == 7
    assert result['attempts'][0]['tokens']['thinking'] == 3
    assert result['attempts'][0]['tokens']['cached_input'] == 4
    assert result['attempts'][0]['tokens']['total'] == 21


def test_worker_threads_share_collector_and_review_purpose():
    with usage_scope() as usage:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [submit_with_usage(pool, call_with_purpose, 'quality_review', provider_post, Mock(return_value=response({'prompt_eval_count': 1, 'eval_count': 2})), 'http://test', provider='ollama_analysis', model='gemma4', purpose='analysis') for _ in range(4)]
            for future in futures: future.result()
    result = usage.summary()
    assert result['request_count'] == 4
    assert result['input_tokens'] == 4
    assert {row['purpose'] for row in result['attempts']} == {'quality_review'}


def test_cache_only_operation_reports_zero_outbound_usage():
    with usage_scope() as usage: pass
    assert usage.summary()['request_count'] == 0
    assert usage.summary()['input_tokens'] == 0


def test_disallowed_provider_is_blocked_before_outbound_call():
    post = Mock()
    with pytest.raises(ProviderStopped):
        with usage_scope(allowed_providers={'gptoss'}):
            provider_post(post, 'http://test', provider='gemini', model='test', purpose='translation')
    post.assert_not_called()


def test_gptoss_discarded_empty_response_is_included_in_actual_usage(monkeypatch):
    from providers.gptoss import GPTOSSProvider
    monkeypatch.setenv('GPTOSS_MAX_ATTEMPTS', '2')
    monkeypatch.setattr('providers.gptoss._time.sleep', lambda _: None)
    provider = GPTOSSProvider()
    provider._session.post = Mock(side_effect=[
        response({'message': {'content': ''}, 'prompt_eval_count': 10, 'eval_count': 6}),
        response({'message': {'content': 'Tubig'}, 'prompt_eval_count': 12, 'eval_count': 3})])
    with usage_scope() as usage:
        result = provider.translate('Water', 'English', 'Cebuano')
    assert result.success
    assert result.token_usage['input'] == 12
    assert usage.summary()['request_count'] == 2
    assert usage.summary()['input_tokens'] == 22
    assert usage.summary()['output_tokens'] == 9


def test_gptoss_batch_and_review_http_paths_are_both_accounted(monkeypatch):
    from providers.gptoss import GPTOSSProvider
    from ai.ollama_provider import OllamaAnalysisProvider
    provider = GPTOSSProvider()
    provider._session.post = Mock(return_value=response({'message': {'content': '{"0":"Tubig"}'}, 'prompt_eval_count': 4, 'eval_count': 3}))
    monkeypatch.setattr('ai.ollama_provider.requests.post', Mock(return_value=response({'message': {'content': '{"score":90}'}, 'prompt_eval_count': 8, 'eval_count': 5})))
    analysis = OllamaAnalysisProvider(model='gemma4:31b')
    with usage_scope() as usage:
        provider._request_batch_chat([{'role': 'user', 'content': 'Water'}])
        call_with_purpose('quality_review', analysis.analyze, 'Return JSON', 'Review Tubig')
    summary = usage.summary()
    assert summary['request_count'] == 2
    assert summary['input_tokens'] == 12
    assert summary['output_tokens'] == 8
    assert summary['attempts'][1]['model'] == 'gemma4:31b'
    assert summary['attempts'][1]['purpose'] == 'quality_review'


def test_server_guard_keeps_usage_on_a_stopped_failed_run(monkeypatch):
    import server
    from providers.gptoss import GPTOSSProvider
    provider = GPTOSSProvider()
    provider._session.post = Mock(return_value=response({'error': 'quota exhausted'}, 429))
    with pytest.raises(server.UsageHTTPException) as error:
        server._run_pipeline_guarded(lambda: provider.translate('Water', 'English', 'Cebuano'))
    assert error.value.status_code == 429
    assert error.value.provider_usage['request_count'] == 1
    assert error.value.provider_usage['input_tokens'] is None


def test_fair_scheduler_propagates_usage_to_document_workers():
    from pipeline.fair_scheduler import document_batch_scheduler
    with usage_scope() as usage:
        future = document_batch_scheduler.submit('usage-test', lambda: provider_post(Mock(return_value=response({'prompt_eval_count': 2, 'eval_count': 3})), 'http://test', provider='gptoss', model='20b', purpose='translation'))
        future.result(timeout=5)
    assert usage.summary()['request_count'] == 1
    assert usage.summary()['input_tokens'] == 2


def test_ollama_cached_tokens_and_actual_model_are_preserved():
    with usage_scope() as usage:
        provider_post(Mock(return_value=response({'model': 'actual-model', 'prompt_eval_count': 11, 'prompt_eval_cached_count': 8, 'eval_count': 18, 'load_duration': 20})), 'http://test', provider='gptoss', model='requested-model', purpose='translation')
    attempt = usage.summary()['attempts'][0]
    assert attempt['model'] == 'actual-model'
    assert attempt['requested_model'] == 'requested-model'
    assert attempt['tokens']['cached_input'] == 8
    assert attempt['provider_timing_ns']['load_duration'] == 20


def test_server_lifespan_sends_no_startup_requests_and_initializes_no_cache(monkeypatch):
    import server
    import requests
    from cache.sqlite_cache import SQLiteTranslationCache
    from fastapi.testclient import TestClient
    post, get, cache = Mock(), Mock(), Mock(return_value=None)
    monkeypatch.setattr(requests.Session, 'post', post)
    monkeypatch.setattr(requests.Session, 'get', get)
    monkeypatch.setattr(SQLiteTranslationCache, '__init__', cache)
    monkeypatch.setenv('APP_ENV', 'testing')
    with TestClient(server.app): pass
    post.assert_not_called()
    get.assert_not_called()
    cache.assert_not_called()


def test_strict_run_stop_latch_blocks_the_next_case_before_http(monkeypatch):
    import provider_usage
    from providers.gptoss import GPTOSSProvider
    monkeypatch.setattr(provider_usage, '_run_stop_reason', None)
    monkeypatch.delenv('PROVIDER_STRICT_RUN', raising=False)
    provider = GPTOSSProvider()
    provider._session.post = Mock(return_value=response({'error': 'allowance exhausted'}, 429))
    with pytest.raises(ProviderStopped):
        with usage_scope():
            provider.translate('Water', 'English', 'Cebuano')
    with pytest.raises(ProviderStopped):
        with usage_scope():
            provider.translate('Next case', 'English', 'Filipino')
    assert provider._session.post.call_count == 1
