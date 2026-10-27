"""Build the local comparison artifacts after both evaluation iterations finish."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TEST_ROOT = ROOT / "chatgpt" / "test"
ITERATIONS = {
    "gptoss": TEST_ROOT / "iteration-2-gptoss" / "findings.json",
    "nllb": TEST_ROOT / "iteration-1-nllb-200-600m" / "findings.json",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sona_rows(data: dict) -> dict[str, dict]:
    return {
        row["target_language"]: row
        for row in data["full_runs"]
        if row["source"] == "SONA_2019_English.pdf"
    }


def elapsed_label(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "N/A"
    return f"{value / 60000:.2f} min"


def failure_summary(row: dict) -> str:
    error = row.get("engine_response", {}).get("error", "")
    if not error:
        return "—"
    # Keep the human report readable while the complete service response stays
    # preserved in the iteration's findings.json.
    text = str(error).replace("\\n", " ").replace("\\\"", "\"")
    return text[:260] + ("…" if len(text) > 260 else "")


def write_iteration_summary(data: dict, *, stopped_by_user: bool = False) -> None:
    """Create a readable report even when a controlled run is stopped."""
    folder = ITERATIONS[data["provider"]].parent
    lines = [
        f"# {data['iteration_title']} Findings",
        "",
        f"Generated: {data['generated_at']}",
        "",
        "## Run Status",
        "",
        "Stopped by user request before all planned measurements completed."
        if stopped_by_user else "Completed.",
        "",
        "## Configuration",
        "",
        f"- Provider: `{data['provider']}`",
        f"- Model: `{data['health'].get('model', 'unavailable')}`",
        "- Translation fallback: disabled.",
        "- Translation cache: disabled.",
        "- Processing mode: `fast` (translation provider isolated from AI review).",
        "",
        "## Full PDF Runs",
        "",
        "| Source | Target | Status | Elapsed | BLEU | chrF | Structural layout |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in data["full_runs"]:
        quality = row.get("quality", {})
        structure = row.get("structure", {})
        lines.append(
            f"| {row['source']} | {row['target_language']} | {row['status']} | "
            f"{elapsed_label(row.get('elapsed_ms'))} | {quality.get('bleu', 'N/A')} | "
            f"{quality.get('chrf', 'N/A')} | {structure.get('layout_validation', 'N/A')} |"
        )
    lines += [
        "",
        "The PSF Brochure has no verified Filipino or Cebuano reference translation; its BLEU and chrF values are intentionally N/A.",
        "",
        "## Two-Page SONA Stability",
        "",
    ]
    if data.get("stability_runs"):
        lines += [
            "| Target | Successful runs | Median latency | Stable output |",
            "|---|---:|---:|---|",
        ]
        for target, result in data["stability_runs"].items():
            lines.append(
                f"| {target} | {result['successful_runs']}/3 | "
                f"{elapsed_label(result.get('median_latency_ms'))} | {result['stable_output']} |"
            )
    else:
        lines.append("Not run." if stopped_by_user else "No stability samples were recorded.")
    lines += [
        "",
        "## Scope and Limitations",
        "",
        "- Scope is English-to-Filipino and English-to-Cebuano only; reverse directions are out of scope.",
        "- SONA BLEU/chrF uses normalized extracted PDF text against official reference editions and is not a substitute for human bilingual review.",
        "- Structural layout is an automated page-count and non-empty-text check, not a visual review.",
    ]
    if stopped_by_user:
        lines += [
            "- The user stopped the remaining GPT-OSS SONA Cebuano and stability measurements to shorten evaluation time.",
        ]
    (folder / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    reports = {name: load(path) for name, path in ITERATIONS.items()}
    gptoss_incomplete = (
        len(sona_rows(reports["gptoss"])) < 2
        or not reports["gptoss"].get("stability_runs")
    )
    write_iteration_summary(reports["nllb"])
    write_iteration_summary(reports["gptoss"], stopped_by_user=gptoss_incomplete)
    if gptoss_incomplete:
        metadata_path = ITERATIONS["gptoss"].parent / "run-metadata.json"
        metadata_path.write_text(json.dumps({
            "provider": "gptoss",
            "model": reports["gptoss"]["health"].get("model"),
            "execution_status": "stopped_by_user",
            "completed_full_runs": len(reports["gptoss"]["full_runs"]),
            "planned_full_runs": 4,
            "stability_runs_completed": 0,
            "note": "The remaining SONA Cebuano and all stability measurements were not run after the user requested a comprehensive current-state report.",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows_by_provider = {name: sona_rows(data) for name, data in reports.items()}
    comparison_rows: list[dict] = []
    for language in ("Filipino", "Cebuano"):
        for provider in ("gptoss", "nllb"):
            row = rows_by_provider[provider].get(language, {})
            quality = row.get("quality", {})
            structure = row.get("structure", {})
            comparison_rows.append({
                "provider": provider,
                "target_language": language,
                "status": row.get("status"),
                "bleu": quality.get("bleu"),
                "chrf": quality.get("chrf"),
                "elapsed_ms": row.get("elapsed_ms"),
                "layout_validation": structure.get("layout_validation"),
                "output_sha256": row.get("output_sha256"),
            })

    gptoss_wins = True
    reasons: list[str] = []
    if gptoss_incomplete:
        gptoss_wins = False
        reasons.append("GPT-OSS evaluation was stopped before the Cebuano SONA and stability measurements completed.")
    for language in ("Filipino", "Cebuano"):
        gpt = rows_by_provider["gptoss"].get(language, {})
        nllb = rows_by_provider["nllb"].get(language, {})
        gq, nq = gpt.get("quality", {}), nllb.get("quality", {})
        if gpt.get("status") != "completed" or nllb.get("status") != "completed":
            gptoss_wins = False
            reasons.append(f"{language}: one or both providers did not complete.")
            continue
        if gq.get("bleu") is None or nq.get("bleu") is None or gq.get("chrf") is None or nq.get("chrf") is None:
            gptoss_wins = False
            reasons.append(f"{language}: quality score unavailable.")
            continue
        if gq["bleu"] < nq["bleu"] or gq["chrf"] < nq["chrf"]:
            gptoss_wins = False
            reasons.append(f"{language}: GPT-OSS did not meet both NLLB quality metrics.")
        if gpt.get("structure", {}).get("layout_validation") != "pass":
            gptoss_wins = False
            reasons.append(f"{language}: GPT-OSS structural layout validation failed.")

    comparison = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "English to Filipino and English to Cebuano only",
        "evaluation_status": "partial: stopped by user request" if gptoss_incomplete else "complete",
        "providers": {
            name: {
                "iteration_title": data["iteration_title"],
                "model": data["health"].get("model"),
            }
            for name, data in reports.items()
        },
        "sona_comparison": comparison_rows,
        "gptoss_qualifies_for_future_iteration_3": gptoss_wins,
        "decision_reasons": reasons or ["GPT-OSS met the configured automated comparison gate."],
        "pause": "No Iteration 3 translation-logic change was made by this evaluation.",
    }
    comparison_dir = TEST_ROOT / "comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    (comparison_dir / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (comparison_dir / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(comparison_rows[0]))
        writer.writeheader()
        writer.writerows(comparison_rows)

    report = [
        "# TriLingua Iteration 1 and 2 Findings",
        "",
        f"Generated: {comparison['generated_at']}",
        "",
        "## Scope",
        "",
        "This controlled evaluation covers English-to-Filipino and English-to-Cebuano only. Reverse translation directions were not tested.",
        "",
        "## Current Evaluation Status",
        "",
        "The NLLB iteration completed. The GPT-OSS iteration was stopped by user request after its Filipino SONA run failed and before its Cebuano SONA run and stability repetitions began." if gptoss_incomplete else "Both iterations completed.",
        "",
        "## SONA 2019 Results",
        "",
        "| Provider | Target | Status | BLEU | chrF | Time (ms) | Structural layout |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in comparison_rows:
        report.append(
            f"| {row['provider']} | {row['target_language']} | {row['status']} | {row['bleu']} | {row['chrf']} | {row['elapsed_ms']} | {row['layout_validation']} |"
        )
    report += [
        "",
        "## Rating Method",
        "",
        "SONA scores use automatically normalized PDF text and official Filipino/Cebuano editions as references. BLEU and chrF measure lexical overlap; they do not replace bilingual human evaluation. The PSF Brochure has no verified reference translation, so its output is reported only for completion and structural layout.",
        "",
        "## Operational Findings",
        "",
        "- NLLB completed both SONA translations with passing automated structural checks. Its two-page excerpt was stable across all three runs for both targets.",
        "- NLLB rejected the Cebuano brochure after three blocks remained unchanged; no false-success PDF was produced.",
        "- GPT-OSS rejected the Filipino brochure after one unchanged block and rejected Filipino SONA after two unchanged blocks.",
        "- GPT-OSS completed the Cebuano brochure with a passing automated structural check, but its planned Cebuano SONA and all stability measurements were not run after the user-requested stop.",
        "",
        "## Full Artifact Inventory and Failures",
        "",
        "| Provider | Source | Target | Status | Time | Output file | Failure/validation note |",
        "|---|---|---|---|---:|---|---|",
    ]
    for provider in ("nllb", "gptoss"):
        for row in reports[provider]["full_runs"]:
            output = Path(row.get("output_path", "")).name if row.get("output_path") else "—"
            note = failure_summary(row) if row.get("status") != "completed" else (
                row.get("structure", {}).get("layout_validation", "N/A")
            )
            report.append(
                f"| {provider} | {row['source']} | {row['target_language']} | {row['status']} | "
                f"{elapsed_label(row.get('elapsed_ms'))} | {output if row.get('status') == 'completed' else '—'} | {note} |"
            )
    report += [
        "",
        "## NLLB Stability Detail",
        "",
        "| Target | Runs | Median latency | Distinct output hashes | Result |",
        "|---|---:|---:|---:|---|",
    ]
    for target, result in reports["nllb"].get("stability_runs", {}).items():
        report.append(
            f"| {target} | {result['successful_runs']}/3 | {elapsed_label(result.get('median_latency_ms'))} | "
            f"{result['distinct_output_hashes']} | {'stable' if result['stable_output'] else 'not stable'} |"
        )
    report += [
        "",
        "The two-page excerpt source is pages 3–4 of the English SONA PDF (5,131 extracted characters). GPT-OSS stability samples were not run because the user stopped the remaining evaluation.",
        "",
        "## Reproducibility",
        "",
        "- Inputs are recorded with SHA-256 hashes in `benchmark-manifest.json`; the original source PDFs were not modified.",
        "- NLLB model: `facebook/nllb-200-distilled-600M` at revision `f8d333a098d19b4fd9a8b18f94170487ad3f821d`, local-only CPU execution.",
        "- GPT-OSS model: `gpt-oss:20b-cloud` through the current configured service.",
        "- Both providers ran with fallback disabled, translation cache disabled, and `fast` mode.",
        "",
        "## Decision Gate",
        "",
        "GPT-OSS qualifies for a future Iteration 3 only when it meets or exceeds NLLB on both BLEU and chrF for both tested targets, without a structural regression.",
        "",
        f"**Result:** {'GPT-OSS qualifies as the preferred future candidate.' if gptoss_wins else 'No provider promotion is recommended from this run.'}",
        "",
        "## Pause",
        "",
        "No GPT-OSS translation-logic change was made. Iteration 3 remains paused pending review of these artifacts.",
    ]
    (comparison_dir / "Trilingua-Iteration-1-and-2-Findings.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
