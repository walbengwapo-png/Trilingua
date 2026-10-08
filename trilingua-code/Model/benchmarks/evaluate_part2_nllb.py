"""Run the isolated NLLB Part2 evaluation without modifying supplied PDFs."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import fitz
import requests
from sacrebleu import corpus_bleu, corpus_chrf


ROOT = Path(__file__).resolve().parents[3]
PART2 = ROOT / "chatgpt" / "Part2 test"
ITERATION = PART2 / "iteration-1-nllb-200-600m"
OUTPUTS = ITERATION / "translated-files"
PAIRS = (
    {
        "id": "en-to-ceb",
        "source": PART2 / "60 Heaven  God s Beautiful Home.pdf",
        "reference": PART2 / "60 Langit  Ang Nindot nga Puluy-anan sa Dios.pdf",
        "source_language": "English",
        "target_language": "Cebuano",
        "gptoss_output": PART2 / "gpt-oss" / "e598d3ff-796c-4e07-890c-3b8be50b0875.pdf",
    },
    {
        "id": "ceb-to-en",
        "source": PART2 / "60 Langit  Ang Nindot nga Puluy-anan sa Dios.pdf",
        "reference": PART2 / "60 Heaven  God s Beautiful Home.pdf",
        "source_language": "Cebuano",
        "target_language": "English",
        "gptoss_output": PART2 / "gpt-oss" / "60 Langit  Ang Nindot nga Puluy-anan sa Dios_translated.pdf",
    },
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pdf_text(path: Path) -> str:
    """Normalize whitespace only; retain all pages for a reproducible comparison."""
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
    except Exception as error:  # Preserve a test failure as evidence.
        return {
            "page_count": None,
            "text_characters": 0,
            "non_empty_text": False,
            "page_count_matches_source": False,
            "layout_validation": "fail",
            "error": str(error),
        }


def score(output: Path, reference: Path) -> dict:
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


def post_document(server_url: str, pair: dict) -> tuple[dict, bytes | None, float]:
    started = time.perf_counter()
    with pair["source"].open("rb") as stream:
        response = requests.post(
            f"{server_url.rstrip('/')}/translate/document",
            files={"file": (pair["source"].name, stream, "application/pdf")},
            data={
                "source_lang": pair["source_language"],
                "target_lang": pair["target_language"],
                "mode": "fast",
                "pdf_column_mode": "auto",
            },
            timeout=7200,
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    if not response.ok:
        return ({"status": response.status_code, "error": response.text[:2000]}, None, elapsed_ms)
    payload = response.json()
    file_base64 = payload.get("file_base64", "")
    if not file_base64:
        return ({"status": 500, "error": "Response contained no file_base64"}, None, elapsed_ms)
    return (payload, base64.b64decode(file_base64), elapsed_ms)


def repeat_text(server_url: str, pair: dict) -> dict:
    with fitz.open(pair["source"]) as document:
        # Physical pages 2-3 contain story text rather than only the cover.
        source_text = "\n".join(document[index].get_text("text") for index in (1, 2)).strip()
    samples: list[dict] = []
    for number in range(1, 4):
        started = time.perf_counter()
        response = requests.post(
            f"{server_url.rstrip('/')}/translate/text",
            json={
                "text": source_text,
                "source_lang": pair["source_language"],
                "target_lang": pair["target_language"],
                "mode": "fast",
            },
            timeout=7200,
        )
        latency = round((time.perf_counter() - started) * 1000, 2)
        if response.ok:
            payload = response.json()
            translated = payload.get("translated", "")
            samples.append({
                "run": number,
                "status": "completed",
                "latency_ms": latency,
                "provider_reported_latency_ms": payload.get("execution_time_ms"),
                "output_sha256": hashlib.sha256(translated.encode("utf-8")).hexdigest(),
                "output_characters": len(translated),
            })
        else:
            samples.append({"run": number, "status": "failed", "latency_ms": latency, "error": response.text[:2000]})
    successful = [item for item in samples if item["status"] == "completed"]
    hashes = {item["output_sha256"] for item in successful}
    return {
        "input_pages": [2, 3],
        "input_characters": len(source_text),
        "samples": samples,
        "successful_runs": len(successful),
        "median_latency_ms": round(statistics.median(item["latency_ms"] for item in successful), 2) if successful else None,
        "distinct_output_hashes": len(hashes),
        "stable_output": len(successful) == 3 and len(hashes) == 1,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", default="http://127.0.0.1:5001")
    args = parser.parse_args()

    missing = [str(path) for pair in PAIRS for path in (pair["source"], pair["reference"], pair["gptoss_output"]) if not path.is_file()]
    if missing:
        raise SystemExit("Missing Part2 evaluation files: " + ", ".join(missing))

    health_response = requests.get(f"{args.server_url.rstrip('/')}/health", timeout=30)
    health_response.raise_for_status()
    health = health_response.json()
    if health.get("active_provider") != "nllb":
        raise SystemExit(f"Expected active NLLB provider, received {health.get('active_provider')!r}.")
    if health.get("fallback_provider"):
        raise SystemExit("Evaluation server has a fallback provider configured; refusing a mixed run.")

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "title": "Part2 Iteration 1 NLLB Evaluation",
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "nllb",
        "model": health.get("model"),
        "server_url": args.server_url,
        "processing_mode": "fast",
        "translation_fallback_disabled": True,
        "translation_cache_disabled": True,
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
    write_json(ITERATION / "benchmark-manifest.json", manifest)

    findings = {
        "schema_version": 1,
        "iteration_title": "Part2 Iteration 1 NLLB",
        "generated_at": manifest["generated_at"],
        "provider": "nllb",
        "health": health,
        "manifest_path": str(ITERATION / "benchmark-manifest.json"),
        "full_runs": [],
        "stability_runs": {},
    }
    for pair in PAIRS:
        output_path = OUTPUTS / f"{pair['id']}.pdf"
        payload, bytes_out, elapsed = post_document(args.server_url, pair)
        record = {
            "id": pair["id"],
            "source": pair["source"].name,
            "reference": pair["reference"].name,
            "source_language": pair["source_language"],
            "target_language": pair["target_language"],
            "source_sha256": sha256(pair["source"]),
            "reference_sha256": sha256(pair["reference"]),
            "output_path": str(output_path),
            "elapsed_ms": elapsed,
            "status": "completed" if bytes_out else "failed",
            "engine_response": {key: value for key, value in payload.items() if key not in {"file_base64", "blocks", "sidecar"}},
        }
        if bytes_out:
            output_path.write_bytes(bytes_out)
            record["output_sha256"] = sha256(output_path)
            record["output_bytes"] = output_path.stat().st_size
            record["structure"] = pdf_structure(output_path, 25)
            record["quality"] = score(output_path, pair["reference"])
        else:
            record["quality"] = {"bleu": None, "chrf": None, "note": "Translation failed"}
        findings["full_runs"].append(record)
        write_json(ITERATION / "findings.json", findings)

    for pair in PAIRS:
        findings["stability_runs"][pair["id"]] = repeat_text(args.server_url, pair)
        write_json(ITERATION / "findings.json", findings)

    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "nllb",
        "model": health.get("model"),
        "health": health,
        "manifest_sha256": sha256(ITERATION / "benchmark-manifest.json"),
        "full_run_count": len(findings["full_runs"]),
        "stability_runs_per_direction": 3,
    }
    write_json(ITERATION / "run-metadata.json", metadata)
    print(json.dumps(findings, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
