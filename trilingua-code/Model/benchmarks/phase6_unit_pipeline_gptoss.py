# -*- coding: utf-8 -*-
"""
Phase 5-6 GPT-OSS-only acceptance benchmark for the DTO unit pipeline.

Runs the Part2 source documents through the REAL FastAPI server in BOTH
directions, 3 runs each, with TRANSLATION_UNIT_PIPELINE=true and the
translation cache disabled (balanced mode, GPT-OSS only, no NLLB/Gemini).

The server is launched by this script unless --server-url is supplied. The
flag is read once at server startup, so the environment must be set before
the process boots — this script does exactly that.

For every run we persist: the output PDF, its SHA-256, the full engine
response (metrics + sidecar + block review), wall time, phase times,
provider time, scheduler wait/batches, batch item count, retries, failures,
span checks, page structure and layout render samples, plus corpus BLEU/chrF
against the sister-language reference PDF.

A single go/no-go acceptance report is written at the end.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import signal
import socketserver
import statistics
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import fitz

try:
    from sacrebleu import corpus_bleu, corpus_chrf
except Exception:  # pragma: no cover
    corpus_bleu = corpus_chrf = None


ENGINE_DIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
PART2 = ROOT / "chatgpt" / "Part2 test"
RESULTS = PART2 / "phase-6-unit-pipeline-gptoss"
SAMPLES = RESULTS / "layout-samples"

PAIRS = (
    {
        "id": "en-to-ceb",
        "source": PART2 / "60 Heaven  God s Beautiful Home.pdf",
        "reference": PART2 / "60 Langit  Ang Nindot nga Puluy-anan sa Dios.pdf",
        "source_language": "English",
        "target_language": "Cebuano",
    },
    {
        "id": "ceb-to-en",
        "source": PART2 / "60 Langit  Ang Nindot nga Puluy-anan sa Dios.pdf",
        "reference": PART2 / "60 Heaven  God s Beautiful Home.pdf",
        "source_language": "Cebuano",
        "target_language": "English",
    },
)

UNIT_METRIC_KEYS = ("provider_request_ms", "provider_retries", "provider_failures",
                    "layout_preflight_blocks", "blocks_batched", "blocks_translated")
SAMPLE_PAGES = (0, 1, 13)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pdf_text(path: Path) -> str:
    with fitz.open(path) as document:
        return " ".join(
            " ".join(page.get_text("text").split()) for page in document
        ).strip()


def pdf_structure(path: Path, expected_pages: int) -> dict:
    try:
        with fitz.open(path) as document:
            pages = len(document)
        text = pdf_text(path)
        return {
            "page_count": pages,
            "text_characters": len(text),
            "non_empty_text": bool(text),
            "page_count_matches_source": pages == expected_pages,
            "layout_validation": "pass" if text and pages == expected_pages else "fail",
        }
    except Exception as error:
        return {"page_count": None, "text_characters": 0, "non_empty_text": False,
                "page_count_matches_source": False, "layout_validation": "fail",
                "error": str(error)}


def score(output: Path, reference: Path) -> dict:
    if corpus_bleu is None:
        return {"bleu": None, "chrf": None, "note": "sacrebleu unavailable"}
    hypothesis = pdf_text(output)
    expected = pdf_text(reference)
    if not hypothesis or not expected:
        return {"bleu": None, "chrf": None, "note": "Text extraction was empty"}
    return {
        "bleu": round(corpus_bleu([hypothesis], [[expected]]).score, 2),
        "chrf": round(corpus_chrf([hypothesis], [[expected]]).score, 2),
        "hypothesis_characters": len(hypothesis),
        "reference_characters": len(expected),
        "normalization": "all pages; whitespace collapsed; no content removed",
    }


_EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
_URL_RE = r"https?://[^\s)]+"
_NUMBER_RE = r"(?<!\d)\d{2,}(?:[.,]\d+)*(?!\d)"
_PLACEHOLDER_RE = r"\{\w+\}"


def span_checks(source: Path, output: Path) -> dict:
    """Best-effort protected-span survival check over extracted text."""
    src = pdf_text(source)
    out = pdf_text(output)
    if corpus_bleu is None:
        return {}
    import re
    checks = {}
    for label, pattern in (("emails", _EMAIL_RE), ("urls", _URL_RE),
                           ("numbers", _NUMBER_RE), ("placeholders", _PLACEHOLDER_RE)):
        expected = set(re.findall(pattern, src))
        found = set(re.findall(pattern, out))
        missing = sorted(expected - found)
        checks[label] = {
            "expected_count": len(expected),
            "missing_count": len(missing),
            "missing": missing[:20],
        }
    return checks


def render_samples(path: Path, tag: str) -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    with fitz.open(path) as document:
        for page_index in SAMPLE_PAGES:
            if page_index >= len(document):
                continue
            pix = document[page_index].get_pixmap(dpi=72)
            pix.save(str(SAMPLES / f"{tag}_page{page_index + 1}.png"))


def post_document(server_url: str, pair: dict, mode: str) -> tuple[dict, bytes | None, float]:
    started = time.perf_counter()
    req = urllib.request.Request(
        f"{server_url.rstrip('/')}/translate/document",
        method="POST",
    )
    boundary = "----phase6benchmark"
    preamble = f"--{boundary}\r\n"
    file_part = (
        f"Content-Disposition: form-data; name=\"file\"; "
        f"filename=\"{pair['source'].name}\"\r\nContent-Type: application/pdf\r\n\r\n"
    )
    fields = [
        ("source_lang", pair["source_language"]),
        ("target_lang", pair["target_language"]),
        ("mode", mode),
        ("pdf_column_mode", "auto"),
    ]
    body = b""
    for name, value in fields:
        body += preamble.encode()
        body += f"Content-Disposition: form-data; name=\"{name}\"\r\n\r\n".encode()
        body += value.encode() + b"\r\n"
    body += preamble.encode() + file_part.encode()
    body += pair["source"].read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, data=body, timeout=7200) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as error:
        return {"status": 500, "error": str(error)[:2000]}, None, round((time.perf_counter() - started) * 1000, 2)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    file_base64 = payload.get("file_base64", "")
    if not file_base64:
        return payload, None, elapsed_ms
    return payload, base64.b64decode(file_base64), elapsed_ms


def wait_for_health(server_url: str, timeout_seconds: int = 120) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{server_url.rstrip('/')}/health", timeout=10) as resp:
                health = json.loads(resp.read().decode("utf-8"))
            if health.get("status") == "ok":
                return health
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit(f"Server at {server_url} did not become healthy within {timeout_seconds}s")


def find_free_port() -> int:
    with socketserver.TCPServer(("127.0.0.1", 0), None) as server:
        return server.server_address[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-url", default="")
    parser.add_argument("--mode", default="balanced")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    for pair in PAIRS:
        for path in (pair["source"], pair["reference"]):
            if not path.is_file():
                raise SystemExit(f"Missing Part2 evaluation file: {path}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    SAMPLES.mkdir(parents=True, exist_ok=True)

    server_url = args.server_url.rstrip("/") or ""
    server_process = None

    if not server_url:
        port = find_free_port()
        server_url = f"http://127.0.0.1:{port}"
        env = dict(os.environ)
        env["TRANSLATION_UNIT_PIPELINE"] = "true"
        env["TRANSLATION_CACHE_ENABLED"] = "false"
        env["TRANSLATION_FALLBACK_PROVIDER"] = "gptoss"
        env["TRANSLATION_PORT"] = str(port)
        env["MODEL_SERVICE_RELOAD"] = "false"
        log_path = RESULTS / "server.log"
        log_handle = log_path.open("w", encoding="utf-8")
        server_process = subprocess.Popen(
            [sys.executable, "server.py"],
            cwd=str(ENGINE_DIR),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        try:
            health = wait_for_health(server_url)
        except Exception:
            log_handle.close()
            raise

    health = wait_for_health(server_url)
    if health.get("active_provider") != "gptoss":
        raise SystemExit(f"Expected active GPT-OSS provider, received {health.get('active_provider')!r}.")
    if health.get("fallback_provider"):
        raise SystemExit("Evaluation server has a fallback provider configured; refusing a mixed run.")

    engine_config = {
        "model": health.get("model"),
        "active_provider": health.get("active_provider"),
        "provider_status": health.get("provider_status"),
        "analysis_status": health.get("analysis_status"),
        "unit_pipeline_flag": os.environ.get("TRANSLATION_UNIT_PIPELINE", "<unset>"),
        "translation_cache_enabled": os.environ.get("TRANSLATION_CACHE_ENABLED", "<unset>"),
        "gptoss_slots": os.environ.get("GPTOSS_TRANSLATION_SLOTS", "8"),
        "gptoss_model": os.environ.get("OLLAMA_CLOUD_MODEL", "gpt-oss:20b-cloud"),
    }

    manifest = {
        "schema_version": 2,
        "title": "Phase 6 — GPT-OSS-only DTO unit pipeline acceptance benchmark",
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "gptoss",
        "model": engine_config["model"],
        "server_url": server_url,
        "processing_mode": args.mode,
        "translation_fallback_disabled": True,
        "translation_cache_disabled": True,
        "translation_unit_pipeline": True,
        "repetitions_per_direction": args.runs,
        "pairs": [
            {
                "id": pair["id"],
                "source_path": str(pair["source"]),
                "source_sha256": sha256(pair["source"]),
                "reference_path": str(pair["reference"]),
                "reference_sha256": sha256(pair["reference"]),
                "source_language": pair["source_language"],
                "target_language": pair["target_language"],
                "source_structure": pdf_structure(pair["source"], 25),
            }
            for pair in PAIRS
        ],
        "score_method": "Corpus BLEU and chrF over all PDF pages after whitespace normalization only.",
    }
    write_json(RESULTS / "benchmark-manifest.json", manifest)

    findings = {
        "schema_version": 2,
        "title": manifest["title"],
        "generated_at": manifest["generated_at"],
        "provider": "gptoss",
        "health": health,
        "engine_config": engine_config,
        "manifest_path": str(RESULTS / "benchmark-manifest.json"),
        "runs": [],
    }

    for pair in PAIRS:
        for run_number in range(1, args.runs + 1):
            output_path = RESULTS / f"{pair['id']}_run{run_number}.pdf"
            payload, bytes_out, elapsed = post_document(server_url, pair, args.mode)
            record = {
                "id": pair["id"],
                "run": run_number,
                "source_language": pair["source_language"],
                "target_language": pair["target_language"],
                "status": "completed" if bytes_out else "failed",
                "elapsed_ms": elapsed,
            }
            if payload.get("status") == 500 or not bytes_out:
                record["error"] = payload.get("error") or "No file in response"
                findings["runs"].append(record)
                write_json(RESULTS / "findings.json", findings)
                continue
            output_path.write_bytes(bytes_out)
            block_count = len(payload.get("blocks") or [])
            metrics = payload.get("metrics") or {}
            record.update({
                "output_path": str(output_path),
                "output_sha256": sha256(output_path),
                "output_bytes": output_path.stat().st_size,
                "structure": pdf_structure(output_path, 25),
                "quality": score(output_path, pair["reference"]),
                "span_checks": span_checks(pair["source"], output_path),
                "blocks": block_count,
                "metrics": metrics,
                "engine_total_time_ms": metrics.get("total_time_ms"),
                "provider_request_ms": metrics.get("provider_request_ms"),
                "provider_retries": metrics.get("provider_retries"),
                "provider_failures": metrics.get("provider_failures"),
                "scheduler_wait_ms": metrics.get("scheduler_wait_ms"),
                "scheduler_batches": metrics.get("scheduler_batches"),
                "scheduler_slots": metrics.get("scheduler_slots"),
                "blocks_translated": metrics.get("blocks_translated"),
                "blocks_batched": metrics.get("blocks_batched"),
                "layout_preflight_blocks": metrics.get("layout_preflight_blocks"),
                "echo_retries": metrics.get("echo_retries"),
                "llm_calls": metrics.get("llm_calls"),
                "phase_times": metrics.get("phase_times"),
                "download_filename": payload.get("download_filename"),
            })
            missing_unit_keys = sorted(
                key for key in UNIT_METRIC_KEYS
                if key not in metrics or metrics.get(key) is None
            )
            if missing_unit_keys:
                record["unit_pipeline_verification"] = {
                    "pass": False,
                    "missing_metric_keys": missing_unit_keys,
                }
            else:
                record["unit_pipeline_verification"] = {"pass": True}
            render_samples(output_path, f"{pair['id']}_run{run_number}") if record["status"] == "completed" else None
            findings["runs"].append(record)
            write_json(RESULTS / "findings.json", findings)
            print(f"[benchmark] {pair['id']} run {run_number}: {record['status']} "
                  f"elapsed={elapsed}ms bleu={record.get('quality', {}).get('bleu')} "
                  f"charts={record['structure'].get('layout_validation')}", flush=True)

    if server_process is not None:
        try:
            server_process.send_signal(signal.CTRL_BREAK_EVENT)
        except Exception:
            try:
                server_process.terminate()
            except Exception:
                pass
        try:
            server_process.wait(timeout=20)
        except Exception:
            server_process.kill()

    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "gptoss",
        "model": health.get("model"),
        "engine_config": engine_config,
        "manifest_sha256": sha256(RESULTS / "benchmark-manifest.json"),
        "findings_sha256": sha256(RESULTS / "findings.json"),
        "full_run_count": len(findings["runs"]),
        "runs_per_direction": args.runs,
    }
    write_json(RESULTS / "run-metadata.json", metadata)
    print(json.dumps(findings, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()