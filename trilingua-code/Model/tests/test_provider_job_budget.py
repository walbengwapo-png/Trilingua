"""No sockets: inspect transport timeouts on mocked provider calls."""
from types import SimpleNamespace
from unittest.mock import Mock
import time
import pytest
from providers.request_budget import request_deadline,transport_timeout,retry_sleep


@pytest.mark.parametrize('provider',['gemini','gptoss','gemini_analysis','ollama_analysis'])
def test_every_transport_uses_remaining_pdf_budget(monkeypatch,provider):
    if provider=='gemini':
        from providers.gemini import GeminiProvider
        instance=GeminiProvider(api_key='TEST-NOT-A-KEY',model='gemini-2.5-flash');response={'candidates':[{'content':{'parts':[{'text':'Target'}]}}]}
        post=Mock();monkeypatch.setattr(instance._session,'post',post)
        call=lambda:instance.translate('Source','English','Cebuano')
    elif provider=='gptoss':
        from providers.gptoss import GPTOSSProvider
        instance=GPTOSSProvider();post=Mock();monkeypatch.setattr(instance._session,'post',post)
        response={'message':{'content':'Target'}};call=lambda:instance.translate('Source','English','Cebuano')
    else:
        import requests
        if provider=='gemini_analysis':
            from ai.gemini_provider import GeminiAnalysisProvider
            instance=GeminiAnalysisProvider(api_key='TEST-NOT-A-KEY',model='gemini-2.5-flash')
            response={'candidates':[{'content':{'parts':[{'text':'{}'}]}}]}
        else:
            from ai.ollama_provider import OllamaAnalysisProvider
            instance=OllamaAnalysisProvider();response={'message':{'content':'{}'}}
        post=Mock();monkeypatch.setattr(requests,'post',post)
        call=lambda:instance.analyze('System','Source')
    post.return_value=SimpleNamespace(status_code=200,json=lambda:response,raise_for_status=lambda:None)
    with request_deadline(time.monotonic()+.5):call()
    timeout=post.call_args.kwargs['timeout']
    assert 0<timeout.total<=.500001 and timeout.connect_timeout<=.500001
    post.reset_mock()
    with request_deadline(time.monotonic()-1):
        with pytest.raises(TimeoutError):call()
    post.assert_not_called()


def test_budget_is_nested_request_local_and_retry_cannot_sleep_past_deadline():
    assert transport_timeout(10,30)==(10,30)
    with request_deadline(time.monotonic()+.1):
        with pytest.raises(TimeoutError):retry_sleep(1)
        with request_deadline(None):assert transport_timeout(10,30)==(10,30)
        assert transport_timeout(10,30).total<=.100001
    assert transport_timeout(10,30)==(10,30)
