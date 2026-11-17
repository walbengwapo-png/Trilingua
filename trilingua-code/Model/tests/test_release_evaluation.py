"""Evidence failures must never turn into study completion or UAT readiness."""
import copy
import json

import pymupdf as fitz
import pytest

from benchmarks.complete_internal_evaluation import DIMENSIONS, digest
from benchmarks.release_evaluation import record_run


@pytest.fixture
def completed_manifest(tmp_path):
    # Synthetic review records test the gate only; they are never study evidence.
    evidence = tmp_path / "synthetic-review.txt"
    evidence.write_text("Synthetic test fixture, no real reviewer approval.")
    artifact = lambda p: {"path": str(p), "sha256": digest(p)}
    review = {"reviewer": "SYNTHETIC", "date": "2026-01-01", "decision": "approved",
              "evidence": artifact(evidence)}
    release = {"app_commit": "a" * 40, "engine_commit": "b" * 40, "app_revision": "v2", "engine_revision": "v2"}
    ids = [f"D{i}" for i in range(10)]
    directions = [(a, b) for a in ("en", "fil", "ceb") for b in ("en", "fil", "ceb") if a != b]
    docs = []
    for i, cid in enumerate(ids):
        p = tmp_path / f"{cid}.pdf"
        with fitz.open() as doc:
            doc.new_page().insert_text((40, 40), f"Unique document {i}: pupils read their books every morning.")
            doc.save(p)
        src, tgt = directions[i % 6]
        docs.append({"case_id": cid, "source": artifact(p), "output": artifact(p),
                     "reference": artifact(p), "reference_validation": copy.deepcopy(review),
                     "release": release, "provenance": "fresh", "job_id": f"job-{i}",
                     "provider": "synthetic", "model": "mock", "status": "PASS",
                     "options": {"source_language": src, "target_language": tgt},
                     "formatting_review": {**copy.deepcopy(review), "dimensions": dict.fromkeys(DIMENSIONS, 4)}})
    functional = [{"case_id": role, "role": role, "module": "History", "atomic": True}
                  for role in ("normal_user", "admin")]
    manifest = {"schema_version": 1, "run_id": "SYNTHETIC_TEST_ONLY", "release": release,
                "scope": {"approval": review, "document_case_ids": ids, "bleu_case_ids": ids,
                          "formatting_case_ids": ids, "functionality_cases": functional,
                          "formatting_method": {"id": "attribute_and_visual", "approval": copy.deepcopy(review),
                                                "rating_scale": {"min": 1, "max": 5}}},
                "documents": docs, "functionality": [
                    {**c, "status": "PASS", "tester": "SYNTHETIC", "executed_at": "2026-01-01",
                     "release": release, "evidence": artifact(evidence)} for c in functional],
                "uat_signoff": review}
    return manifest, tmp_path


def run_fixture(manifest, path):
    manifest_path = path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return record_run(manifest_path, path / "results")


def test_full_measurement_and_separate_readiness_gates(completed_manifest):
    m, p = completed_manifest
    result = run_fixture(m, p)
    assert result["evaluation_complete"] and result["ready_for_teacher_uat"]
    m["defects"] = [{"severity": "high", "status": "open"}]
    assert run_fixture(m, p)["evaluation_complete"]
    assert not run_fixture(m, p)["ready_for_teacher_uat"]


@pytest.mark.parametrize("failure", ["mixed_release", "missing_hash", "changed_output", "reused_output",
                                    "reused_job", "missing_rating", "pending_reference", "missing_scope",
                                    "unsupported_method", "compound_case", "wrong_role", "no_signoff"])
def test_incomplete_or_ineligible_evidence_cannot_be_uat_ready(completed_manifest, failure):
    m, p = completed_manifest
    doc = m["documents"][-1]
    if failure == "mixed_release":
        doc["release"] = {**doc["release"], "engine_commit": "older"}
    elif failure == "missing_hash":
        del doc["output"]["sha256"]
    elif failure == "changed_output":
        (p / "D9.pdf").write_bytes(b"changed")
    elif failure == "reused_output":
        doc["output"] = m["documents"][0]["output"]
    elif failure == "reused_job":
        doc["job_id"] = m["documents"][0]["job_id"]
    elif failure == "missing_rating":
        doc["formatting_review"]["dimensions"].pop(DIMENSIONS[0])
    elif failure == "pending_reference":
        doc["reference_validation"]["decision"] = "pending"
    elif failure == "missing_scope":
        m["scope"]["approval"] = {}
    elif failure == "unsupported_method":
        m["scope"]["formatting_method"]["id"] = "embedding_cosine"
    elif failure == "compound_case":
        m["scope"]["functionality_cases"][0]["atomic"] = False
    elif failure == "wrong_role":
        m["functionality"][0]["role"] = "admin"
    elif failure == "no_signoff":
        del m["uat_signoff"]
    result = run_fixture(m, p)
    assert not result["ready_for_teacher_uat"]
    assert result["evaluation_complete"] == (failure == "no_signoff")


def test_module_threshold_is_not_hidden_by_total_pass_rate(completed_manifest):
    m, p = completed_manifest
    m["functionality"][0]["status"] = "FAIL"
    result = run_fixture(m, p)
    assert result["functionality_complete"]  # Executed, with a recorded failure.
    assert not result["functionality_meets_module_threshold"]
    assert not result["ready_for_teacher_uat"]


def test_duplicate_case_ids_are_rejected(completed_manifest):
    m, p = completed_manifest
    m["documents"].append(m["documents"][0])
    with pytest.raises(ValueError, match="Duplicate document case ID"):
        run_fixture(m, p)
