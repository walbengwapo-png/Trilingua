"""Release-specific offline evidence recorder. No provider calls or automatic human ratings.

The manifest records evidence supplied by testers; it does not authenticate a
reviewer's identity. Keep signed/source review records alongside this manifest.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
from pathlib import Path
import re

from benchmarks.complete_internal_evaluation import (
    DIMENSIONS, diagnostic_bleu, dump, load, read_text, structural_metrics, verify_hash,
)

LANGUAGES = {"en", "ceb", "fil"}
RELEASE_FIELDS = ("app_commit", "engine_commit", "app_revision", "engine_revision")


def release_key(release):
    return tuple(release.get(k, "").strip() if isinstance(release.get(k), str) else ""
                 for k in RELEASE_FIELDS)


def record_run(manifest_path, output_dir):
    """Write derived completion separately from quality/readiness, failing closed."""
    manifest_path, output_dir = Path(manifest_path), Path(output_dir)
    manifest = load(manifest_path)
    if manifest.get("schema_version") != 1 or not manifest.get("run_id"):
        raise ValueError("schema_version=1 and a run_id are required")
    output_dir.mkdir(parents=True, exist_ok=True)
    base, integrity = manifest_path.parent, []

    def artifact(spec, label):
        spec = spec or {}
        path = Path(spec.get("path") or "__missing_artifact__")
        if not path.is_absolute():
            path = base / path
        expected = spec.get("sha256", "")
        check = verify_hash(path, expected) if len(expected) == 64 else "MISSING_HASH"
        integrity.append({"artifact": label, "path": str(path), "check": check})
        return path if check == "MATCH" else None

    def review(spec, label):
        spec = spec or {}
        try:
            dated = date.fromisoformat(spec.get("date", "")) <= date.today()
        except (ValueError, TypeError):
            dated = False
        return bool(spec.get("reviewer") and dated and spec.get("decision") == "approved"
                    and artifact(spec.get("evidence"), label))

    target = manifest.get("release", {})
    compatible = (all(release_key(target))
                  and all(re.fullmatch(r"[0-9a-f]{40}", target.get(k, ""))
                          for k in ("app_commit", "engine_commit"))
                  and target.get("app_revision") == target.get("engine_revision"))
    scope = manifest.get("scope", {})
    scope_approved = review(scope.get("approval"), "scope approval")
    method = scope.get("formatting_method", {})
    method_approved = (method.get("id") == "attribute_and_visual"
                       and review(method.get("approval"), "formatting method approval"))
    documents = scope.get("document_case_ids", [])
    bleu_ids = scope.get("bleu_case_ids", [])
    format_ids = scope.get("formatting_case_ids", [])
    functional_scope = scope.get("functionality_cases", [])
    for label, ids in [("document", documents), ("BLEU", bleu_ids), ("formatting", format_ids),
                       ("functionality", [c["case_id"] for c in functional_scope])]:
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate {label} scope case IDs")
    if not set(bleu_ids + format_ids).issubset(documents):
        raise ValueError("BLEU/formatting scope must be part of document scope")

    runs, seen_ids, seen_outputs, seen_jobs = [], set(), set(), set()
    bleu_groups = defaultdict(list)
    valid_by_id = {}
    for entry in manifest.get("documents", []):
        cid = entry["case_id"]
        if cid in seen_ids:
            raise ValueError(f"Duplicate document case ID: {cid}")
        seen_ids.add(cid)
        source = artifact(entry.get("source"), cid + " source")
        translated = artifact(entry.get("output"), cid + " output")
        same_release = compatible and release_key(entry.get("release", {})) == release_key(target)
        output_hash = entry.get("output", {}).get("sha256")
        job = entry.get("job_id")
        reused = bool(entry.get("reuse_from") or entry.get("provenance") != "fresh"
                      or output_hash in seen_outputs or (job and job in seen_jobs))
        seen_outputs.add(output_hash)
        if job:
            seen_jobs.add(job)
        src, tgt = (entry.get("options", {}).get(k) for k in ("source_language", "target_language"))
        provenance = bool(job and entry.get("provider") and entry.get("model")
                          and src in LANGUAGES and tgt in LANGUAGES and src != tgt)
        valid = bool(source and translated and same_release and not reused and provenance)
        row = {"case_id": cid, "release": entry.get("release", {}), "current_release": same_release,
               "independent": not reused, "artifacts_valid": bool(source and translated),
               "eligible_current_run": valid, "status": entry.get("status", "NOT_RUN")}
        if valid:
            valid_by_id[cid] = row
            if cid in format_ids:
                row["structural_metrics"] = {"source": structural_metrics(source),
                                             "output": structural_metrics(translated)}
            if cid in bleu_ids:
                reference = artifact(entry.get("reference"), cid + " reference")
                validated = review(entry.get("reference_validation"), cid + " reference validation")
                row["reference_validated"] = bool(reference and validated)
                if reference:
                    hypothesis = " ".join(read_text(translated).split())
                    reftext = " ".join(read_text(reference).split())
                    if hypothesis and reftext:
                        row["bleu"] = diagnostic_bleu([hypothesis], [reftext])
                        bleu_groups[(release_key(target), src, tgt)].append((cid, hypothesis, reftext))
            rating = entry.get("formatting_review", {})
            values = rating.get("dimensions", {})
            scale = method.get("rating_scale", {})
            low, high = scale.get("min"), scale.get("max")
            numeric_scale = (type(low) in (int, float) and type(high) in (int, float)
                             and math.isfinite(low) and math.isfinite(high) and low < high)
            complete_values = (numeric_scale and set(values) == set(DIMENSIONS)
                               and all(type(v) in (int, float) and math.isfinite(v)
                                       and low <= v <= high for v in values.values()))
            row["formatting_review_complete"] = bool(
                cid in format_ids and source.suffix.lower() in {".pdf", ".docx"}
                and translated.suffix.lower() == source.suffix.lower()
                and method_approved and complete_values
                and review(rating, cid + " formatting review"))
            if row["formatting_review_complete"]:
                row["manual_dimensions"] = values
                row["manual_overall_mean"] = sum(values.values()) / len(DIMENSIONS)
        runs.append(row)

    observations = {}
    for entry in manifest.get("functionality", []):
        cid = entry["case_id"]
        if cid in observations:
            raise ValueError(f"Duplicate functionality observation: {cid}")
        observations[cid] = entry
    modules = defaultdict(list)
    for case in functional_scope:
        cid, role = case["case_id"], case["role"]
        entry = observations.get(cid, {})
        eligible = bool(compatible and case.get("atomic") is True and entry.get("role") == role
                        and entry.get("tester") and entry.get("executed_at")
                        and release_key(entry.get("release", {})) == release_key(target)
                        and artifact(entry.get("evidence"), cid + " functionality evidence"))
        status = entry.get("status") if eligible else "NOT_VERIFIED"
        modules[(role, case["module"])].append(status)
    module_results = [{"role": role, "module": module, "required": len(statuses),
                       "passed": statuses.count("PASS"),
                       "pass_percent": 100 * statuses.count("PASS") / len(statuses),
                       "all_executed": all(s in {"PASS", "FAIL"} for s in statuses)}
                      for (role, module), statuses in sorted(modules.items())]
    functionality_complete = bool(scope_approved and module_results
                                  and all(m["all_executed"] for m in module_results))
    functionality_ready = functionality_complete and all(m["pass_percent"] >= 95 for m in module_results)
    all_docs = bool(scope_approved and documents and all(cid in valid_by_id for cid in documents))
    six_directions = {(a, b) for a in LANGUAGES for b in LANGUAGES if a != b}
    measured_directions = {(src, tgt) for (_, src, tgt), _ in bleu_groups.items()}
    bleu_complete = bool(all_docs and bleu_ids and measured_directions == six_directions
                         and all(valid_by_id[cid].get("reference_validated")
                                 and valid_by_id[cid].get("bleu") for cid in bleu_ids))
    formatting_complete = bool(all_docs and method_approved and len(format_ids) >= 10
                               and all(valid_by_id[cid].get("formatting_review_complete") for cid in format_ids))
    evaluation_complete = all_docs and functionality_complete and bleu_complete and formatting_complete
    serious_blockers = [b for b in manifest.get("defects", [])
                        if b.get("status") != "closed" and b.get("severity") in {"critical", "high"}]
    # Pending acceptance is a blocker. Completed measurements can still have low scores.
    accepted_documents = all_docs and all(valid_by_id[cid]["status"] == "PASS" for cid in documents)
    signoff = review(manifest.get("uat_signoff"), "UAT signoff")
    summary = {"run_id": manifest["run_id"], "release": target,
               "compatible_release_recorded": bool(compatible), "scope_approved": scope_approved,
               "independent_current_document_outputs": len(valid_by_id),
               "required_document_outputs": len(documents), "document_evidence_complete": all_docs,
               "formal_bleu_complete": bleu_complete, "formal_formatting_complete": formatting_complete,
               "functionality_complete": functionality_complete, "functionality_meets_module_threshold": functionality_ready,
               "evaluation_complete": evaluation_complete, "open_serious_defects": len(serious_blockers),
               "ready_for_teacher_uat": bool(evaluation_complete and functionality_ready
                                             and accepted_documents and not serious_blockers and signoff),
               "limitation": "Human records are supplied evidence, not independently authenticated identities."}
    scores = [{"release": dict(zip(RELEASE_FIELDS, key)), "source_language": src, "target_language": tgt,
               "case_ids": [x[0] for x in values],
               **diagnostic_bleu([x[1] for x in values], [x[2] for x in values])}
              for (key, src, tgt), values in sorted(bleu_groups.items())]
    dump(output_dir / "release_evidence.json", runs)
    dump(output_dir / "artifact_integrity.json", integrity)
    dump(output_dir / "bleu_results.json", scores)
    dump(output_dir / "functionality_module_summary.json", module_results)
    dump(output_dir / "completion_status.json", summary)
    return summary
