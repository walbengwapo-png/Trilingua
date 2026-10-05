"""Offline regressions for F15: import safety and terminal Ollama errors."""
import os
import subprocess
import sys
from unittest.mock import Mock
import pytest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_server_import_does_not_initialize_cache_or_contact_provider():
    code = """
from unittest.mock import patch
import requests
from cache.sqlite_cache import SQLiteTranslationCache
with patch.object(requests.Session, 'post') as post, patch.object(requests.Session, 'get') as get, patch.object(SQLiteTranslationCache, '__init__', return_value=None) as cache:
    import server
    assert post.call_count == 0, post.call_count
    assert get.call_count == 0, get.call_count
    assert cache.call_count == 0, cache.call_count
"""
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.environ.get('PYTHONPATH',''), str(__import__('pathlib').Path('Model').resolve())]))
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stdout + result.stderr


def test_warmup_requires_explicit_opt_in(monkeypatch):
    from providers.gptoss import GPTOSSProvider
    monkeypatch.delenv('ALLOW_PROVIDER_WARMUP', raising=False)
    provider = GPTOSSProvider()
    provider._session.post = Mock()
    assert provider.warmup() is False
    provider._session.post.assert_not_called()


@pytest.mark.parametrize('status', [401, 403, 429])
def test_ollama_terminal_status_never_retries_or_falls_back(monkeypatch, status):
    from providers.gptoss import GPTOSSProvider
    from providers.fallback import FallbackTranslationProvider
    from provider_usage import ProviderStopped, usage_scope
    monkeypatch.setenv('GPTOSS_MAX_ATTEMPTS', '3')
    primary = GPTOSSProvider()
    response = Mock(status_code=status)
    response.json.return_value = {'error': 'allowance exhausted'}
    primary._session.post = Mock(return_value=response)
    fallback = Mock()
    route = FallbackTranslationProvider(primary, fallback)
    with pytest.raises(ProviderStopped):
        with usage_scope() as usage:
            with pytest.raises(ProviderStopped):
                route.translate('Hello', 'English', 'Cebuano')
            with pytest.raises(ProviderStopped):
                primary.translate('Hello again', 'English', 'Cebuano')
    assert primary._session.post.call_count == 1
    fallback.translate.assert_not_called()
