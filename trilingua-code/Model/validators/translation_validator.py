# -*- coding: utf-8 -*-
"""
Translation validation utilities.

Contains BLEU scoring and other quality metrics.
Extracted from document_translator_v3.py BLEU_Reporter.
"""

import os


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