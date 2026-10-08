"""Rerun only the user-requested GPT-OSS English-to-Cebuano SONA case.

This preserves already-recorded iteration evidence and intentionally does not
run the separate three-repeat stability protocol.
"""

from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

import requests

from evaluate_test_folder import (
    SONA_SOURCE,
    TARGETS,
    TEST_ROOT,
    output_structure,
    pdf_page_count,
    post_document,
    score_sona,
    sha256,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", default="http://127.0.0.1:5001")
    args = parser.parse_args()

    iteration_dir = TEST_ROOT / "iteration-2-gptoss"
    findings_path = iteration_dir / "findings.json"
    if not findings_path.is_file():
        raise SystemExit(f"Missing existing findings: {findings_path}")

    health = requests.get(f"{args.server_url.rstrip('/')}/health", timeout=20).json()
    if health.get("active_provider") != "gptoss" or health.get("fallback_provider"):
        raise SystemExit("Refusing rerun: server is not isolated GPT-OSS with fallback disabled.")

    data = json.loads(findings_path.read_text(encoding="utf-8"))
    output_path = iteration_dir / "translated-files" / "SONA_2019_English__en-to-ceb.pdf"
    payload, file_bytes, elapsed_ms = post_document(args.server_url, SONA_SOURCE, "Cebuano")
    record = {
        "source": SONA_SOURCE.name,
        "source_sha256": sha256(SONA_SOURCE),
        "target_language": "Cebuano",
        "output_path": str(output_path),
        "elapsed_ms": elapsed_ms,
        "status": "completed" if file_bytes else "failed",
        "engine_response": {
            key: value for key, value in payload.items()
            if key not in {"file_base64", "blocks", "sidecar"}
        },
        "rerun_reason": "User-requested completion of previously stopped SONA Cebuano GPT-OSS case.",
    }
    if file_bytes:
        output_path.write_bytes(file_bytes)
        record["output_sha256"] = sha256(output_path)
        record["output_bytes"] = output_path.stat().st_size
        record["structure"] = output_structure(output_path, pdf_page_count(SONA_SOURCE))
        record["quality"] = score_sona(output_path, "Cebuano")
    else:
        record["quality"] = {"bleu": None, "chrf": None, "note": "Translation failed"}

    data["health"] = health
    data["full_runs"] = [
        row for row in data["full_runs"]
        if not (row["source"] == SONA_SOURCE.name and row["target_language"] == "Cebuano")
    ]
    data["full_runs"].append(record)
    write_json(findings_path, data)

    metadata_path = iteration_dir / "run-metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    metadata.update({
        "provider": "gptoss",
        "model": health.get("model"),
        "execution_status": "partial: SONA Cebuano rerun completed; GPT-OSS stability not run",
        "completed_full_runs": len(data["full_runs"]),
        "planned_full_runs": 4,
        "stability_runs_completed": 0,
        "last_rerun": {
            "source": SONA_SOURCE.name,
            "target": "Cebuano",
            "status": record["status"],
            "elapsed_ms": elapsed_ms,
        },
    })
    write_json(metadata_path, metadata)
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
