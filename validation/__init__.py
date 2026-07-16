# -*- coding: utf-8 -*-
"""
Quality Validation Engine — severity-based QA for translated documents.
"""

from validation.engine import ValidationEngine
from validation.severity import Severity, CheckResult, QualityReport
from validation.checks.check_registry import CHECK_REGISTRY

__all__ = [
    "ValidationEngine",
    "Severity",
    "CheckResult",
    "QualityReport",
    "CHECK_REGISTRY",
]