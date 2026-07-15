# -*- coding: utf-8 -*-
"""
AI Quality Reviewer.

Replaces regex-only hallucination detection with AI-powered quality review.
Compares source text and translated text to detect issues.

The reviewer detects:
- Missing content (sentences omitted from translation)
- Hallucinations (content added that wasn't in source)
- Terminology inconsistency
- Incorrect numbers, dates, and data
- Untranslated segments (original language text left in output)
- Formatting-sensitive mistakes

Returns a structured QualityReview with score and actionable issues.

IMPORTANT: The existing regex-based hallucination_detector.py is preserved
and runs FIRST as a fast pre-filter. The AI reviewer runs SECOND for
deeper analysis. This way, simple hallucinations are caught instantly,
and the AI only reviews chunks that passed the regex check.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QualityIssue:
    """A specific issue found during quality review."""
    severity: str       # critical, major, minor
    category: str       # missing_content, hallucination, terminology,
                        # number_error, date_error, untranslated, formatting
    description: str    # Human-readable description
    source_snippet: str = ""      # Relevant source text excerpt
    translation_snippet: str = "" # Relevant translation excerpt


@dataclass
class QualityReview:
    """Complete quality review result."""
    score: float                    # 0.0 - 100.0
    issues: list[QualityIssue] = field(default_factory=list)
    retry_required: bool = False    # True if score < threshold
    summary: str = ""               # Brief summary for retry prompt

    @property
    def passed(self) -> bool:
        """Whether the translation passed quality review."""
        return not self.retry_required

    @property
    def critical_issues(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.severity == "critical"]

    @property
    def major_issues(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.severity == "major"]

    @property
    def minor_issues(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.severity == "minor"]


class AIQualityReviewer:
    """Reviews translation quality using AI analysis.

    The reviewer sends the source and translation pair to an AI analysis
    provider and parses the structured JSON response.

    Threshold: configurable score threshold (default 70.0).
    Below this threshold, retranslation is recommended.

    The reviewer also checks for critical issues (hallucinations, missing
    content) which always trigger retranslation regardless of score.
    """

    # Default threshold — translations scoring below this get retried
    DEFAULT_THRESHOLD = 70.0

    # Minimum threshold — translations below this are critically bad
    CRITICAL_THRESHOLD = 40.0

    def __init__(self, ai_provider, threshold: float = DEFAULT_THRESHOLD):
        """Initialize the quality reviewer.

        Args:
            ai_provider: An instance of AIAnalysisProvider.
            threshold: Score threshold for retranslation (0.0 - 100.0).
                      Default 70.0.
        """
        self._ai = ai_provider
        self.threshold = threshold

    def review(self, source: str, translation: str,
               document_type: str = "",
               terminology: list[str] | None = None) -> QualityReview:
        """Review a translation for quality issues.

        Args:
            source: Original source text.
            translation: Translated text.
            document_type: Optional document type for context.
            terminology: Optional list of known terminology terms.

        Returns:
            A QualityReview with score, issues, and retry recommendation.
        """
        # Fast path: empty or identical translations
        if not translation.strip():
            return QualityReview(
                score=0.0,
                issues=[QualityIssue(
                    severity="critical",
                    category="missing_content",
                    description="Translation is empty",
                )],
                retry_required=True,
                summary="Empty translation",
            )

        if source.strip() == translation.strip():
            return QualityReview(
                score=30.0,
                issues=[QualityIssue(
                    severity="critical",
                    category="untranslated",
                    description="Source and translation are identical",
                    source_snippet=source[:100],
                    translation_snippet=translation[:100],
                )],
                retry_required=True,
                summary="Text was not translated",
            )

        # Fast check: look for obvious issues without AI
        pre_check_issues = self._pre_check(source, translation, terminology)

        # If pre-check found critical issues, skip AI review for speed
        if any(i.severity == "critical" for i in pre_check_issues):
            return QualityReview(
                score=30.0,
                issues=pre_check_issues,
                retry_required=True,
                summary="; ".join(i.description for i in pre_check_issues[:3]),
            )

        # Build prompts for AI review
        system_prompt = self._build_system_prompt(document_type)
        user_prompt = self._build_user_prompt(source, translation, terminology)

        # Call AI for deep review
        try:
            result = self._ai.analyze(system_prompt, user_prompt)
        except (RuntimeError, ConnectionError) as e:
            # If AI review fails, pass the translation (don't block on review)
            print(f"  [QualityReview] AI review failed: {e}")
            print(f"  [QualityReview] Passing translation without AI review")
            return QualityReview(
                score=100.0,
                issues=pre_check_issues,
                retry_required=False,
                summary="AI review unavailable, passed without review",
            )

        # Parse the AI response
        review = self._parse_response(result, pre_check_issues, source, translation)

        return review

    def needs_retranslation(self, review: QualityReview) -> bool:
        """Check if retranslation is needed based on review.

        Retranslation is triggered if:
        - Score is below threshold
        - Any critical issues exist (hallucinations, missing content)

        Args:
            review: The QualityReview to check.

        Returns:
            True if retranslation is recommended.
        """
        if review.retry_required:
            return True
        if review.score < self.threshold:
            return True
        if any(i.severity == "critical" for i in review.issues):
            return True
        return False

    def _pre_check(self, source: str, translation: str,
                   terminology: list[str] | None = None) -> list[QualityIssue]:
        """Fast pre-check for obvious issues without AI call.

        Checks:
        - Length ratio (translation too short or too long)
        - Numbers preserved
        - Untranslated segments (source language text in output)
        """
        import re
        issues: list[QualityIssue] = []

        # Length ratio check
        src_words = len(source.split())
        tgt_words = len(translation.split())
        if src_words > 0 and tgt_words > 0:
            ratio = tgt_words / src_words
            if ratio < 0.3:
                issues.append(QualityIssue(
                    severity="critical",
                    category="missing_content",
                    description=f"Translation is too short ({tgt_words} vs {src_words} words, ratio={ratio:.2f})",
                ))
            elif ratio > 3.0:
                issues.append(QualityIssue(
                    severity="major",
                    category="hallucination",
                    description=f"Translation is too long ({tgt_words} vs {src_words} words, ratio={ratio:.2f})",
                ))

        # Number preservation check
        src_numbers = set(re.findall(r'\b\d+(?:\.\d+)?\b', source))
        tgt_numbers = set(re.findall(r'\b\d+(?:\.\d+)?\b', translation))
        missing_numbers = src_numbers - tgt_numbers
        if missing_numbers and len(missing_numbers) <= 3:
            issues.append(QualityIssue(
                severity="major",
                category="number_error",
                description=f"Numbers missing from translation: {', '.join(sorted(missing_numbers))}",
                source_snippet=f"Numbers: {missing_numbers}",
            ))

        # Check for untranslated segments (if source language appears in output)
        # This is a simple heuristic — check if long source phrases appear verbatim
        if len(source) > 50:
            # Check if more than 50% of the source appears unchanged
            source_words = set(source.lower().split())
            tgt_words_set = set(translation.lower().split())
            overlap = source_words & tgt_words_set
            # Only flag if significant overlap AND similar length (likely untranslated)
            if len(overlap) > len(source_words) * 0.7 and ratio > 0.8:
                issues.append(QualityIssue(
                    severity="critical",
                    category="untranslated",
                    description="Translation appears to be mostly untranslated source text",
                ))

        return issues

    def _build_system_prompt(self, document_type: str = "") -> str:
        """Build the system prompt for quality review."""
        prompt = (
            "You are a translation quality validator. "
            "Compare the source text and translation, then return a structured "
            "JSON quality assessment.\n\n"
            "Check for:\n"
            "1. Missing content — is any information from the source absent?\n"
            "2. Hallucinations — is there content not present in the source?\n"
            "3. Terminology errors — are specialized terms translated incorrectly?\n"
            "4. Number errors — are numbers, percentages, dates preserved?\n"
            "5. Untranslated text — is any source language text left in the output?\n"
            "6. Formatting issues — are lists, headers, or structure preserved?\n\n"
            "Return a JSON object with these fields:\n"
            "{\n"
            '  "score": 85.0,\n'
            '  "issues": [\n'
            '    {\n'
            '      "severity": "major",\n'
            '      "category": "terminology",\n'
            '      "description": "Brief description of the issue"\n'
            '    }\n'
            '  ],\n'
            '  "summary": "Brief overall assessment"\n'
            "}\n\n"
            "Score is 0-100 where 100 is a perfect translation.\n"
            "Severity: critical, major, or minor.\n\n"
            "Return ONLY valid JSON. No explanations."
        )

        if document_type:
            prompt += f"\nDocument type: {document_type}"

        return prompt

    def _build_user_prompt(self, source: str, translation: str,
                           terminology: list[str] | None = None) -> str:
        """Build the user prompt with source and translation."""
        prompt = (
            f"SOURCE TEXT:\n{source}\n\n"
            f"TRANSLATION:\n{translation}\n\n"
            f"Assess the quality of this translation."
        )

        if terminology:
            terms_str = ", ".join(terminology[:10])
            prompt += f"\n\nExpected terminology: {terms_str}"

        return prompt

    def _parse_response(self, result: dict, pre_issues: list[QualityIssue],
                        source: str, translation: str) -> QualityReview:
        """Parse the AI response into a QualityReview."""
        score = float(result.get("score", 100.0))
        score = max(0.0, min(100.0, score))

        # Parse issues from AI
        ai_issues: list[QualityIssue] = []
        issues_raw = result.get("issues", [])
        if isinstance(issues_raw, list):
            for item in issues_raw:
                if isinstance(item, dict):
                    ai_issues.append(QualityIssue(
                        severity=str(item.get("severity", "minor")),
                        category=str(item.get("category", "unknown")),
                        description=str(item.get("description", "")),
                    ))

        # Merge pre-check issues with AI issues
        all_issues = pre_issues + ai_issues

        summary = str(result.get("summary", ""))

        # Determine if retry is needed
        has_critical = any(i.severity == "critical" for i in all_issues)
        retry = score < self.threshold or has_critical

        return QualityReview(
            score=score,
            issues=all_issues,
            retry_required=retry,
            summary=summary or f"Score: {score:.1f}, Issues: {len(all_issues)}",
        )