# -*- coding: utf-8 -*-
"""
Validation pipeline.

Responsible for quality checks after translation:
- Layout validation (missing text, formatting)
- Translation validation (numbers, placeholders, hyperlinks)
- Hallucination detection
- Consistency checking

Can be run independently or as part of the document pipeline.
"""

from validators.translation_validator import LayoutValidator, BLEUReporter
from validators.hallucination_detector import sanitize_translation, detect_hallucination


class ValidationPipeline:
    """Runs quality validation checks on translations."""

    def __init__(self):
        self.layout_validator = LayoutValidator()
        self.bleu_reporter = BLEUReporter()

    def validate_translation(self, source_text: str, translated_text: str) -> list[str]:
        """Validate a single translation.

        Args:
            source_text: The original source text.
            translated_text: The translated text.

        Returns:
            A list of warning strings. Empty if validation passes.
        """
        warnings = []

        # Check for empty translation
        if not translated_text or not translated_text.strip():
            warnings.append("Translation is empty")
            return warnings

        # Check for hallucination
        is_hallucinated, reason = detect_hallucination(translated_text, source_text)
        if is_hallucinated:
            warnings.append(f"Hallucination detected: {reason}")

        # Check number preservation
        source_numbers = set(part for part in source_text.split() if part.replace(",", "").replace(".", "").isdigit())
        target_numbers = set(part for part in translated_text.split() if part.replace(",", "").replace(".", "").isdigit())
        missing_numbers = source_numbers - target_numbers
        if missing_numbers:
            warnings.append(f"Missing numbers in translation: {missing_numbers}")

        # Check for excessive length difference
        src_len = len(source_text.split())
        tgt_len = len(translated_text.split())
        if src_len > 0 and tgt_len > 0:
            ratio = tgt_len / src_len
            if ratio < 0.2:
                warnings.append(f"Translation too short ({tgt_len} vs {src_len} words, ratio={ratio:.2f})")
            elif ratio > 8.0:
                warnings.append(f"Translation too long ({tgt_len} vs {src_len} words, ratio={ratio:.2f})")

        return warnings

    def validate_document(self, original_blocks: list[dict],
                          translated_blocks: list[dict]) -> list[str]:
        """Validate a complete document translation.

        Args:
            original_blocks: Original extracted blocks.
            translated_blocks: Translated blocks.

        Returns:
            A list of warning strings.
        """
        warnings = []

        # Layout validation
        layout_warnings = self.layout_validator.validate(original_blocks, translated_blocks)
        warnings.extend(layout_warnings)

        # Validate each block
        for i, (orig, trans) in enumerate(zip(original_blocks, translated_blocks)):
            block_warnings = self.validate_translation(
                orig.get("text", ""), trans.get("text", "")
            )
            for w in block_warnings:
                warnings.append(f"Block {i}: {w}")

        return warnings