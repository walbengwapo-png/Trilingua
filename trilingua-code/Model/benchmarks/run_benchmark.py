"""Run the versioned TriLingua benchmark through a configured FastAPI server."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

import requests


CORPUS = Path(__file__).with_name("translation_quality_v1.jsonl")


def load_cases(include_pending: bool) -> list[dict]:
    cases = [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line]
    return cases if include_pending else [c for c in cases if c["review_status"] == "approved"]


def score(hypotheses: list[str], references: list[str]) -> dict:
    try:
        import sacrebleu
    except ImportError:
        return {"sacrebleu": None, "chrf": None, "note": "Install sacrebleu to score references."}
    return {
        "sacrebleu": round(sacrebleu.corpus_bleu(hypotheses, [references]).score, 2),
        "chrf": round(sacrebleu.corpus_chrf(hypotheses, [references]).score, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", default="http://127.0.0.1:5000")
    parser.add_argument("--include-pending", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("benchmark-report.json"))
    args = parser.parse_args()

    cases = load_cases(args.include_pending)
    if not cases:
        raise SystemExit("No approved benchmark cases yet. Use --include-pending for curation runs.")

    groups: dict[str, dict[str, list]] = defaultdict(lambda: {"hypotheses": [], "references": [], "latencies_ms": [], "failures": []})
    for case in cases:
        pair = f"{case['source_lang']}→{case['target_lang']}"
        started = time.perf_counter()
        response = requests.post(
            f"{args.server_url.rstrip('/')}/translate/text",
            json={"text": case["source"], "source_lang": case["source_lang"], "target_lang": case["target_lang"]},
            timeout=120,
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        if not response.ok:
            groups[pair]["failures"].append({"id": case["id"], "status": response.status_code, "detail": response.text[:300]})
            continue
        translated = response.json().get("translated", "")
        groups[pair]["hypotheses"].append(translated)
        groups[pair]["references"].append(case["reference"])
        groups[pair]["latencies_ms"].append(latency_ms)

    report = {"corpus": CORPUS.name, "cases": len(cases), "pairs": {}}
    for pair, values in groups.items():
        report["pairs"][pair] = {
            **score(values["hypotheses"], values["references"]),
            "median_latency_ms": round(statistics.median(values["latencies_ms"]), 2) if values["latencies_ms"] else None,
            "failures": values["failures"],
        }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
