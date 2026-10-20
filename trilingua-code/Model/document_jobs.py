"""Durable document queue in the existing Supabase database and private bucket."""
import hashlib
import io
import json
import logging
import os
import threading
import time
from uuid import UUID

import requests
from fastapi import HTTPException, UploadFile

log = logging.getLogger("uvicorn.error")
MAX_INPUT_BYTES = 50 * 1024 * 1024


class DocumentJobStore:
    def __init__(self):
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.bucket = os.environ.get("SUPABASE_BUCKET", "")
        if not self.url.startswith("https://") or not self.key or not self.bucket:
            raise RuntimeError("Document jobs require SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and SUPABASE_BUCKET")

    def request(self, method, path, **kwargs):
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
        headers.update(kwargs.pop("headers", {}))
        response = requests.request(method, self.url + path, headers=headers,
                                    timeout=(3, 10), allow_redirects=False, **kwargs)
        if not response.ok:
            # Do not echo provider URLs, credentials or document content in errors.
            raise HTTPException(503, f"Document job storage unavailable (HTTP {response.status_code})")
        return response

    def verify(self):
        bucket = self.request("GET", f"/storage/v1/bucket/{self.bucket}").json()
        if bucket.get("public") is not False:
            raise RuntimeError("The document job bucket must be private")
        self.request("GET", "/rest/v1/python_document_jobs", params={"select": "id", "limit": 0})

    def get(self, job_id):
        rows = self.request("GET", "/rest/v1/python_document_jobs",
                            params={"id": f"eq.{job_id}", "select": "*"}).json()
        return rows[0] if rows else None

    def put_object(self, path, contents, content_type):
        # Paths include the payload hash or lease UUID; never overwrite another payload.
        response = requests.post(f"{self.url}/storage/v1/object/{self.bucket}/{path}",
                                 headers={"apikey": self.key, "Authorization": f"Bearer {self.key}",
                                          "Content-Type": content_type, "x-upsert": "false"},
                                 data=contents, timeout=(3, 10), allow_redirects=False)
        if not response.ok and response.status_code not in (400, 409):
            raise HTTPException(503, "Could not durably store the document job file")
        if not response.ok:
            error = response.json()
            if str(error.get("statusCode")) != "409" and error.get("error") != "Duplicate":
                raise HTTPException(503, "Could not durably store the document job file")

    def read_object(self, path):
        return self.request("GET", f"/storage/v1/object/authenticated/{self.bucket}/{path}").content

    def submit(self, job_id, filename, contents, options):
        job_id = str(UUID(str(job_id)))
        ext = os.path.splitext(filename)[1].lower()
        fingerprint = hashlib.sha256(contents + json.dumps({"extension": ext, "options": options}, sort_keys=True).encode()).hexdigest()
        existing = self.get(job_id)
        if existing:
            if existing["fingerprint"] != fingerprint:
                raise HTTPException(409, "Job ID already belongs to a different document request")
            return existing
        input_path = f"engine-jobs/{job_id}/{fingerprint}/input{ext}"
        self.put_object(input_path, contents, "application/octet-stream")
        rows = self.request("POST", "/rest/v1/python_document_jobs",
                            params={"on_conflict": "id"},
                            headers={"Prefer": "resolution=ignore-duplicates,return=representation"},
                            json={"id": job_id, "filename": filename, "fingerprint": fingerprint,
                                  "input_path": input_path, "options": options}).json()
        row = rows[0] if rows else self.get(job_id)
        if not row or row["fingerprint"] != fingerprint:
            raise HTTPException(409, "Job ID already belongs to a different document request")
        return row

    def claim(self):
        rows = self.request("POST", "/rest/v1/rpc/claim_python_document_job", json={}).json()
        return rows[0] if rows else None

    def renew(self, row):
        return self.request("POST", "/rest/v1/rpc/renew_python_document_job",
                            json={"job_id": row["id"], "lease_id": row["lease_id"]}).json() is True

    def finish(self, row, **changes):
        return self.request("POST", "/rest/v1/rpc/finish_python_document_job",
                            json={"job_id": row["id"], "lease_id": row["lease_id"],
                                  "result_path": changes.get("result_path"), "error": changes.get("error"),
                                  "error_status": changes.get("error_status")}).json() is True

    def acknowledge(self, row):
        # ponytail: failed/unacknowledged files need operator cleanup; add TTL cleanup before storage quota becomes tight.
        if row["status"] != "completed":
            raise HTTPException(409, "Only completed document jobs can be acknowledged")
        paths = [path for path in (row["input_path"], row.get("result_path")) if path]
        if paths:
            self.request("DELETE", f"/storage/v1/object/{self.bucket}", json={"prefixes": paths})
        self.request("PATCH", "/rest/v1/python_document_jobs", params={"id": f"eq.{row['id']}"},
                     json={"acknowledged": True})


def public_status(row):
    return {key: row.get(key) for key in ("id", "status", "error", "error_status", "acknowledged")}


class DocumentJobWorker:
    def __init__(self, store, translate):
        self.store, self.translate = store, translate
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self.run, name="document-jobs", daemon=True)

    def run_one(self, row):
        from provider_usage import usage_scope
        done = threading.Event()
        monitor = None
        try:
            with usage_scope() as usage:
                def heartbeat():
                    while not done.wait(20):
                        try:
                            alive = self.store.renew(row)
                        except Exception:
                            alive = False
                        if not alive:
                            usage.stop_reason = "Document worker lost its durable lease or exceeded its deadline; no further AI calls permitted"
                            return
                monitor = threading.Thread(target=heartbeat, name="document-heartbeat", daemon=True)
                monitor.start()
                contents = self.store.read_object(row["input_path"])
                if len(contents) > MAX_INPUT_BYTES:
                    raise HTTPException(413, "Document exceeds the 50 MiB limit")
                with io.BytesIO(contents) as stream:
                    result = self.translate(file=UploadFile(filename=row["filename"], file=stream), **row["options"])
                usage.check()
                result_path = f"engine-jobs/{row['id']}/{row['lease_id']}/result.json"
                self.store.put_object(result_path, json.dumps(result).encode(), "application/json")
                if not self.store.finish(row, status="completed", result_path=result_path):
                    log.warning("Document result refused after lease loss: %s", row["id"])

        except Exception as error:
            from provider_usage import ProviderStopped
            status = 429 if isinstance(error, ProviderStopped) else error.status_code if isinstance(error, HTTPException) else 500
            detail = str(error) if isinstance(error, ProviderStopped) else error.detail if isinstance(error, HTTPException) else "Document background processing failed"
            if not isinstance(detail, str):
                detail = json.dumps(detail)
            self.store.finish(row, status="failed", error=detail[:2000], error_status=status)
        finally:
            done.set()
            if monitor:
                monitor.join(timeout=30)

    def run(self):
        while not self.stop.is_set():
            try:
                row = self.store.claim()
                if row:
                    self.run_one(row)
                    continue
            except Exception:
                log.exception("Document background worker could not access its durable queue")
            self.wake.wait(5)
            self.wake.clear()
