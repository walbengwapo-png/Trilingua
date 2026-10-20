"""No AI/network: test durable submission, authentication and worker failures."""
import io
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from document_jobs import DocumentJobStore, DocumentJobWorker, public_status


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-only-key")
    monkeypatch.setenv("SUPABASE_BUCKET", "test-only-bucket")
    return DocumentJobStore()


def test_same_submission_reuses_durable_id_without_upload_or_ai(store):
    id = str(uuid4())
    rows = []
    store.get = Mock(side_effect=lambda _: rows[0] if rows else None)
    store.put_object = Mock()
    def insert(*args, **kwargs):
        rows.append(dict(kwargs["json"], status="queued"))
        return SimpleNamespace(json=lambda: rows)
    store.request = Mock(side_effect=insert)
    first = store.submit(id, "first.txt", b"source", {"target_lang": "Filipino"})
    assert store.submit(id, "renamed.txt", b"source", {"target_lang": "Filipino"}) == first
    assert store.put_object.call_count == 1
    with pytest.raises(HTTPException) as error:
        store.submit(id, "first.txt", b"different", {"target_lang": "Filipino"})
    assert error.value.status_code == 409
    assert store.put_object.call_count == 1


def test_queue_refuses_public_bucket(store):
    store.request = Mock(return_value=SimpleNamespace(json=lambda: {"public": True}))
    with pytest.raises(RuntimeError, match="must be private"):
        store.verify()


def test_status_never_exposes_storage_paths_or_document_options():
    status = public_status({"id": "id", "status": "processing", "input_path": "private/path", "options": {"private": "text"}})
    assert "input_path" not in status and "options" not in status


def test_worker_persists_result_before_marking_complete(store, monkeypatch):
    import provider_usage
    monkeypatch.setattr(provider_usage, "_run_stop_reason", None)
    events = []
    store.read_object = Mock(return_value=b"source")
    store.put_object = Mock(side_effect=lambda *args: events.append("stored"))
    store.finish = Mock(side_effect=lambda *args, **kwargs: events.append(kwargs["status"]) or True)
    worker = DocumentJobWorker(store, Mock(return_value={"file_base64": "dHJhbnNsYXRlZA==", "blocks": []}))
    worker.run_one({"id": str(uuid4()), "lease_id": str(uuid4()), "input_path": "input", "filename": "source.txt", "options": {}})
    assert events == ["stored", "completed"]


def test_worker_records_an_existing_provider_stop_without_calling_translation(store, monkeypatch):
    import provider_usage
    monkeypatch.setattr(provider_usage, "_run_stop_reason", "Provider quota stopped")
    store.finish = Mock(return_value=True)
    translate = Mock()
    DocumentJobWorker(store, translate).run_one({"id": str(uuid4()), "lease_id": str(uuid4())})
    translate.assert_not_called()
    assert store.finish.call_args.kwargs["error_status"] == 429


def test_submission_returns_202_without_running_pipeline_and_requires_token(monkeypatch):
    import server
    monkeypatch.setenv("PYTHON_SERVICE_TOKEN", "test-token")
    store = Mock()
    store.submit.return_value = {"id": str(uuid4()), "status": "queued"}
    monkeypatch.setattr(server.app.state, "document_jobs", SimpleNamespace(store=store, wake=Mock()), raising=False)
    client = TestClient(server.app)
    data = {"job_id": store.submit.return_value["id"], "source_lang": "English", "target_lang": "Filipino"}
    files = {"file": ("source.txt", io.BytesIO(b"source"), "text/plain")}
    assert client.post("/translate/document/jobs", data=data, files=files).status_code == 401
    files = {"file": ("source.txt", io.BytesIO(b"source"), "text/plain")}
    response = client.post("/translate/document/jobs", data=data, files=files, headers={"X-Service-Token": "test-token"})
    assert response.status_code == 202 and response.json()["status"] == "queued"
    store.submit.assert_called_once()
