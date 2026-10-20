"""Requests must be visible before processing, without recording their contents."""
import asyncio
import logging

import pytest
from starlette.requests import Request
from starlette.responses import Response


@pytest.mark.parametrize("path,status", [
    ("/translate/text", 200),
    ("/translate/document", 500),
    ("/translate/document/regenerate", 401),
])
def test_translation_logs_before_processing_and_reports_status(path, status, caplog):
    import server

    request = Request({"type": "http", "method": "POST", "path": path,
                       "headers": [], "query_string": b"secret=private"})

    async def process(_request):
        assert "Translation request received" in caplog.text
        return Response(status_code=status)

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        response = asyncio.run(server.log_translation_request(request, process))
    assert response.status_code == status
    assert f"status={status}" in caplog.text
    assert "private" not in caplog.text


def test_unexpected_request_failure_is_logged_and_propagated(caplog):
    import server

    request = Request({"type": "http", "method": "POST", "path": "/translate/text",
                       "headers": [], "query_string": b""})

    async def fail(_request):
        raise RuntimeError("simulated failure")

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        with pytest.raises(RuntimeError, match="simulated failure"):
            asyncio.run(server.log_translation_request(request, fail))
    assert "Translation request failed" in caplog.text
