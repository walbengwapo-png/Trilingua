# -*- coding: utf-8 -*-
"""Service-token policy for the translation service (Gate 2).

Laravel reads PYTHON_SERVICE_TOKEN (config/translation.php) and presents it as
X-Service-Token. The engine must read the *same* variable name, and must not
serve production traffic unauthenticated.

These tests cover:
  1. The .env loader actually carries PYTHON_SERVICE_TOKEN into the process.
  2. The engine reads PYTHON_SERVICE_TOKEN (the name Laravel writes).
  3. A protected call is rejected with 401 when the token is absent or wrong.
  4. A configured token is accepted.
  5. APP_ENV=production without a token refuses to start (fails closed).
  6. Local and testing runs keep the opt-in behaviour they always had.
  7. The mutation/translation endpoints are actually wired to the dependency.
"""

import asyncio
import os

import pytest
from fastapi import HTTPException

from config.environment import load_engine_environment


# ---------------------------------------------------------------------------
# 1. The shared .env loader
# ---------------------------------------------------------------------------
def test_env_loader_carries_the_python_service_token(tmp_path, monkeypatch):
    """The loader must include the exact shared-token and environment keys.

    Without it the engine boots with no token in a deployment where Laravel
    has one, and every request is rejected.
    """
    monkeypatch.delenv("PYTHON_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=production\n"
        "PYTHON_SERVICE_TOKEN=s3cr3t-from-laravel-env\n",
        encoding="utf-8",
    )

    load_engine_environment(str(env_file))

    assert os.environ["PYTHON_SERVICE_TOKEN"] == "s3cr3t-from-laravel-env"
    # APP_ENV is loaded too, so the engine can tell it is not local.
    assert os.environ["APP_ENV"] == "production"


def test_env_loader_does_not_override_a_real_environment_variable(tmp_path, monkeypatch):
    """A variable already in the process environment outranks the .env file.

    This is what makes a Railway-injected token win over anything stale in a
    checked-in or mounted .env file.
    """
    monkeypatch.setenv("PYTHON_SERVICE_TOKEN", "injected-by-the-platform")

    env_file = tmp_path / ".env"
    env_file.write_text("PYTHON_SERVICE_TOKEN=stale-file-value\n", encoding="utf-8")

    load_engine_environment(str(env_file))

    assert os.environ["PYTHON_SERVICE_TOKEN"] == "injected-by-the-platform"


def test_env_loader_ignores_unrelated_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DB_PASSWORD=hunter2\n", encoding="utf-8")

    load_engine_environment(str(env_file))

    assert "DB_PASSWORD" not in os.environ


# ---------------------------------------------------------------------------
# 2-6. The engine policy
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def server_module():
    """Import the engine once. Heavy: it runs the warm-up path."""
    import server  # noqa: E402  (heavy import; runs warmup once)
    return server


@pytest.fixture
def clean_token_env(monkeypatch):
    """Remove every token variable so each test declares what it wants."""
    for key in ("PYTHON_SERVICE_TOKEN", "MODEL_SERVICE_TOKEN", "APP_ENV"):
        monkeypatch.delenv(key, raising=False)


def _enforce(server):
    server._enforce_startup_token_policy()


def _require(server, presented):
    """Invoke the FastAPI dependency and report the resulting status code."""
    try:
        asyncio.run(server.require_service_token(presented))
    except HTTPException as exc:
        return exc.status_code
    return 200


def test_engine_reads_the_same_variable_name_laravel_writes(server_module, clean_token_env):
    """The canonical name is PYTHON_SERVICE_TOKEN, matching config/translation.php."""
    clean_token_env  # noqa: B018  (applies the env cleanup)
    os.environ["PYTHON_SERVICE_TOKEN"] = "shared-secret"

    assert server_module._model_service_token() == "shared-secret"


def test_legacy_variable_still_works_for_existing_local_setups(server_module, clean_token_env):
    """MODEL_SERVICE_TOKEN is a local-compat fallback, not the deploy name."""
    clean_token_env  # noqa: B018
    os.environ["MODEL_SERVICE_TOKEN"] = "legacy-local"

    assert server_module._model_service_token() == "legacy-local"


def test_canonical_name_wins_over_the_legacy_fallback(server_module, clean_token_env):
    clean_token_env  # noqa: B018
    os.environ["PYTHON_SERVICE_TOKEN"] = "canonical"
    os.environ["MODEL_SERVICE_TOKEN"] = "legacy"

    assert server_module._model_service_token() == "canonical"


def test_configured_token_rejects_a_caller_with_no_header(server_module, clean_token_env):
    clean_token_env  # noqa: B018
    os.environ["PYTHON_SERVICE_TOKEN"] = "shared-secret"

    assert _require(server_module, None) == 401


def test_configured_token_rejects_a_wrong_token(server_module, clean_token_env):
    clean_token_env  # noqa: B018
    os.environ["PYTHON_SERVICE_TOKEN"] = "shared-secret"

    assert _require(server_module, "not-the-secret") == 401


def test_configured_token_admits_the_matching_caller(server_module, clean_token_env):
    clean_token_env  # noqa: B018
    os.environ["PYTHON_SERVICE_TOKEN"] = "shared-secret"

    assert _require(server_module, "shared-secret") == 200


def test_production_without_a_token_refuses_to_start(server_module, clean_token_env):
    """This is the fail-closed guarantee: no token means no production service."""
    clean_token_env  # noqa: B018
    os.environ["APP_ENV"] = "production"

    with pytest.raises(RuntimeError, match="PYTHON_SERVICE_TOKEN"):
        _enforce(server_module)


def test_production_does_not_accept_the_legacy_local_token(server_module, clean_token_env):
    clean_token_env  # noqa: B018
    os.environ["APP_ENV"] = "production"
    os.environ["MODEL_SERVICE_TOKEN"] = "legacy-local"

    with pytest.raises(RuntimeError, match="PYTHON_SERVICE_TOKEN"):
        _enforce(server_module)


def test_production_with_a_token_starts(server_module, clean_token_env):
    clean_token_env  # noqa: B018
    os.environ["APP_ENV"] = "production"
    os.environ["PYTHON_SERVICE_TOKEN"] = "shared-secret"

    _enforce(server_module)  # must not raise


@pytest.mark.parametrize("app_env", ["local", "testing", "development", ""])
def test_non_production_still_starts_without_a_token(server_module, clean_token_env, app_env):
    """Local and test workflows must keep working with no token configured."""
    clean_token_env  # noqa: B018
    if app_env:
        os.environ["APP_ENV"] = app_env

    _enforce(server_module)  # must not raise
    # ...and an unconfigured service keeps its historical open behaviour.
    assert _require(server_module, None) == 200


def test_production_dependency_fails_closed_even_if_config_is_lost(server_module, clean_token_env):
    """Startup already refuses to boot, but never serve open if it is reached.

    If the process somehow loses its configuration mid-flight the dependency
    must not fall back to the open behaviour.
    """
    clean_token_env  # noqa: B018
    os.environ["APP_ENV"] = "production"

    assert _require(server_module, "anything") == 503


def test_every_mutating_endpoint_is_actually_protected(server_module, clean_token_env):
    """Guards against a future route being added without the dependency.

    /health is intentionally excluded: it stays open for monitoring.
    """
    clean_token_env  # noqa: B018

    guard = server_module.require_service_token
    expected = {
        ("POST", "/translate/text"),
        ("POST", "/translate/document"),
        ("POST", "/translate/document/regenerate"),
        ("DELETE", "/cache/clear"),
    }

    protected = set()
    for route in server_module.app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        if path not in {p for _, p in expected}:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            calls = [d.call for d in getattr(route, "dependant", None).dependencies] if getattr(route, "dependant", None) else []
            if guard in calls:
                protected.add((method, path))

    assert protected == expected
