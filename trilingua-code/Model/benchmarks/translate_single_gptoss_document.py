"""Translate one ad-hoc document through an already isolated GPT-OSS server."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

from evaluate_test_folder import output_structure, pdf_page_count, post_document, sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--target", required=True, choices=("Filipino", "Cebuano"))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--server-url", default="http://127.0.0.1:5001")
    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"Input PDF not found: {args.input}")
    health = requests.get(f"{args.server_url.rstrip('/')}/health", timeout=20).json()
    fallback = health.get("fallback_provider")
    if health.get("active_provider") != "gptoss" or fallback not in (None, "", "none"):
        raise SystemExit("Refusing translation: server is not isolated GPT-OSS with fallback disabled.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    code = "fil" if args.target == "Filipino" else "ceb"
    output_path = args.output_dir / f"{args.input.stem}__en-to-{code}.pdf"
    payload, file_bytes, elapsed_ms = post_document(args.server_url, args.input, args.target)
    result = {
        "source": str(args.input),
        "source_sha256": sha256(args.input),
        "target_language": args.target,
        "provider": "gptoss",
        "model": health.get("model"),
        "fallback_disabled": True,
        "cache_disabled": True,
        "mode": "fast",
        "elapsed_ms": elapsed_ms,
        "status": "completed" if file_bytes else "failed",
        "engine_response": {
            key: value for key, value in payload.items()
            if key not in {"file_base64", "blocks", "sidecar"}
        },
    }
    if file_bytes:
        output_path.write_bytes(file_bytes)
        result.update({
            "output_path": str(output_path),
            "output_sha256": sha256(output_path),
            "output_bytes": output_path.stat().st_size,
            "structure": output_structure(output_path, pdf_page_count(args.input)),
        })
    (args.output_dir / "translation-metadata.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
