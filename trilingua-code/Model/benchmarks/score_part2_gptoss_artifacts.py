"""Score supplied Part2 GPT-OSS PDFs without invoking a translation provider."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
from sacrebleu import corpus_bleu, corpus_chrf


ROOT = Path(__file__).resolve().parents[3]
PART2 = ROOT / "chatgpt" / "Part2 test"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(path: Path) -> str:
    with fitz.open(path) as document:
        return " ".join(" ".join(page.get_text("text").split()) for page in document).strip()


def record(identifier: str, direction: str, source: Path, reference: Path, output: Path) -> dict:
    hypothesis = text(output)
    expected = text(reference)
    with fitz.open(output) as document:
        pages = len(document)
    return {
        "id": identifier,
        "direction": direction,
        "source": source.name,
        "reference": reference.name,
        "output": output.name,
        "output_path": str(output),
        "output_sha256": sha256(output),
        "page_count": pages,
        "text_characters": len(hypothesis),
        "layout_validation": "pass" if pages == 25 and hypothesis else "fail",
        "bleu": round(corpus_bleu([hypothesis], [[expected]]).score, 2),
        "chrf": round(corpus_chrf([hypothesis], [[expected]]).score, 2),
        "runtime_metadata": "Not supplied with the PDF artifact",
        "normalization": "all pages; whitespace collapsed; no content removed",
    }


def main() -> None:
    english = PART2 / "60 Heaven  God s Beautiful Home.pdf"
    cebuano = PART2 / "60 Langit  Ang Nindot nga Puluy-anan sa Dios.pdf"
    output = {
        "iteration_title": "Part2 Iteration 2 GPT OSS supplied artifacts",
        "method": "Corpus BLEU and chrF over all PDF pages after whitespace normalization only.",
        "gptoss_artifacts": [
            record("en-to-ceb", "English to Cebuano", english, cebuano, PART2 / "gpt-oss" / "e598d3ff-796c-4e07-890c-3b8be50b0875.pdf"),
            record("ceb-to-en", "Cebuano to English", cebuano, english, PART2 / "gpt-oss" / "60 Langit  Ang Nindot nga Puluy-anan sa Dios_translated.pdf"),
        ],
    }
    (PART2 / "iteration-2-gptoss-artifacts.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
