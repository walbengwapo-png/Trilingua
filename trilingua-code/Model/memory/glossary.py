# -*- coding: utf-8 -*-
"""
Glossary management.

Provides term substitution for post-translation processing.
Extracted from document_translator_v3.py Glossary_Store.
"""

import re


class GlossaryStore:
    """Holds source→target term pairs and applies post-translation substitution."""

    def __init__(self, pairs: list | None = None):
        if pairs is None:
            pairs = []
        if len(pairs) > 1000:
            raise ValueError(f"GlossaryStore: too many term pairs ({len(pairs)}); maximum is 1000.")

        self._terms: list[tuple[str, str]] = []
        seen: dict[str, str] = {}

        for source, target in pairs:
            key = source.lower()
            if key in seen:
                raise ValueError(
                    f"GlossaryStore: duplicate source term '{source}' "
                    f"(already registered as '{seen[key]}')."
                )
            seen[key] = source
            self._terms.append((source, target))

        if self._terms:
            sorted_terms = sorted(self._terms, key=lambda p: len(p[0]), reverse=True)
            pattern = "|".join(
                r"\b" + re.escape(src) + r"\b" for src, _ in sorted_terms
            )
            self._regex = re.compile(pattern, re.IGNORECASE)
            self._lookup = {src.lower(): tgt for src, tgt in sorted_terms}
        else:
            self._regex = None
            self._lookup = {}

    def apply(self, text: str) -> str:
        if self._regex is None:
            return text

        def _replace(match: re.Match) -> str:
            original_token = match.group(0)
            target_term = self._lookup[original_token.lower()]
            return self._match_case(original_token, target_term)

        return self._regex.sub(_replace, text)

    @staticmethod
    def _match_case(original_token: str, target_term: str) -> str:
        if original_token.isupper():
            return target_term.upper()
        if original_token.istitle():
            return target_term.title()
        if original_token.islower():
            return target_term.lower()
        return target_term