"""Offline internal-evaluation evidence reconciliation; never calls a provider or database.

Raw metrics and BLEU are diagnostic until references, release provenance and the
study's formatting method are confirmed. Human ratings are never auto-filled.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile

from lxml import etree
import pymupdf as fitz
from sacrebleu.metrics import BLEU

RELEASE = "880847620588a0063f6fe593eb171121d0698dbd"
DIMENSIONS = ["Text formatting", "Font consistency", "Layout structure", "Images and figures",
              "Tables and lists", "Captions and labels", "Color and visual styling"]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_hash(path, expected):
    if not Path(path).is_file():
        return "MISSING"
    return "MATCH" if digest(path) == expected else "MISMATCH"


def write_csv(path, rows, fields=None):
    if not rows and fields is None:
        raise ValueError("Cannot infer fields for empty CSV")
    fields = fields or list(rows[0])
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_text(path):
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        with fitz.open(path) as doc:
            return "\n".join(page.get_text("text", sort=True) for page in doc)
    if path.suffix.lower() == ".docx":
        with ZipFile(path) as package:
            root = etree.fromstring(package.read("word/document.xml"),
                                    etree.XMLParser(resolve_entities=False, no_network=True))
        return "\n".join("".join(p.itertext()) for p in root.iter(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"))
    return path.read_text(encoding="utf-8-sig", errors="strict")


def diagnostic_bleu(hypotheses, references):
    if len(hypotheses) != len(references) or not hypotheses:
        raise ValueError("Nonempty aligned candidate/reference lists required")
    metric = BLEU(tokenize="13a", lowercase=False, smooth_method="exp", effective_order=False)
    score = metric.corpus_score(hypotheses, [references])
    return {"diagnostic_bleu": score.score, "signature": str(metric.get_signature()),
            "candidate_tokens": score.sys_len, "reference_tokens": score.ref_len,
            "brevity_penalty": score.bp, "segments": len(hypotheses),
            "status": "DIAGNOSTIC_ONLY_REFERENCES_AND_RELEASE_NOT_VALIDATED"}


def structural_metrics(path):
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        with fitz.open(path) as doc:
            spans = [s for p in doc for b in p.get_text("dict")["blocks"] if "lines" in b
                     for line in b["lines"] for s in line["spans"]]
            return {"format": "pdf", "pages": len(doc),
                    "page_sizes": [[round(p.rect.width, 2), round(p.rect.height, 2)] for p in doc],
                    "font_name_counts": dict(Counter(s["font"] for s in spans)),
                    "font_size_counts": dict(Counter(str(round(s["size"], 1)) for s in spans)),
                    "color_counts": dict(Counter(str(s["color"]) for s in spans)),
                    "image_occurrences": sum(len(p.get_image_info()) for p in doc),
                    "links": sum(len(p.get_links()) for p in doc),
                    "text_characters": sum(len(p.get_text()) for p in doc)}
    if path.suffix.lower() == ".docx":
        with ZipFile(path) as package:
            root = etree.fromstring(package.read("word/document.xml"),
                                    etree.XMLParser(resolve_entities=False, no_network=True))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            counts = {name: len(root.findall(".//w:" + tag, ns))
                      for name, tag in [("paragraphs", "p"), ("tables", "tbl"), ("rows", "tr"),
                                        ("cells", "tc"), ("numbered_paragraphs", "numPr"),
                                        ("drawings", "drawing"), ("legacy_pictures", "pict"),
                                        ("breaks", "br"), ("bold_marks", "b"), ("italic_marks", "i")]}
            attrs = {tag: [dict(e.attrib) for e in root.findall(".//w:" + tag, ns)]
                     for tag in ["rFonts", "sz", "color", "highlight", "spacing", "ind", "jc", "sectPr"]}
            return {"format": "docx", **counts, "attributes": attrs,
                    "media_hashes": sorted(hashlib.sha256(package.read(n)).hexdigest()
                                           for n in package.namelist() if n.startswith("word/media/"))}
    return {"format": path.suffix.lower().lstrip("."), "bytes": path.stat().st_size}


def render_pair(source, output, dest):
    """PDF contact sheets are review aids, never substituted for human ratings."""
    from PIL import Image, ImageDraw
    dest.mkdir(parents=True, exist_ok=True)
    with fitz.open(source) as original, fitz.open(output) as translated:
        for index in range(max(len(original), len(translated))):
            images = []
            for doc in (original, translated):
                if index < len(doc):
                    pix = doc[index].get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
                    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    image.thumbnail((760, 1000))
                    images.append(image)
                else:
                    images.append(Image.new("RGB", (760, 1000), "#dddddd"))
            sheet = Image.new("RGB", (1540, max(i.height for i in images) + 40), "white")
            draw = ImageDraw.Draw(sheet)
            draw.text((10, 10), f"Source, page {index + 1}", fill="black")
            draw.text((790, 10), f"Actual output, page {index + 1}", fill="black")
            sheet.paste(images[0], (0, 35)); sheet.paste(images[1], (780, 35))
            sheet.save(dest / f"page_{index + 1}.png")


def reconcile(root, out):
    packet = root / "output/Trilingua_Internal_Testing_2026-11-15"
    old = root / "output/Trilingua_Live_Test_Results_2026-11-15"
    latest = root / "output/Trilingua_Release_Test_Results_2026-11-16"
    register = load(packet / "TEST_REGISTER.json")
    prior = {c["id"]: c for c in load(old / "results.json")["cases"]}
    fresh = {c["id"]: c for c in load(old / "fresh_inputs/manifest.json")["inputs"]}
    hashes = load(latest / "hash_manifest.json")
    integrity = [{"file": name, "check": verify_hash(latest / name, spec["sha256"])}
                 for name, spec in hashes.items()]
    dump(out / "latest_packet_integrity.json", integrity)
    if any(r["check"] != "MATCH" for r in integrity):
        raise ValueError("Latest packet hash verification failed; do not score unverified evidence")
    evidence = []
    for case in register:
        cid = case["id"]
        previous = prior[cid]
        source = packet / case["upload"]
        reference = packet / case["reference"] if case["reference"] else None
        generated_release = "unverified-historical-2026-11-15"
        actual_source = source
        input_expected = case["input_sha256"]
        output = old / previous.get("downloaded_output", "MISSING").replace("\\", "/")
        if ((cid in fresh and "FRESH" in previous.get("live_status", "").upper())
                or cid in {"F06", "F07", "F08", "F09", "F10"}):
            if cid in fresh:
                actual_source = old / "fresh_inputs" / Path(fresh[cid]["path"].replace("\\", "/")).name
                input_expected = fresh[cid]["fresh_sha256"]
        latest_meta = latest / cid / "live_result.json"
        job_id = previous.get("job_uuid", "")
        status = previous.get("live_status", "NOT RUN")
        provenance = "Prior saved artifact; generation release unverified"
        if latest_meta.exists():
            meta = load(latest_meta)
            source = actual_source = latest / cid / ("source." + case["expected_extension"])
            input_expected = meta["source_sha256"]
            output = latest / cid / ("output." + case["expected_extension"])
            generated_release = RELEASE
            job_id = meta["job_id"]
            status = "FAIL_FORMATTING" if cid != "R_CSV01" else "FAIL_LANGUAGE_REVIEW_REQUIRED"
            provenance = "Fresh production run recorded in latest packet; not rerun in this execution"
        recovered = out / "recovered" / cid / "output.pdf"
        if cid == "D01" and recovered.exists():
            output = recovered
            provenance = "Recovered history 77 output; historical generation, not a new provider run"
        if cid == "F03":
            status = "FAILED_RECONCILED"
            provenance = "Deployment checkpoint and current Jobs page confirm failed; no replay performed"
        evidence.append({
            "case_id": cid, "module": "Document translation",
            "source_language": case["source_language"], "target_language": case["target_language"],
            "source_path": str(actual_source), "registered_source_path": str(packet / case["upload"]),
            "source_sha256": digest(actual_source) if actual_source.is_file() else "",
            "input_integrity": verify_hash(actual_source, input_expected),
            "reference_path": str(reference) if reference and reference.is_file() else "",
            "reference_sha256": digest(reference) if reference and reference.is_file() else "",
            "reference_validation": "PENDING_QUALIFIED_BILINGUAL_REVIEW" if reference else "NO_REFERENCE",
            "output_path": str(output) if output.is_file() else "",
            "output_sha256": digest(output) if output.is_file() else "",
            "prior_output_integrity": verify_hash(output, previous["output_sha256"]) if (
                previous.get("output_sha256") and not latest_meta.exists()) else "NOT_APPLICABLE",
            "generation_release": generated_release, "job_id": job_id, "case_status": status,
            "reuse_from": case.get("reuse_from", ""), "provenance": provenance,
            "valid_final_acceptance": False})
    write_csv(out / "evidence_register.csv", evidence)
    dump(out / "evidence_register.json", evidence)
    return evidence


def build(root, out, render=False):
    out.mkdir(parents=True, exist_ok=True)
    rows = reconcile(root, out)
    metrics, formatting, human, manifest = [], [], [], []
    for row in rows:
        if row["reuse_from"] or not row["output_path"] or row["input_integrity"] != "MATCH":
            continue
        source, output = Path(row["source_path"]), Path(row["output_path"])
        if source.suffix.lower() not in {".docx", ".pdf"}:
            continue
        pair = {"case_id": row["case_id"], "generation_release": row["generation_release"],
                "source_sha256": row["source_sha256"], "output_sha256": row["output_sha256"],
                "source": structural_metrics(source), "output": structural_metrics(output)}
        metrics.append(pair)
        for dim in DIMENSIONS:
            formatting.append({"case_id": row["case_id"], "dimension": dim,
                "generation_release": row["generation_release"], "automated_score": "",
                "manual_score": "", "status": "METHOD_AND_HUMAN_RATINGS_PENDING",
                "raw_metrics": f"structural_metrics.json#{row['case_id']}"})
            human.append({"case_id": row["case_id"], "dimension": dim, "rating": "",
                "reviewer": "", "review_date": "", "page_or_element": "", "notes": "",
                "source_path": row["source_path"], "output_path": row["output_path"]})
        if render and source.suffix.lower() == ".pdf":
            render_pair(source, output, out / "review_pages" / row["case_id"])
    dump(out / "structural_metrics.json", metrics)
    write_csv(out / "formatting_results.csv", formatting)
    # Never overwrite a completed human review form on resume.
    if not (out / "human_formatting_review.csv").exists():
        write_csv(out / "human_formatting_review.csv", human)

    scores, groups = [], defaultdict(list)
    for row in rows:
        if not row["case_id"].startswith("D"):
            continue
        entry = {k: row[k] for k in ["case_id", "source_language", "target_language", "source_path",
                 "source_sha256", "reference_path", "reference_sha256", "reference_validation",
                 "output_path", "output_sha256", "generation_release"]}
        entry["segmentation"] = "One complete PDF per segment, all pages in spatial reading order; whitespace collapsed"
        entry["formal_score"] = None
        if row["output_path"] and row["reference_path"] and row["input_integrity"] == "MATCH":
            textdir = out / "bleu_inputs" / row["case_id"]
            textdir.mkdir(parents=True, exist_ok=True)
            candidate = " ".join(read_text(row["output_path"]).split())
            reference = " ".join(read_text(row["reference_path"]).split())
            source_text = " ".join(read_text(row["source_path"]).split())
            for name, text in [("candidate", candidate), ("reference", reference), ("source", source_text)]:
                (textdir / (name + ".txt")).write_text(text + "\n", encoding="utf-8")
            entry["candidate_text_sha256"] = digest(textdir / "candidate.txt")
            entry["reference_text_sha256"] = digest(textdir / "reference.txt")
            if candidate and reference:
                entry.update(diagnostic_bleu([candidate], [reference]))
                groups[(row["generation_release"], row["source_language"], row["target_language"])].append(
                    (row["case_id"], candidate, reference))
            else:
                entry["status"] = "BLOCKED_EMPTY_EXTRACTION"
        else:
            entry["status"] = "BLOCKED_MISSING_VALID_ARTIFACT_OR_REFERENCE"
        manifest.append(entry)
    for (release, src, tgt), group in sorted(groups.items()):
        scores.append({"generation_release": release, "source_language": src, "target_language": tgt,
                       "case_ids": [x[0] for x in group],
                       **diagnostic_bleu([x[1] for x in group], [x[2] for x in group])})
    dump(out / "bleu_manifest.json", manifest)
    write_csv(out / "bleu_manifest.csv", [
        {k: e.get(k, "") for k in ["case_id", "source_language", "target_language", "generation_release",
                                   "reference_validation", "status", "diagnostic_bleu",
                                   "candidate_text_sha256", "reference_text_sha256"]} for e in manifest])
    dump(out / "bleu_results.json", {"purpose": "Diagnostic only; not final study results",
         "scale": "0-100", "signature_settings": "13a; mixed case; exponential smoothing; effective_order=false",
         "prohibited_inference": "BLEU is neither semantic accuracy nor a percentage of correct sentences",
         "scoring_surfaces": "All PDF pages, including retained source text; no content removed to raise scores",
         "manual_segment_alignment": "PENDING", "release_and_reference_validation": "PENDING",
         "directions": scores})

    if (out / "functionality_cases.json").exists():
        cases = load(out / "functionality_cases.json")
        live_path = out / "current_live_checks.json"
        live = load(live_path) if live_path.exists() else []
        passed_titles = {x["template_title"]: x for x in live if x.get("status") == "PASS" and x.get("template_title")}
        for case in cases:
            if case["title"] in passed_titles:
                case["status"] = "PASS"
                case["evidence"] = "current_live_checks.json"
        write_csv(out / "functionality_results.csv", cases)
        modules = []
        for role, module in sorted({(c["role"], c["module"]) for c in cases}):
            subset = [c for c in cases if (c["role"], c["module"]) == (role, module)]
            passes = sum(c["status"] == "PASS" for c in subset)
            modules.append({"role": role, "module": module, "required_template_rows": len(subset),
                            "verified_current_passes": passes, "not_run": sum(c["status"] == "NOT_RUN" for c in subset),
                            "provisional_verified_fraction_percent": round(100 * passes / len(subset), 2),
                            "closure": "INCOMPLETE_COMPOUND_ROWS_REQUIRE_FINAL_CASE_MAPPING"})
        dump(out / "functionality_module_summary.json", modules)
        # Historical checks are retained without being promoted to current-role passes.
        dump(out / "historical_functionality_checks.json", load(
            root / "output/Trilingua_Live_Test_Results_2026-11-15/functional_checks.json"))

    summary = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "registered_document_case_ids": len(rows),
               "independent_required_document_runs": sum(not r["reuse_from"] for r in rows),
               "cases_with_saved_outputs": sum(bool(r["output_path"]) for r in rows),
               "independent_saved_outputs": sum(bool(r["output_path"]) and not r["reuse_from"] for r in rows),
               "diagnostic_formatting_pairs": len(metrics),
               "diagnostic_bleu_directions": len(scores),
               "formal_bleu_complete": False, "formal_formatting_complete": False,
               "functionality_complete": False, "ready_for_teacher_uat": False,
               "reason": "Required functional cases and final-release outputs remain; reference validation, formatting methodology and human ratings pending"}
    dump(out / "completion_status.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--run-manifest", type=Path,
                        help="Explicit release-specific run; omission retains historical diagnostic mode")
    args = parser.parse_args()
    if args.run_manifest:
        from benchmarks.release_evaluation import record_run
        result = record_run(args.run_manifest, args.output)
    else:
        result = build(args.root, args.output, args.render)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

