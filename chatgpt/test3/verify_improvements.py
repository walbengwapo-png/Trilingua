"""Offline reconstruction replay. Uses saved translations; never calls providers."""
import copy
import hashlib
import json
import sys
from pathlib import Path

import fitz

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "trilingua-code" / "Model"))
from document.reconstructor import write_pdf_preserved
from validators.hallucination_detector import translation_content_issue
from validators.translation_validator import PDFValidationError


def main():
    destination = HERE / "improvements"
    destination.mkdir(exist_ok=True)
    manifest = json.loads((HERE / "evidence" / "manifest.json").read_text(encoding="utf-8"))
    results = []
    for index, source in enumerate(sorted(HERE.glob("[0-9][0-9]_*.pdf")), 1):
        payload = json.loads((HERE / "evidence" / f"{index:02d}_response.json").read_text(encoding="utf-8"))
        sidecar = payload["sidecar"]
        blocks = copy.deepcopy(sidecar["blocks"])
        output = destination / (source.stem + "_reconstructed.pdf")
        invalid = [{"block": b["block_index"], "issue": translation_content_issue(b["source_text"], b["text"])}
                   for b in blocks if not b.get("passthrough") and
                   translation_content_issue(b["source_text"], b["text"])]
        result = {"id": index, "source": source.name, "output": output.name,
                  "source_unchanged": hashlib.sha256(source.read_bytes()).hexdigest() == manifest["files"][index - 1]["sha256"],
                  "historical_content_rejected_by_new_guard": invalid}
        fitz.TOOLS.mupdf_warnings()
        try:
            result["validation"] = write_pdf_preserved(
                blocks, str(source), str(output), source_lang=sidecar["source_lang"],
                target_lang=sidecar["target_lang"])
        except PDFValidationError as error:
            result["validation"] = error.report
        except Exception as error:
            result["error"] = str(error)
        result["mupdf_diagnostics"] = fitz.TOOLS.mupdf_warnings()
        if output.exists():
            with fitz.open(output) as doc:
                result["pages"] = len(doc)
                result["bytes"] = output.stat().st_size
                for page in doc:
                    page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2)).save(
                        str(destination / f"{index:02d}_page_{page.number + 1:02d}.png"))
        results.append(result)
        print(index, result.get("validation", {}).get("status", "error"), result.get("pages", 0),
              len(result.get("validation", {}).get("issues", [])), result.get("error", ""), flush=True)
        (destination / "replay-results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
