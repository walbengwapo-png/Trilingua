# -*- coding: utf-8 -*-
"""
Translation validation utilities.

Contains BLEU scoring and other quality metrics.
Extracted from document_translator_v3.py BLEU_Reporter.
"""

import os
import re
import unicodedata


class PDFValidationError(ValueError):
    """A generated PDF failed deterministic saved-output checks."""
    def __init__(self, report):
        self.report = report
        issues = report.get("issues", [])
        super().__init__("Saved PDF validation failed: " + "; ".join(issues[:8]))


def validate_pdf_output(path, placements, source_pages, blocks=None):
    """Reopen the saved file and check each placed fragment in its own region.

    This is content coverage and geometry validation, not a linguistic score.
    """
    import fitz

    def normalized(text):
        text = unicodedata.normalize("NFKC", text)
        text = re.sub(r"[\u00ad\u2010\u2011]", "-", text)
        return re.sub(r"[\s\u200b]+", "", text)

    issues, content_issues, layout_issues = [], [], []
    content_findings = []
    records = []
    for index, block in enumerate(blocks or []):
        if block.get("passthrough") or not block.get("text", "").strip():
            continue
        fragments = "".join(p["text"] for p in placements
                            if p["block_index"] == index and p["action"] in {"fit", "continuation"})
        if normalized(block["text"]) != normalized(fragments):
            content_issues.append(f"Block {index}: incomplete block placement")
    with fitz.open(path) as doc:
        for placement in placements:
            page_number = placement.get("page")
            prefix = f"Block {placement['block_index']}"
            if page_number is None or page_number >= len(doc):
                content_issues.append(f"{prefix}: missing output page")
                continue
            page = doc[page_number]
            rect = fitz.Rect(placement["rect"])
            clip = rect + (-.5, -.5, .5, .5)
            text = page.get_text("text", clip=clip, sort=True)
            if normalized(placement["text"]) not in normalized(text):
                content_issues.append(f"{prefix}: missing rendered text on page {page_number + 1}")
                content_findings.append({"block_index": placement["block_index"],
                                         "page": page_number, "rect": list(rect),
                                         "expected": placement["text"], "observed": text})
            if not (page.rect + (-.5, -.5, .5, .5)).contains(rect):
                layout_issues.append(f"{prefix}: text outside page {page_number + 1}")
            for block in page.get_text("dict", clip=clip)["blocks"]:
                for line in block.get("lines", []):
                    if placement["action"] != "passthrough" and (
                            abs(line["dir"][0] - 1) > .01 or abs(line["dir"][1]) > .01):
                        layout_issues.append(f"{prefix}: text orientation on page {page_number + 1}")
            records.append({key: placement[key] for key in
                            ("block_index", "source_page", "rect", "font_size", "action")}
                           | {"page": page_number})
        # ponytail: pairwise fragment rectangles; spatial index if document size warrants it.
        for i, left in enumerate(records):
            for right in records[i + 1:]:
                if left["page"] != right["page"]:
                    continue
                if left["action"] == right["action"] == "passthrough":
                    continue
                overlap = fitz.Rect(left["rect"]) & fitz.Rect(right["rect"])
                if not overlap.is_empty and overlap.get_area() > 2 and overlap.height > 1:
                    layout_issues.append(
                        f"Blocks {left['block_index']}/{right['block_index']}: overlap on page {left['page'] + 1}")
        page_count = len(doc)
    issues.extend(content_issues)
    issues.extend(layout_issues)
    return {
        "status": "failed" if issues else "passed",
        "content_coverage": "failed" if content_issues else "passed",
        "layout": "failed" if layout_issues else "passed",
        "linguistic_accuracy": "unverified",
        "source_pages": source_pages, "output_pages": page_count,
        "continuation_pages": max(0, page_count - source_pages),
        "checked_fragments": len(placements), "issues": issues,
        "content_findings": content_findings,
        "blocks": records,
    }


class BLEUReporter:
    """Computes BLEU scores between translated blocks and a reference file.

    Uses sacrebleu for BLEU computation. Returns ``None`` (with a warning)
    when the reference file is missing, unreadable, or empty — never raises.
    """

    def compute(self, blocks, reference_file):
        """Compute BLEU score for *blocks* against *reference_file*.

        Parameters
        ----------
        blocks : list[dict]
            Translated blocks, each with a ``"text"`` key.
        reference_file : str | None
            Path to a plain-text reference file (one sentence per line).

        Returns
        -------
        float | None
            BLEU score in ``[0.0, 100.0]``, or ``None`` when scoring is not possible.
        """
        if reference_file is None:
            return None

        if not os.path.isfile(reference_file):
            print(f"  ⚠️  BLEU: reference file not found: {reference_file}")
            return None

        try:
            with open(reference_file, "r", encoding="utf-8") as f:
                ref_lines = [line.strip() for line in f if line.strip()]
        except OSError as e:
            print(f"  ⚠️  BLEU: cannot read reference file: {e}")
            return None

        if not ref_lines:
            print(f"  ⚠️  BLEU: reference file is empty: {reference_file}")
            return None

        hyp_texts = [b.get("text", "") for b in blocks if b.get("text", "").strip()]
        if not hyp_texts:
            print(f"  ⚠️  BLEU: no translated texts to score")
            return None

        min_len = min(len(hyp_texts), len(ref_lines))
        if len(hyp_texts) != len(ref_lines):
            print(f"  ⚠️  BLEU: count mismatch (hyp={len(hyp_texts)} ref={len(ref_lines)}), "
                  f"aligning over {min_len} pairs")

        try:
            import sacrebleu
            refs = [ref_lines[:min_len]]
            hyps = hyp_texts[:min_len]
            bleu = sacrebleu.corpus_bleu(hyps, refs)
            return bleu.score
        except Exception as e:
            print(f"  ⚠️  BLEU: computation error: {e}")
            return None


class LayoutValidator:
    """Validates document layout after reconstruction.

    Checks for missing blocks, block count mismatches, and type preservation.
    """

    @staticmethod
    def validate(original_blocks: list[dict], translated_blocks: list[dict]) -> list[str]:
        """Validate reconstruction quality.

        Args:
            original_blocks: Original extracted blocks.
            translated_blocks: Translated blocks after reconstruction.

        Returns:
            A list of warning strings. Empty if validation passes.
        """
        warnings = []

        if len(original_blocks) != len(translated_blocks):
            warnings.append(
                f"Block count mismatch: {len(original_blocks)} original vs "
                f"{len(translated_blocks)} translated"
            )

        # Check for empty translations
        for i, block in enumerate(translated_blocks):
            if not block.get("text", "").strip():
                orig_text = original_blocks[i]["text"] if i < len(original_blocks) else "?"
                warnings.append(f"Block {i} is empty after translation (original: '{orig_text[:50]}')")

        return warnings
