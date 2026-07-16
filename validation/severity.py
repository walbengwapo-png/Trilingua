# -*- coding: utf-8 -*-
"""
Severity definitions and quality report model.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(Enum):
    """Severity levels for quality validation checks."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class CheckResult:
    """Result of a single validation check."""
    check_name: str
    severity: Severity
    passed: bool
    detail: str = ""
    object_id: Optional[str] = None
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "check_name": self.check_name,
            "severity": self.severity.value,
            "passed": self.passed,
            "detail": self.detail,
            "object_id": self.object_id,
            "expected": self.expected_value,
            "actual": self.actual_value,
        }


@dataclass
class QualityReport:
    """Complete quality report for a translated document."""
    overall_score: float  # 0.0 - 1.0
    passed: bool
    critical_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    checks: list[CheckResult] = field(default_factory=list)
    recommendation: str = ""

    def add_check(self, check: CheckResult) -> None:
        """Add a check result and update counts."""
        self.checks.append(check)
        if not check.passed:
            if check.severity == Severity.CRITICAL:
                self.critical_count += 1
            elif check.severity == Severity.ERROR:
                self.error_count += 1
            elif check.severity == Severity.WARNING:
                self.warning_count += 1
            elif check.severity == Severity.INFO:
                self.info_count += 1

        # Update overall
        self.passed = self.critical_count == 0
        passed_count = sum(1 for c in self.checks if c.passed)
        self.overall_score = passed_count / len(self.checks) if self.checks else 1.0

        # Determine recommendation
        if self.critical_count > 0:
            self.recommendation = (
                f"REJECT: {self.critical_count} critical issue(s) found. "
                f"Requires rework before acceptance."
            )
        elif self.error_count > 0:
            self.recommendation = (
                f"REVIEW: {self.error_count} error(s) found. "
                f"Manual review recommended before acceptance."
            )
        elif self.warning_count > 0:
            self.recommendation = (
                f"ACCEPT WITH REVIEW: {self.warning_count} warning(s) found. "
                f"Minor issues to review."
            )
        else:
            self.recommendation = "ACCEPT: All checks passed."

    def to_dict(self) -> dict:
        return {
            "overall_score": round(self.overall_score, 4),
            "passed": self.passed,
            "critical_count": self.critical_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "recommendation": self.recommendation,
            "checks": [c.to_dict() for c in self.checks],
        }