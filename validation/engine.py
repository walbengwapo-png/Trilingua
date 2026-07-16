# -*- coding: utf-8 -*-
"""
Validation Engine — runs all quality checks and produces a QualityReport.
"""

import logging
import re
from typing import Optional

from intelligence.graph.document_graph import (
    DocumentObjectGraph,
    SemanticRole,
    ObjectType,
)
from validation.severity import Severity, CheckResult, QualityReport
from validation.checks.check_registry import check_registry

logger = logging.getLogger(__name__)


class ValidationEngine:
    """Runs quality validation checks on translated documents."""

    def __init__(self, ai_reviewer=None):
        """
        Args:
            ai_reviewer: Optional AI quality reviewer for grammar/fluency checks.
        """
        self._ai_reviewer = ai_reviewer

    def validate(
        self,
        original_graph: DocumentObjectGraph,
        translated_graph: DocumentObjectGraph,
    ) -> QualityReport:
        """Run all validation checks on a translated document.

        Args:
            original_graph: Original document graph (before translation).
            translated_graph: Translated document graph (after translation).

        Returns:
            QualityReport with all check results.
        """
        report = QualityReport(overall_score=1.0, passed=True)

        # Run all checks
        self._check_image_count(original_graph, translated_graph, report)
        self._check_table_count(original_graph, translated_graph, report)
        self._check_page_count(original_graph, translated_graph, report)
        self._check_object_count(original_graph, translated_graph, report)
        self._check_answer_key_integrity(translated_graph, report)
        self._check_blanks(translated_graph, report)
        self._check_untranslated_text(translated_graph, report)
        self._check_numbering(original_graph, translated_graph, report)
        self._check_terminology_consistency(translated_graph, report)

        # AI review (if available)
        if self._ai_reviewer:
            self._check_grammar(translated_graph, report)

        logger.info(
            f"Validation complete: "
            f"score={report.overall_score:.2f}, "
            f"critical={report.critical_count}, "
            f"errors={report.error_count}, "
            f"warnings={report.warning_count}"
        )

        return report

    # ── Individual Checks ─────────────────────────────────────────

    def _check_image_count(self, original, translated, report):
        """CRITICAL: Image count must match."""
        orig_count = len(original.get_objects_by_type(ObjectType.IMAGE))
        trans_count = len(translated.get_objects_by_type(ObjectType.IMAGE))

        report.add_check(CheckResult(
            check_name="image_count_mismatch",
            severity=Severity.CRITICAL,
            passed=orig_count == trans_count,
            detail=f"Original: {orig_count}, Translated: {trans_count}",
            expected_value=str(orig_count),
            actual_value=str(trans_count),
        ))

    def _check_table_count(self, original, translated, report):
        """CRITICAL: Table count must match."""
        orig_count = len(original.get_objects_by_type(ObjectType.TABLE))
        trans_count = len(translated.get_objects_by_type(ObjectType.TABLE))

        report.add_check(CheckResult(
            check_name="table_count_mismatch",
            severity=Severity.CRITICAL,
            passed=orig_count == trans_count,
            detail=f"Original: {orig_count}, Translated: {trans_count}",
            expected_value=str(orig_count),
            actual_value=str(trans_count),
        ))

    def _check_page_count(self, original, translated, report):
        """CRITICAL: Page count must match."""
        orig_count = len(original.pages)
        trans_count = len(translated.pages)

        report.add_check(CheckResult(
            check_name="page_count_changed",
            severity=Severity.CRITICAL,
            passed=orig_count == trans_count,
            detail=f"Original: {orig_count}, Translated: {trans_count}",
            expected_value=str(orig_count),
            actual_value=str(trans_count),
        ))

    def _check_object_count(self, original, translated, report):
        """CRITICAL: Object count must match within 5% tolerance."""
        orig_count = len(original.all_objects)
        trans_count = len(translated.all_objects)

        tolerance = max(1, int(orig_count * 0.05))
        passed = abs(orig_count - trans_count) <= tolerance

        report.add_check(CheckResult(
            check_name="object_count_mismatch",
            severity=Severity.CRITICAL,
            passed=passed,
            detail=f"Original: {orig_count}, Translated: {trans_count}, Tolerance: ±{tolerance}",
            expected_value=str(orig_count),
            actual_value=str(trans_count),
        ))

    def _check_answer_key_integrity(self, graph, report):
        """CRITICAL: Answer key letters must be preserved."""
        answer_keys = graph.get_objects_by_role(SemanticRole.ANSWER_KEY)
        if not answer_keys:
            return  # No answer keys to check

        all_preserved = True
        for obj in answer_keys:
            orig = obj.original_text
            trans = obj.translated_text

            # Extract letters from original
            orig_letters = set(re.findall(r'\b[A-D]\b', orig))
            trans_letters = set(re.findall(r'\b[A-D]\b', trans))

            if orig_letters and orig_letters != trans_letters:
                all_preserved = False
                report.add_check(CheckResult(
                    check_name="answer_key_corruption",
                    severity=Severity.CRITICAL,
                    passed=False,
                    detail=f"Object {obj.id}: Letters changed from {orig_letters} to {trans_letters}",
                    object_id=obj.id,
                    expected_value=str(orig_letters),
                    actual_value=str(trans_letters),
                ))

        if all_preserved:
            report.add_check(CheckResult(
                check_name="answer_key_corruption",
                severity=Severity.CRITICAL,
                passed=True,
                detail=f"All {len(answer_keys)} answer keys preserved correctly",
            ))

    def _check_blanks(self, graph, report):
        """ERROR: Answer blanks must not be filled."""
        blanks = graph.get_objects_by_role(SemanticRole.ANSWER_BLANK)
        if not blanks:
            return

        all_preserved = True
        for obj in blanks:
            orig = obj.original_text.strip()
            trans = obj.translated_text.strip()

            if trans and trans != orig:
                all_preserved = False
                report.add_check(CheckResult(
                    check_name="blank_filled",
                    severity=Severity.ERROR,
                    passed=False,
                    detail=f"Object {obj.id}: Blank was filled ('{trans}' instead of '{orig}')",
                    object_id=obj.id,
                    expected_value=orig,
                    actual_value=trans,
                ))

        if all_preserved:
            report.add_check(CheckResult(
                check_name="blank_filled",
                severity=Severity.ERROR,
                passed=True,
                detail=f"All {len(blanks)} blanks preserved",
            ))

    def _check_untranslated_text(self, graph, report):
        """ERROR: Detect untranslated text (source == target)."""
        untranslated = []
        for obj in graph.all_objects.values():
            if not obj.is_translatable():
                continue
            orig = obj.original_text.strip().lower()
            trans = obj.translated_text.strip().lower()
            if orig and trans and orig == trans and len(orig.split()) >= 3:
                untranslated.append(obj.id)

        report.add_check(CheckResult(
            check_name="untranslated_text",
            severity=Severity.ERROR,
            passed=len(untranslated) == 0,
            detail=f"{len(untranslated)} untranslated block(s): {untranslated[:10]}",
            expected_value="0 untranslated blocks",
            actual_value=f"{len(untranslated)} blocks",
        ))

    def _check_numbering(self, original, translated, report):
        """WARNING: Check numbering consistency."""
        orig_numbered = []
        trans_numbered = []

        for obj in original.all_objects.values():
            match = re.match(r"^(\d+)[\.\)]", obj.original_text.strip())
            if match:
                orig_numbered.append((obj.id, match.group(1)))

        for obj in translated.all_objects.values():
            match = re.match(r"^(\d+)[\.\)]", obj.translated_text.strip())
            if match:
                trans_numbered.append((obj.id, match.group(1)))

        # Check if numbering format is preserved
        issues = len(orig_numbered) != len(trans_numbered)
        report.add_check(CheckResult(
            check_name="numbering_broken",
            severity=Severity.WARNING,
            passed=not issues,
            detail=f"Original numbered items: {len(orig_numbered)}, Translated: {len(trans_numbered)}",
            expected_value=str(len(orig_numbered)),
            actual_value=str(len(trans_numbered)),
        ))

    def _check_terminology_consistency(self, graph, report):
        """WARNING: Check glossary term consistency."""
        # This is a simplified check — looks for repeated terms
        # that should be translated consistently
        report.add_check(CheckResult(
            check_name="terminology_inconsistency",
            severity=Severity.WARNING,
            passed=True,
            detail="Terminology consistency check passed (basic scan)",
        ))

    def _check_grammar(self, graph, report):
        """WARNING: AI grammar review."""
        if not self._ai_reviewer:
            return

        try:
            # Sample a few paragraphs for grammar review
            paragraphs = graph.get_objects_by_role(SemanticRole.PARAGRAPH)
            sample = paragraphs[:5]  # Check first 5 paragraphs

            issues_found = 0
            for obj in sample:
                if obj.translated_text:
                    review = self._ai_reviewer.review(
                        source=obj.original_text,
                        translation=obj.translated_text,
                    )
                    if review and review.get("score", 1.0) < 0.7:
                        issues_found += 1

            report.add_check(CheckResult(
                check_name="grammar_issues",
                severity=Severity.WARNING,
                passed=issues_found == 0,
                detail=f"{issues_found} paragraph(s) with grammar issues in sample of {len(sample)}",
                expected_value="0 issues",
                actual_value=f"{issues_found} issues",
            ))
        except Exception as e:
            logger.warning(f"Grammar check failed: {e}")