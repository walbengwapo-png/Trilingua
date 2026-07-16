# -*- coding: utf-8 -*-
"""
Check Registry — defines all quality validation checks with severity levels.
"""

from typing import Any

from validation.severity import Severity


CHECK_REGISTRY: list[dict[str, Any]] = [
    {
        "name": "image_count_mismatch",
        "severity": Severity.CRITICAL,
        "description": "Translated image count differs from original",
        "pipeline_response": "Halt translation",
    },
    {
        "name": "table_count_mismatch",
        "severity": Severity.CRITICAL,
        "description": "Translated table count differs from original",
        "pipeline_response": "Halt translation",
    },
    {
        "name": "page_count_changed",
        "severity": Severity.CRITICAL,
        "description": "Page count differs from original",
        "pipeline_response": "Halt translation",
    },
    {
        "name": "object_count_mismatch",
        "severity": Severity.CRITICAL,
        "description": "Total objects differ significantly from original",
        "pipeline_response": "Halt translation",
    },
    {
        "name": "answer_key_corruption",
        "severity": Severity.CRITICAL,
        "description": "Answer letters changed or removed in answer keys",
        "pipeline_response": "Halt translation",
    },
    {
        "name": "blank_filled",
        "severity": Severity.ERROR,
        "description": "Answer blank has content when it should be empty",
        "pipeline_response": "Retranslate with stronger constraint",
    },
    {
        "name": "untranslated_text",
        "severity": Severity.ERROR,
        "description": "Source text equals target text (untranslated)",
        "pipeline_response": "Retranslate affected blocks",
    },
    {
        "name": "header_footer_missing",
        "severity": Severity.ERROR,
        "description": "Headers/footers not found in output",
        "pipeline_response": "Retranslate",
    },
    {
        "name": "hyperlink_lost",
        "severity": Severity.WARNING,
        "description": "Hyperlink text not linked in output",
        "pipeline_response": "Log for review",
    },
    {
        "name": "numbering_broken",
        "severity": Severity.WARNING,
        "description": "Numbering format inconsistent between original and translation",
        "pipeline_response": "Log for review",
    },
    {
        "name": "terminology_inconsistency",
        "severity": Severity.WARNING,
        "description": "Glossary term translated differently in different locations",
        "pipeline_response": "Log for review",
    },
    {
        "name": "grammar_issues",
        "severity": Severity.WARNING,
        "description": "AI reviewer grammar score below threshold (0.7)",
        "pipeline_response": "Log for review",
    },
    {
        "name": "blank_length_changed",
        "severity": Severity.INFO,
        "description": "Answer blank underscore count changed",
        "pipeline_response": "Log only",
    },
    {
        "name": "font_size_changed",
        "severity": Severity.INFO,
        "description": "Font size differs by 2pt or less",
        "pipeline_response": "Log only",
    },
    {
        "name": "font_family_changed",
        "severity": Severity.INFO,
        "description": "Font family changed",
        "pipeline_response": "Log only",
    },
]


class CheckRegistry:
    """Registry for quality checks with lookup utilities."""

    @staticmethod
    def get_check(name: str) -> dict:
        """Get check definition by name."""
        for check in CHECK_REGISTRY:
            if check["name"] == name:
                return check
        return {"name": name, "severity": Severity.INFO, "description": "", "pipeline_response": ""}

    @staticmethod
    def get_checks_by_severity(severity: Severity) -> list[dict]:
        """Get all checks with a specific severity."""
        return [c for c in CHECK_REGISTRY if c["severity"] == severity]

    @staticmethod
    def get_critical_checks() -> list[dict]:
        """Get all CRITICAL checks."""
        return CheckRegistry.get_checks_by_severity(Severity.CRITICAL)

    @staticmethod
    def get_all_checks() -> list[dict]:
        """Get all registered checks."""
        return CHECK_REGISTRY


check_registry = CheckRegistry()