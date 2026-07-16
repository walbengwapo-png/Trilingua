# -*- coding: utf-8 -*-
"""
Heuristic Classifier — rule-based semantic role detection.
Fast, deterministic, no LLM calls. Handles high-confidence patterns.
"""

import re
from typing import Optional

from intelligence.graph.document_graph import DocumentObject, SemanticRole
from intelligence.semantic.role_registry import ROLE_PATTERNS


class HeuristicClassifier:
    """Rule-based semantic role classifier using regex patterns."""

    def __init__(self):
        # Compile all patterns for performance
        self._compiled = []
        for rp in ROLE_PATTERNS:
            compiled_patterns = []
            for pat in rp.patterns:
                try:
                    compiled_patterns.append(re.compile(pat, re.IGNORECASE))
                except re.error:
                    pass
            self._compiled.append((rp, compiled_patterns))

    def classify(self, obj: DocumentObject) -> Optional[tuple[SemanticRole, float]]:
        """Classify a single document object using heuristic rules.

        Args:
            obj: The document object to classify.

        Returns:
            (role, confidence) tuple if matched, None if no heuristic match.
        """
        text = obj.original_text.strip()
        if not text:
            return None

        # Try patterns in priority order
        for rp, compiled_patterns in self._compiled:
            for pattern in compiled_patterns:
                if pattern.search(text):
                    return (rp.role, rp.min_confidence)

        # Fallback: check specific heuristic functions
        if self._is_heading(text, obj):
            return (SemanticRole.HEADING_3, 0.70)
        if self._is_list_item(text):
            return (SemanticRole.LIST_ITEM, 0.80)
        if self._is_table_cell(text, obj):
            return (SemanticRole.TABLE_CELL, 0.75)

        return None

    def classify_batch(
        self, objects: list[DocumentObject]
    ) -> dict[str, tuple[SemanticRole, float]]:
        """Classify multiple objects at once.

        Returns:
            Dict mapping object_id → (role, confidence)
        """
        results = {}
        for obj in objects:
            result = self.classify(obj)
            if result:
                results[obj.id] = result
        return results

    # ── Heuristic Functions ──────────────────────────────────────

    def _is_heading(self, text: str, obj: DocumentObject) -> bool:
        """Detect if text is a heading based on style and content."""
        # Check style: bold + larger font
        if obj.style.bold and obj.style.font_size >= 14:
            return True
        # Check content: short, capitalized, no period
        if len(text.split()) <= 10 and not text.endswith("."):
            if text[0].isupper() and not text.endswith("?"):
                return True
        return False

    def _is_list_item(self, text: str) -> bool:
        """Detect if text is a list item."""
        patterns = [
            r"^[-*•]\s+",  # Bullet points
            r"^\d+[\.\)]\s+",  # Numbered items
            r"^[a-z][\.\)]\s+",  # Lettered items
            r"^[ivxlcdm]+[\.\)]\s+",  # Roman numerals
        ]
        return any(re.match(p, text, re.IGNORECASE) for p in patterns)

    def _is_table_cell(self, text: str, obj: DocumentObject) -> bool:
        """Detect if object is a table cell based on metadata."""
        return obj.object_type.name == "TABLE" or "table_index" in obj.metadata

    def is_answer_blank(self, text: str) -> bool:
        """Check if text is an answer blank."""
        return bool(re.match(r"^_{2,}$", text.strip()))

    def is_answer_key(self, text: str) -> bool:
        """Check if text is an answer key entry."""
        return bool(re.match(r"^\d+\s*[\.\)]\s*[A-D]", text.strip()))

    def is_mc_option(self, text: str) -> bool:
        """Check if text is a multiple choice option."""
        return bool(re.match(r"^[A-Da-d][\.\)]\s+\w", text.strip()))

    def is_question(self, text: str) -> bool:
        """Check if text is a question."""
        return text.strip().endswith("?")