# -*- coding: utf-8 -*-
"""
Regression tests for DocumentContext.record_block_quality().

Verifies the per-block AI quality result is stored as a plain-dict snapshot,
which is required so it can be serialized into the regeneration sidecar and
persisted by Laravel as translation_blocks.quality_issues.

Regression context: record_block_quality() used ``getattr(i, "severity",
i.get("severity"))``; Python evaluates the default argument eagerly, so it
crashed with ``'QualityIssue' object has no attribute 'get'`` whenever the
reviewer returned QualityIssue dataclasses (any real document with a flagged
block). See also the full document translation path in
pipeline/translation_pipeline.py:682,891.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from pipeline.document_context import DocumentContext
from validators.ai_quality_reviewer import QualityIssue


def test_record_block_quality_accepts_dataclass_issues():
    ctx = DocumentContext()
    ctx.record_block_quality(
        0,
        88.5,
        [
            QualityIssue(
                severity="major",
                category="hallucination",
                description="Added content not in source",
                source_snippet="src",
                translation_snippet="tgt",
            )
        ],
    )
    assert ctx.block_quality[0]["score"] == 88.5
    assert ctx.block_quality[0]["issues"] == [
        {
            "severity": "major",
            "category": "hallucination",
            "description": "Added content not in source",
            "source_snippet": "src",
            "translation_snippet": "tgt",
        }
    ]


def test_record_block_quality_accepts_dataclass_without_optional_snippets():
    """QualityIssue defaults source_snippet/translation_snippet to ''."""
    ctx = DocumentContext()
    ctx.record_block_quality(1, 40.0, [QualityIssue("critical", "untranslated", "Untranslated")])
    assert ctx.block_quality[1]["issues"] == [
        {
            "severity": "critical",
            "category": "untranslated",
            "description": "Untranslated",
            "source_snippet": "",
            "translation_snippet": "",
        }
    ]


def test_record_block_quality_passes_through_dict_issues():
    """Backward-compat: dict inputs are normalized with .get, kept as dicts."""
    ctx = DocumentContext()
    ctx.record_block_quality(
        2,
        72.0,
        [{"severity": "minor", "category": "formatting", "description": "Spacing"}],
    )
    assert ctx.block_quality[2]["issues"] == [
        {
            "severity": "minor",
            "category": "formatting",
            "description": "Spacing",
            "source_snippet": "",
            "translation_snippet": "",
        }
    ]


def test_record_block_quality_handles_empty_issues():
    ctx = DocumentContext()
    ctx.record_block_quality(3, 100.0, [])
    assert ctx.block_quality[3] == {"score": 100.0, "issues": []}
    ctx.record_block_quality(4, 100.0, None)
    assert ctx.block_quality[4]["issues"] == []


def test_record_block_quality_preserves_older_blocks():
    """Recording a later block must not clobber earlier recordings."""
    ctx = DocumentContext()
    ctx.record_block_quality(0, 90.0, [QualityIssue("minor", "terminology", "Word")])
    ctx.record_block_quality(1, 50.0, [])
    assert ctx.block_quality[0]["score"] == 90.0
    assert ctx.block_quality[1]["score"] == 50.0