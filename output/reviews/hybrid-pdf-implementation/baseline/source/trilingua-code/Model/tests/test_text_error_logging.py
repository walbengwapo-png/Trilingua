"""Unexpected text failures retain a traceback without logging source text."""
import logging

import pytest
from fastapi import HTTPException


def test_unexpected_text_failure_logs_traceback(monkeypatch, caplog):
    import server

    def fail(_operation):
        raise RuntimeError("simulated pipeline failure")

    monkeypatch.setattr(server, "_run_pipeline_guarded", fail)
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        with pytest.raises(HTTPException) as caught:
            server.translate_text(server.TextRequest(
                text="Private source text must not appear in the log",
                source_lang="English", target_lang="Cebuano", mode="fast",
            ))
    assert caught.value.status_code == 500
    assert "Text translation failed" in caplog.text
    assert "RuntimeError: simulated pipeline failure" in caplog.text
    assert "Private source text" not in caplog.text
