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
        self._ai = ai_provider
        self.threshold = threshold

    def batch_review(
        self,
        entries: list[tuple[int, str, str]],
        document_type: str = "",
        terminology: list[str] | None = None,
    ) -> dict[int, QualityReview]:
        """Review multiple translations in a single AI call.

        Each entry is (block_index, source_text, translation_text).
        Returns dict mapping block_index -> QualityReview.

        Falls back to per-item review if the batch AI call fails.
        """
        from prompts.quality import build_batch_quality_review_prompt

        results: dict[int, QualityReview] = {}
        uncritical: list[tuple[int, str, str]] = []

        for idx, source, translation in entries:
            if not translation.strip():
                results[idx] = QualityReview(
                    score=0.0,
                    issues=[QualityIssue(
                        severity="critical", category="missing_content",
                        description="Translation is empty",
                    )],
                    retry_required=True,
                    summary="Empty translation",
                )
                continue

            if source.strip() == translation.strip():
                results[idx] = QualityReview(
                    score=30.0,
                    issues=[QualityIssue(
                        severity="critical", category="untranslated",
                        description="Source and translation are identical",
                    )],
                    retry_required=True,
                    summary="Text was not translated",
                )
                continue

            pre_issues = self._pre_check(source, translation, terminology)
            if any(i.severity == "critical" for i in pre_issues):
                results[idx] = QualityReview(
                    score=30.0,
                    issues=pre_issues,
                    retry_required=True,
                    summary="; ".join(i.description for i in pre_issues[:3]),
                )
                continue

            uncritical.append((idx, source, translation))

        if not uncritical:
            return results

        system_prompt = self._build_system_prompt(document_type)
        user_prompt = build_batch_quality_review_prompt(uncritical, document_type)

        def _fallback_one(idx, source, translation):
            """Try per-item review; treat provider-exception soft-fails as hard fails."""
            try:
                r = self.review(source, translation, document_type, terminology)
            except Exception as fb_e:
                print(f"  [QualityReview] Fallback per-item review failed: {fb_e}")
                return QualityReview(
                    score=0.0, retry_required=True,
                    summary=f"Review failed: {fb_e}",
                )
            # Detect soft-fail: provider exception wrapped in score=100/passed
            if r.score == 100.0 and not r.retry_required and "unavailable" in r.summary.lower():
                print(f"  [QualityReview] Fallback per-item also unavailable, marking as failed")
                return QualityReview(
                    score=0.0, retry_required=True,
                    summary="Review unavailable at all levels",
                )
            return r

        try:
            batch_result = self._ai.analyze(system_prompt, user_prompt)
        except (RuntimeError, ConnectionError) as e:
            print(f"  [QualityReview] Batch review failed: {e}")
            print(f"  [QualityReview] Falling back to per-item review")
            for idx, source, translation in uncritical:
                results[idx] = _fallback_one(idx, source, translation)
            return results

        if not isinstance(batch_result, dict):
            print(f"  [QualityReview] Batch review returned non-dict (type={type(batch_result).__name__}), "
                  f"falling back to per-item review")
            for idx, source, translation in uncritical:
                results[idx] = _fallback_one(idx, source, translation)
            return results

        for idx, source, translation in uncritical:
            key = str(idx)
            entry = batch_result.get(key) or batch_result.get(idx)
            if entry and isinstance(entry, dict):
                # Validate score before parsing — if invalid, fall back to per-item
                try:
                    test_score = entry.get("score", 100.0)
                    float(test_score)
                except (ValueError, TypeError):
                    print(f"  [QualityReview] Batch entry {idx} has non-numeric score "
                          f"({test_score!r}), falling back to per-item review")
                    results[idx] = _fallback_one(idx, source, translation)
                    continue
                pre_issues = self._pre_check(source, translation, terminology)
                review = self._parse_response(entry, pre_issues, source, translation)
                # Match per-block behavior: critical pre-check overrides AI score
                # so both modes flag consistently (per-block skips AI entirely;
                # batch has already called AI but must not trust its score)
                if any(i.severity == "critical" for i in pre_issues):
                    review = QualityReview(
                        score=30.0, issues=pre_issues + review.issues,
                        retry_required=True,
                        summary=review.summary or "Quality check failed",
                    )
                results[idx] = review
            else:
                print(f"  [QualityReview] Batch missing entry {idx}, falling back to per-item")
                results[idx] = _fallback_one(idx, source, translation)

        return results

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

        # Validate result type before parsing — fail-closed, not fail-open
        if not isinstance(result, dict):
            print(f"  [QualityReview] CRITICAL: AI returned non-dict result "
                  f"(type={type(result).__name__}), marking review as failed")
            pre_check_issues.append(QualityIssue(
                severity="critical", category="review_failed",
                description=f"AI review provider returned {type(result).__name__} instead of dict",
            ))
            return QualityReview(
                score=0.0,
                issues=pre_check_issues,
                retry_required=True,
                summary="AI review failed — provider returned malformed data",
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

    @staticmethod
    def _normalize_source_numbers(source: str) -> set[str]:
        """Extract all numbers from source (digits, comma-format, spelled-out)."""
        import re

        numbers = set()

        # 1. Comma-formatted integers: 1,250 → "1250"
        for m in re.finditer(r'\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b', source):
            numbers.add(m.group(0).replace(',', ''))

        # 2. Plain digits and decimals (may overlap with #1 above)
        for m in re.finditer(r'\b\d+(?:\.\d+)?\b', source):
            numbers.add(m.group(0))

        # 3. Spelled-out English numbers — map to digits
        WORD_MAP = {
            'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
            'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
            'ten': '10', 'eleven': '11', 'twelve': '12', 'thirteen': '13',
            'fourteen': '14', 'fifteen': '15', 'sixteen': '16', 'seventeen': '17',
            'eighteen': '18', 'nineteen': '19', 'twenty': '20', 'thirty': '30',
            'forty': '40', 'fifty': '50', 'sixty': '60', 'seventy': '70',
            'eighty': '80', 'ninety': '90',
            'hundred': '100', 'thousand': '1000', 'million': '1000000', 'billion': '1000000000',
        }
        for word, digit in WORD_MAP.items():
            if word in source.lower().split():
                numbers.add(digit)

        return numbers

    @staticmethod
    def _extract_entities(text: str) -> set[str]:
        """Extract proper nouns (capitalized words not at sentence start)."""
        import re
        entities = set()
        # Match capitalized words that aren't sentence-initial
        # Pattern: preceded by lowercase/digit or inside quotes, then capital word
        for m in re.finditer(r'(?<=[a-z0-9,;:])\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text):
            entities.add(m.group(1).lower())
        return entities

    def _pre_check(self, source: str, translation: str,
                   terminology: list[str] | None = None) -> list[QualityIssue]:
        """Fast pre-check for obvious issues without AI call.

        Checks:
        - Length ratio (translation too short or too long)
        - Numbers preserved (digits + spoken-word forms, source-side only)
        - Proper entities preserved (capitalized names/places)
        - Untranslated segments (source language text in output)

        NOTE: Number comparison is source-side only. Cebuano spelled-out
        numbers (e.g. "tulo" for three) are not mapped, so digit→Cebuano-word
        translations are not flagged (avoids false positives). The AI review
        prompt is responsible for catching those.
        """
        import re
        issues: list[QualityIssue] = []

        # Cache for reuse below
        src_words = source.split()
        tgt_words = translation.split()
        src_word_count = len(src_words)
        tgt_word_count = len(tgt_words)

        # Length ratio check
        if src_word_count > 0 and tgt_word_count > 0:
            ratio = tgt_word_count / src_word_count
            if ratio < 0.5:
                issues.append(QualityIssue(
                    severity="critical",
                    category="missing_content",
                    description=f"Translation is too short ({tgt_word_count} vs {src_word_count} words, ratio={ratio:.2f})",
                ))
            elif ratio > 3.0:
                issues.append(QualityIssue(
                    severity="major",
                    category="hallucination",
                    description=f"Translation is too long ({tgt_word_count} vs {src_word_count} words, ratio={ratio:.2f})",
                ))

        # Number preservation check
        src_numbers = self._normalize_source_numbers(source)
        tgt_digits = set(re.findall(r'\b\d+(?:\.\d+)?\b', translation))
        # Also normalize comma-format in translation
        for m in re.finditer(r'\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b', translation):
            tgt_digits.add(m.group(0).replace(',', ''))

        # Flag source numbers that appear in translation with a DIFFERENT digit
        number_mismatches = []
        for sn in src_numbers:
            if sn in tgt_digits:
                continue
            # Check if a different digit exists in translation for the same quantity
            # e.g., source "3" → translation "8" (both digits)
            if not any(td == sn for td in tgt_digits) and tgt_digits:
                # Only flag if source was a digit (not spelled-out), to avoid
                # digit→Cebuano-word false positives
                if re.match(r'^\d+(?:\.\d+)?$', sn):
                    number_mismatches.append(sn)

        # Also flag DIGITS that exist in source but are missing in translation
        # (skipping spelled-out source numbers to avoid Cebuano-word false positives)
        src_digits = set(re.findall(r'\b\d+(?:\.\d+)?\b', source))
        missing_digits = src_digits - tgt_digits
        combined = set(number_mismatches) | set(d for d in missing_digits
                                                 if d not in number_mismatches)

        if combined and len(combined) <= 5:
            issues.append(QualityIssue(
                severity="critical",
                category="number_error",
                description=f"Number mismatch: source has {', '.join(sorted(combined))} "
                            f"but translation has {', '.join(sorted(tgt_digits)) or 'none'}",
                source_snippet=f"Source numbers: {src_numbers}",
            ))

        # Proper-entity preservation check
        src_entities = self._extract_entities(source)
        if src_entities:
            tgt_lower = translation.lower()
            missing_entities = {e for e in src_entities if e not in tgt_lower}
            if missing_entities and len(missing_entities) <= 3:
                issues.append(QualityIssue(
                    severity="major",
                    category="entity_error",
                    description=f"Proper names/places missing from translation: {', '.join(sorted(missing_entities))}",
                    source_snippet=f"Entities: {missing_entities}",
                ))

        # Clause/time/location segment-preservation check (Option B MVP)
        # Count structural segment markers in source and translation;
        # a significant deficit suggests omission (e.g., time modifier dropped).
        # Uses position-tracking with overlap dedup to avoid double-counting
        # the same word matched by multiple patterns.
        # Severity is "major" so this never triggers an early return or
        # forced retranslation on its own — only adds information for the
        # caller to consider alongside AI judgment.
        def _merge_segments(positions: set[tuple[int, int]]) -> int:
            """Count non-overlapping matches (longer match wins on overlap)."""
            if not positions:
                return 0
            sorted_pos = sorted(positions, key=lambda x: (x[0], -(x[1] - x[0])))
            merged = 0
            last_end = -1
            for s, e in sorted_pos:
                if s >= last_end:
                    merged += 1
                    last_end = e
            return merged

        _src_positions: set[tuple[int, int]] = set()
        _tgt_positions: set[tuple[int, int]] = set()

        for _pat in (
            r'\b(when|if|because|before|after|until|while|although|though|since|unless)\b',
            r'\b(and|but|or)\b',
            r'\b(morning|afternoon|evening|night|noon|midnight'
            r'|monday|tuesday|wednesday|thursday|friday|saturday|sunday'
            r'|january|february|march|april|may|june|july|august'
            r'|september|october|november|december'
            r'|market|hospital|school|house|city|town|airport'
            r'|beach|backyard|park|office|building|hotel|restaurant)\b',
        ):
            for m in re.finditer(_pat, source, re.IGNORECASE):
                _src_positions.add((m.start(), m.end()))
        for _pat in (
            r'\b(every|next|last)\s+(day|week|month|year'
            r'|morning|afternoon|evening|night|monday|tuesday|wednesday'
            r'|thursday|friday|saturday|sunday)\b',
        ):
            for m in re.finditer(_pat, source, re.IGNORECASE):
                _src_positions.add((m.start(), m.end()))

        for _pat in (
            r'\b(kung|kay|human|hangtod|samtang|bisan|gawas|sukad|kon)\b',
            r'\bwala\s+pa\b|\bdili\s+pa\b',
            r'\b(ug|apan|pero)\b',
            r'\b(buntag|hapon|gabii|udto|kaadlawon'
            r'|Lunes|Martes|Miyerkoles|Huwebes|Biyernes|Sabado|Dominggo'
            r'|Enero|Pebrero|Marso|Abril|Mayo|Hunyo|Hulyo|Agosto'
            r'|Septiyembre|Oktubre|Nobyembre|Disyembre'
            r'|merkado|ospital|eskwelahan|tunghaan|balay|siyudad|hospital'
            r'|lungsod|paliparan|airport|baybayon|bakuran|bakyard'
            r'|parke|opisina|building|hotel|restawran)\b',
        ):
            for m in re.finditer(_pat, translation, re.IGNORECASE):
                _tgt_positions.add((m.start(), m.end()))
        for _pat in (
            r'\b(kada|matag|sunod|miaging)\s+'
            r'(adlaw|semana|bulan|tuig'
            r'|buntag|hapon|gabii|udto'
            r'|Lunes|Martes|Miyerkoles|Huwebes|Biyernes|Sabado|Dominggo)\b',
        ):
            for m in re.finditer(_pat, translation, re.IGNORECASE):
                _tgt_positions.add((m.start(), m.end()))

        _src_seg = _merge_segments(_src_positions)
        _tgt_seg = _merge_segments(_tgt_positions)
        deficit = _src_seg - _tgt_seg
        if deficit >= 2:
            issues.append(QualityIssue(
                severity="major",
                category="missing_content",
                description=f"Translation may be missing content: "
                            f"{_src_seg} structural segments in source vs "
                            f"{_tgt_seg} in translation (deficit={deficit})",
                source_snippet=source[:100],
                translation_snippet=translation[:100],
            ))

        # Check for untranslated segments (if source language appears in output)
        if len(source) > 50:
            source_words_set = set(w.lower() for w in src_words)
            tgt_words_set = set(w.lower() for w in tgt_words)
            overlap = source_words_set & tgt_words_set
            if len(overlap) > len(source_words_set) * 0.7 and tgt_word_count / src_word_count > 0.8:
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
            "1. Missing content — split the source into clauses (by comma, "
            "semicolon, period). Verify each clause has an equivalent in the "
            "translation. Flag any source clause with no corresponding "
            "translation content.\n"
            "2. Hallucinations — is there content not present in the source?\n"
            "3. Terminology errors — are specialized terms translated incorrectly?\n"
            "4. Number, date, and entity errors — extract every number, date, "
            "measurement, and proper name from the source. Cross-check each one "
            "in the translation. Report any mismatch, missing item, or changed "
            "value.\n"
            "5. Untranslated text — is any source language text left in the output?\n"
            "6. Formatting issues — are lists, headers, or structure preserved?\n\n"
            "Return a JSON object with these fields:\n"
            "{\n"
            '  "score": 85.0,\n'
            '  "issues": [\n'
            '    {\n'
            '      "severity": "major",\n'
            '      "category": "missing_content",\n'
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
        try:
            score = float(result.get("score", 100.0))
            score = max(0.0, min(100.0, score))
        except (ValueError, TypeError):
            score = 0.0
            print(f"  [QualityReview] Non-numeric score in AI response, marking as failed")

        # Parse issues from AI
        ai_issues: list[QualityIssue] = []
        issues_raw = result.get("issues", [])
        if isinstance(issues_raw, list):
            for item in issues_raw:
                if isinstance(item, dict):
                    try:
                        ai_issues.append(QualityIssue(
                            severity=str(item.get("severity", "minor")),
                            category=str(item.get("category", "unknown")),
                            description=str(item.get("description", "")),
                        ))
                    except Exception:
                        pass  # skip malformed issues

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