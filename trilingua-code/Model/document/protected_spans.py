# -*- coding: utf-8 -*-
"""
Protected Span detection and restoration.

Spans that carry stable identity -- URLs, emails, numbers+units,
placeholders and inline code -- must survive translation character-for-
character. Detection runs at the dict->unit boundary; restoration runs
after provider output. Restoration is conservative: it only rewrites a
token when the original span's stable fingerprint is actually found in
the translation (for numbers this tolerates digit reordering), and it
never touches surrounding prose.
"""

import re
from typing import List, Optional, Tuple

from dto.pipeline import ProtectedSpan

_URL_RE = re.compile(
    r"https?://[^\s\"'<>]+|\b(?:www\.)?[\w-]+(?:\.[\w-]+)*"
    r"\.(?:gov|com|org|net|edu|ph|info|io)(?![\w.-])(?:/[^\s\"'<>]*)?", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_NUMERIC_LITERAL = r"\d+(?:,\d{3})*(?:\.\d+)?"
_UNIT_NUMBER_RE = re.compile(r"\$\s?" + _NUMERIC_LITERAL + "|" + _NUMERIC_LITERAL
                             + r"\s?(?:%|km|kg|m|cm|mm|px|pt)(?![A-Za-z])")
_NUMBER_RE = re.compile(r"(?<![\w.])" + _NUMERIC_LITERAL + r"(?!\w|\.\d)")

_KINDS = ("url", "email", "placeholder", "inline_code", "unit_number", "number")


def detect_protected_spans(text: str) -> Tuple[ProtectedSpan, ...]:
    """Find non-translatable spans in ``text``, sorted and disjoint by start."""
    if not text:
        return ()
    matches: List[Tuple[int, int, str]] = []
    for pattern, kind in ((_URL_RE, "url"),
                          (_EMAIL_RE, "email"),
                          (_PLACEHOLDER_RE, "placeholder"),
                          (_INLINE_CODE_RE, "inline_code"),
                          (_UNIT_NUMBER_RE, "unit_number"),
                          (_NUMBER_RE, "number")):
        for match in pattern.finditer(text):
            end = match.end()
            if kind in {"url", "email"}:
                end -= len(match.group()) - len(match.group().rstrip(".,;:!?)]}"))
            matches.append((match.start(), end, kind))

    matches.sort(key=lambda m: (m[0], -(m[1] - m[0])))
    selected: List[ProtectedSpan] = []
    consumed = -1
    for start, end, kind in matches:
        if start < consumed:
            continue
        selected.append(ProtectedSpan(start=start, end=end, kind=kind))
        consumed = end
    return tuple(selected)


def missing_protected_spans(source: str, translation: str) -> list[str]:
    """Check each literal and its occurrence count inside the matching block."""
    from collections import Counter
    expected = Counter(source[s.start:s.end] for s in detect_protected_spans(source))
    missing = []
    for token, count in expected.items():
        pattern = r"(?<![\w])" + re.escape(token) + r"(?![\w])"
        if len(re.findall(pattern, translation)) < count:
            missing.append(token)
    return missing


def _digit_multiset(token: str) -> str:
    digits = [ch for ch in token if ch.isdigit()]
    return "".join(sorted(digits))


def _find_number_token(translation: str, original: str) -> Optional[str]:
    expected = _digit_multiset(original)
    if not expected:
        return None
    for token in re.findall(r"[A-Za-z0-9.\-$]+%?|\d[\d.,]*\s?[A-Za-z]{1,3}", translation):
        if _digit_multiset(token) == expected:
            return token
    return None


def _find_bracket_token(translation: str, original: str) -> Optional[str]:
    opening, closing = original[0], original[-1]
    for token in re.findall(r"\{[^{}]*\}|`[^`]*`", translation):
        if token[0] == opening and token[-1] == closing:
            if set(token) == set(original):
                return token
    return None


def _find_contact_token(translation: str, original: str) -> Optional[str]:
    """Match a URL/email whose alphanumeric multiset survives translation."""
    kept = set(ch for ch in original if ch.isalnum())
    if not kept:
        return None
    for token in re.findall(r"\S+", translation):
        token_alnum = set(ch for ch in token if ch.isalnum())
        if token_alnum == kept:
            return token
    return None


def restore_protected_spans(source: str, translation: str,
                            spans: Tuple[ProtectedSpan, ...]) -> str:
    """Re-insert any protected span that a provider dropped or mangled."""
    if not spans or not translation:
        return translation
    result = translation
    for span in sorted(spans, key=lambda s: s.start):
        original = source[span.start:span.end]
        if not original or original in result:
            continue
        replacement = None
        if span.kind == "number":
            replacement = _find_number_token(result, original)
            if replacement is None and _digit_multiset(original) and _digit_multiset(original) in _digit_multiset(result):
                continue
        elif span.kind in ("placeholder", "inline_code"):
            replacement = _find_bracket_token(result, original)
        elif span.kind in ("url", "email"):
            replacement = _find_contact_token(result, original)

        if replacement is not None:
            result = result.replace(replacement, original, 1)
    return result
