# -*- coding: utf-8 -*-
"""
Base exception classes for Trilingua document localization platform.
Hierarchy: TrilinguaException → category-specific subclasses.
"""

from typing import Optional, Any


class TrilinguaException(Exception):
    """Base exception for all Trilingua errors."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "system",
        severity: str = "ERROR",
        can_retry: bool = False,
        retry_count: int = 0,
        context: Optional[dict] = None,
    ):
        self.message = message
        self.category = category
        self.severity = severity
        self.can_retry = can_retry
        self.retry_count = retry_count
        self.context = context or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "error": self.message,
            "category": self.category,
            "severity": self.severity,
            "can_retry": self.can_retry,
            "context": self.context,
        }


class InputError(TrilinguaException):
    """File not found, unsupported format, empty document, password-protected."""

    def __init__(self, message: str, **kwargs):
        super().__init__(message, category="input", severity="ERROR", **kwargs)


class ParseError(TrilinguaException):
    """Malformed XML, corrupted PDF stream, missing table structure."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message, category="parse", severity="WARNING", can_retry=False, **kwargs
        )


class AnalysisError(TrilinguaException):
    """LLM timeout during analysis, semantic classifier failure, low confidence."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message, category="analysis", severity="WARNING", can_retry=True, **kwargs
        )


class TranslationError(TrilinguaException):
    """Provider unavailable, LLM returns empty or invalid format."""

    def __init__(self, message: str, can_retry: bool = True, **kwargs):
        super().__init__(
            message,
            category="translation",
            severity="ERROR",
            can_retry=can_retry,
            **kwargs,
        )


class ReconstructionError(TrilinguaException):
    """Text overflow unresolvable, file write permission, image missing."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category="reconstruction",
            severity="WARNING",
            can_retry=False,
            **kwargs,
        )


class ValidationError(TrilinguaException):
    """CRITICAL check failed: answer key corrupted, images lost, page count mismatch."""

    def __init__(self, message: str, severity: str = "CRITICAL", **kwargs):
        super().__init__(
            message,
            category="validation",
            severity=severity,
            can_retry=False,
            **kwargs,
        )


class ConfigurationError(TrilinguaException):
    """Missing API key, invalid provider config, bad environment."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message, category="configuration", severity="ERROR", can_retry=False, **kwargs
        )


class ProviderError(TrilinguaException):
    """All providers unavailable, rate limited, auth failure."""

    def __init__(self, message: str, can_retry: bool = True, **kwargs):
        super().__init__(
            message,
            category="provider",
            severity="ERROR",
            can_retry=can_retry,
            **kwargs,
        )


class ContextEngineError(TrilinguaException):
    """TM unavailable, glossary not found, neighbor index corrupt."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category="context_engine",
            severity="WARNING",
            can_retry=True,
            **kwargs,
        )


class CheckpointError(TrilinguaException):
    """Checkpoint save/restore failure, corrupt checkpoint data."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category="checkpoint",
            severity="ERROR",
            can_retry=True,
            **kwargs,
        )