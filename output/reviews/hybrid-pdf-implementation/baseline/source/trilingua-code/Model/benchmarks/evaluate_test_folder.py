"""Run one isolated provider against the user-supplied PDF evaluation set.

The script is intentionally separate from Laravel.  It talks directly to a
FastAPI server started with one provider and writes every generated artifact to
``chatgpt/test`` so evaluation runs cannot pollute production history.
"""

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


ROOT = Path(__file__).resolve().parents[3]
TEST_ROOT = ROOT / "chatgpt" / "test"
ORIGINALS = TEST_ROOT / "Original Files"
SONA_SOURCE = ORIGINALS / "SONA_2019_English.pdf"
PSF_SOURCE = ORIGINALS / "English PSF Brochure.pdf"
SONA_REFERENCES = {
    "Filipino": ROOT / "output" / "sona2019" / "SONA_2019_Filipino.pdf",
    "Cebuano": ROOT / "output" / "sona2019" / "SONA_2019_Cebuano.pdf",
}
TARGETS = {"Filipino": "fil", "Cebuano": "ceb"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pdf_page_count(path: Path) -> int | None:
    try:
        with fitz.open(path) as document:
            return len(document)
    except Exception:
        return None


def normalized_pdf_text(path: Path, *, sona: bool) -> str:
    """Extract a stable scoring surface without page furniture or cover text."""
    with fitz.open(path) as document:
        pages = list(document)
        # The SONA source and reference editions begin with a blank/cover page
        # and title material.  Removing their first two pages avoids rating a
        # model on translated cover furniture rather than the speech body.
        if sona:
            pages = pages[2:]

        kept: list[str] = []
        for page in pages:
            for raw_line in page.get_text("text").splitlines():
                line = " ".join(raw_line.split()).strip()
                if not line:
                    continue
                if line.isdigit():
                    continue
                upper = line.upper()
                if upper.startswith("STATE OF THE NATION ADDRESS"):
                    continue
                if upper.startswith("SONA 2019"):
                    continue
                kept.append(line)
    return " ".join(kept)


def output_structure(path: Path, expected_pages: int | None) -> dict:
    try:
        with fitz.open(path) as document:
            pages = len(document)
            text_chars = sum(len(page.get_text("text").strip()) for page in document)
        return {
            "page_count": pages,
            "text_characters": text_chars,
            "non_empty_text": text_chars > 0,
            "page_count_matches_source": expected_pages is None or pages == expected_pages,
            # This is an automatic structural proxy. It deliberately does not
            # claim a human visual-layout review.
            "layout_validation": "pass"
            if text_chars > 0 and (expected_pages is None or pages == expected_pages)
            else "fail",
        }
    except Exception as error:
        return {
            "page_count": None,
            "text_characters": 0,
            "non_empty_text": False,
            "page_count_matches_source": False,
            "layout_validation": "fail",
            "error": str(error),
        }


def score_sona(output_path: Path, target_language: str) -> dict:
    try:
        import sacrebleu
    except ImportError:
        return {"bleu": None, "chrf": None, "note": "sacrebleu is not installed"}

    hypothesis = normalized_pdf_text(output_path, sona=True)
    reference = normalized_pdf_text(SONA_REFERENCES[target_language], sona=True)
    if not hypothesis or not reference:
        return {
            "bleu": None,
            "chrf": None,
            "note": "Output or reference text extraction was empty",
            "hypothesis_characters": len(hypothesis),
            "reference_characters": len(reference),
        }
    return {
        "bleu": round(sacrebleu.corpus_bleu([hypothesis], [[reference]]).score, 2),
        "chrf": round(sacrebleu.corpus_chrf([hypothesis], [[reference]]).score, 2),
        "hypothesis_characters": len(hypothesis),
        "reference_characters": len(reference),
    }


def post_document(server_url: str, source: Path, target_language: str) -> tuple[dict, bytes | None, float]:
    started = time.perf_counter()
    with source.open("rb") as handle:
        response = requests.post(
            f"{server_url.rstrip('/')}/translate/document",
            files={"file": (source.name, handle, "application/pdf")},
            data={
                "source_lang": "English",
                "target_lang": target_language,
                # Fast mode avoids model-backed analysis/review, isolating the
                # selected translation provider for a fair benchmark.
                "mode": "fast",
                "pdf_column_mode": "auto",
            },
            timeout=7200,
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    if not response.ok:
        return ({"status": response.status_code, "error": response.text[:1000]}, None, elapsed_ms)
    payload = response.json()
    encoded = payload.get("file_base64", "")
    if not encoded:
        return ({"status": 500, "error": "Response contained no file_base64 payload"}, None, elapsed_ms)
    return (payload, base64.b64decode(encoded), elapsed_ms)


def subset_text() -> str:
    with fitz.open(SONA_SOURCE) as document:
        # Pages 3-4 are the first two substantive speech pages after cover and
        # title material. The same source text is used for all stability runs.
        return "\n".join(document[index].get_text("text") for index in (2, 3)).strip()


def repeat_text(server_url: str, text: str, target_language: str) -> dict:
    samples: list[dict] = []
    for run_number in range(1, 4):
        started = time.perf_counter()
        response = requests.post(
            f"{server_url.rstrip('/')}/translate/text",
            json={
                "text": text,
                "source_lang": "English",
                "target_lang": target_language,
                "mode": "fast",
            },
            timeout=7200,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        if response.ok:
            payload = response.json()
            translated = payload.get("translated", "")
            samples.append({
                "run": run_number,
                "status": "completed",
                "latency_ms": elapsed_ms,
                "provider_reported_latency_ms": payload.get("execution_time_ms"),
                "output_sha256": hashlib.sha256(translated.encode("utf-8")).hexdigest(),
                "output_characters": len(translated),
            })
        else:
            samples.append({"run": run_number, "status": "failed", "latency_ms": elapsed_ms,
                            "error": response.text[:1000]})
    completed = [sample for sample in samples if sample["status"] == "completed"]
    hashes = {sample["output_sha256"] for sample in completed}
    return {
        "input_pages": [3, 4],
        "input_characters": len(text),
        "samples": samples,
        "median_latency_ms": round(statistics.median([sample["latency_ms"] for sample in completed]), 2)
        if completed else None,
        "successful_runs": len(completed),
        "stable_output": len(hashes) == 1 if completed else False,
        "distinct_output_hashes": len(hashes),
    }


def markdown_report(data: dict) -> str:
    lines = [
        f"# {data['iteration_title']} Findings",
        "",
        f"Generated: {data['generated_at']}",
        "",
        "## Configuration",
        "",
        f"- Provider: `{data['provider']}`",
        f"- Server-reported model: `{data['health'].get('model', 'unavailable')}`",
        "- Translation fallback: disabled for this controlled evaluation.",
        "- Processing mode: `fast` to isolate the selected translation provider.",
        "",
        "## Full PDF Outputs",
        "",
        "| Source | Target | Status | Time (ms) | BLEU | chrF | Structural layout |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for record in data["full_runs"]:
        score = record.get("quality", {})
        structure = record.get("structure", {})
        lines.append(
            "| {source} | {target} | {status} | {latency} | {bleu} | {chrf} | {layout} |".format(
                source=record["source"],
                target=record["target_language"],
                status=record["status"],
                latency=record["elapsed_ms"],
                bleu=score.get("bleu", "N/A"),
                chrf=score.get("chrf", "N/A"),
                layout=structure.get("layout_validation", "N/A"),
            )
        )
    lines += [
        "",
        "The PSF Brochure has no verified Filipino or Cebuano reference; BLEU and chrF are intentionally N/A for that file.",
        "",
        "## Two-Page Stability Runs",
        "",
        "| Target | Successful runs | Median latency (ms) | Stable output |",
        "|---|---:|---:|---|",
    ]
    for target, result in data["stability_runs"].items():
        lines.append(
            f"| {target} | {result['successful_runs']}/3 | {result['median_latency_ms']} | {result['stable_output']} |"
        )
    lines += [
        "",
        "## Scope and Limitations",
        "",
        "- This evaluation covers English-to-Filipino and English-to-Cebuano only; reverse directions are out of scope.",
        "- SONA scores are automatic lexical-overlap metrics against official translations. They do not replace bilingual human evaluation.",
        "- Structural layout is an automatic page-count and non-empty-text proxy, not a human visual review.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, choices=("gptoss", "nllb"))
    parser.add_argument("--server-url", default="http://127.0.0.1:5000")
    args = parser.parse_args()

    iteration_folder = (
        TEST_ROOT / "iteration-2-gptoss"
        if args.provider == "gptoss"
        else TEST_ROOT / "iteration-1-nllb-200-600m"
    )
    outputs = iteration_folder / "translated-files"
    outputs.mkdir(parents=True, exist_ok=True)

    required = [SONA_SOURCE, PSF_SOURCE, *SONA_REFERENCES.values()]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("Missing evaluation files: " + ", ".join(missing))

    health_response = requests.get(f"{args.server_url.rstrip('/')}/health", timeout=20)
    health_response.raise_for_status()
    health = health_response.json()
    if health.get("active_provider") != args.provider:
        raise SystemExit(
            f"Server provider is {health.get('active_provider')!r}, expected {args.provider!r}."
        )
    if health.get("fallback_provider"):
        raise SystemExit("Evaluation server reports a configured fallback provider; refusing mixed-model run.")

    manifest = {
        "schema_version": 1,
        "source_language": "English",
        "targets": list(TARGETS),
        "processing_mode": "fast",
        "fallback_disabled": True,
        "original_files": [
            {"path": str(SONA_SOURCE), "sha256": sha256(SONA_SOURCE), "pages": pdf_page_count(SONA_SOURCE)},
            {"path": str(PSF_SOURCE), "sha256": sha256(PSF_SOURCE), "pages": pdf_page_count(PSF_SOURCE)},
        ],
        "sona_references": {
            language: {"path": str(path), "sha256": sha256(path), "pages": pdf_page_count(path)}
            for language, path in SONA_REFERENCES.items()
        },
        "normalization": {
            "skip_first_two_sona_pages": True,
            "remove_page_number_lines": True,
            "remove_repeated_sona_running_headers": True,
        },
    }
    write_json(TEST_ROOT / "benchmark-manifest.json", manifest)

    data = {
        "schema_version": 1,
        "iteration_title": "Iteration 2 — Current GPT-OSS" if args.provider == "gptoss"
        else "Iteration 1 — Local NLLB-200 600M",
        "provider": args.provider,
        "generated_at": datetime.now(UTC).isoformat(),
        "server_url": args.server_url,
        "health": health,
        "manifest_path": str(TEST_ROOT / "benchmark-manifest.json"),
        "full_runs": [],
        "stability_runs": {},
    }

    for source in (PSF_SOURCE, SONA_SOURCE):
        source_pages = pdf_page_count(source)
        for target_language, target_code in TARGETS.items():
            output_name = f"{source.stem}__en-to-{target_code}.pdf"
            output_path = outputs / output_name
            payload, file_bytes, elapsed_ms = post_document(args.server_url, source, target_language)
            record = {
                "source": source.name,
                "source_sha256": sha256(source),
                "target_language": target_language,
                "output_path": str(output_path),
                "elapsed_ms": elapsed_ms,
                "status": "completed" if file_bytes else "failed",
                "engine_response": {
                    key: value
                    for key, value in payload.items()
                    if key not in {"file_base64", "blocks", "sidecar"}
                },
            }
            if file_bytes:
                output_path.write_bytes(file_bytes)
                record["output_sha256"] = sha256(output_path)
                record["output_bytes"] = output_path.stat().st_size
                record["structure"] = output_structure(output_path, source_pages)
                record["quality"] = score_sona(output_path, target_language) if source == SONA_SOURCE else {
                    "bleu": "N/A", "chrf": "N/A", "note": "No verified brochure reference translation",
                }
            else:
                record["quality"] = {"bleu": None, "chrf": None, "note": "Translation failed"}
            data["full_runs"].append(record)
            write_json(iteration_folder / "findings.json", data)

    text = subset_text()
    for target_language in TARGETS:
        data["stability_runs"][target_language] = repeat_text(args.server_url, text, target_language)
        write_json(iteration_folder / "findings.json", data)

    metadata = {
        "generated_at": data["generated_at"],
        "provider": args.provider,
        "health": health,
        "manifest_sha256": sha256(TEST_ROOT / "benchmark-manifest.json"),
        "full_run_count": len(data["full_runs"]),
        "stability_run_count_per_target": 3,
    }
    write_json(iteration_folder / "run-metadata.json", metadata)
    (iteration_folder / "findings.md").write_text(markdown_report(data), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
