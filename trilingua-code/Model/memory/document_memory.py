# -*- coding: utf-8 -*-
"""
Document Memory.

Maintains persistent memory across the entire document translation process.
Replaces the tiny ContextBuffer (which only remembered 2 chunks) with
full-document awareness.

The memory stores:
- Document profile (type, style, language)
- Terminology and their chosen translations
- Abbreviations and their full forms
- Named entity translations
- Translation decisions (for consistency)
- Recently translated chunks (for immediate coherence)
- Writing style and document tone

Every translation request receives RELEVANT context from this memory,
not just the previous chunk.

Architecture:
- One DocumentMemory instance per document translation
- Created after Document Analyzer, passed through TranslationPipeline
- Updated incrementally as each chunk is translated
- Cleared after the document is complete
"""

from dataclasses import dataclass, field
from collections import deque
from typing import Any

from document.document_analyzer import DocumentProfile


@dataclass
class TranslationRecord:
    """A single translation decision recorded in memory."""
    source: str                     # Original source text (truncated)
    target: str                     # Translated text (truncated)
    block_index: int                # Which block this belongs to
    terms_used: list[str] = field(default_factory=list)  # Terms that appeared


class DocumentMemory:
    """Maintains context and terminology memory across a document translation.

    Usage:
        memory = DocumentMemory()
        memory.store_profile(profile)

        # Before translating a block:
        context = memory.get_context_for_block(block, block_index)
        request.context_hint = context

        # After translating:
        memory.record_translation(source, target, block_index)
        memory.extract_terms(source, target)
        memory.update_abbreviations(source)
    """

    def __init__(self, window_size: int = 5):
        """Initialize document memory.

        Args:
            window_size: Number of recent chunks to keep for immediate context.
        """
        # Document profile (from analyzer)
        self.profile: DocumentProfile | None = None

        # Terminology tracking: normalized_term -> chosen translation
        self.terminology: dict[str, str] = {}

        # Abbreviation map: abbr -> full_form
        self.abbreviations: dict[str, str] = {}

        # Entity translations: entity_name -> chosen translation
        self.entities: dict[str, str] = {}

        # Translation decisions: source phrase -> chosen translation
        self.translation_decisions: dict[str, str] = {}

        # Recent context (last N chunks)
        self.recent_context: deque[TranslationRecord] = deque(maxlen=window_size)

        # All translations (for full-document lookup)
        self.all_translations: list[TranslationRecord] = []

        # Tracking
        self.term_occurrences: dict[str, int] = {}  # term -> count
        self.translated_chunks: int = 0

    # ── Profile Management ─────────────────────────────────────────────────

    def store_profile(self, profile: DocumentProfile) -> None:
        """Store the document analysis profile.

        Also populates initial terminology and abbreviations from the profile.
        """
        self.profile = profile

        # Seed terminology from the profile
        for term in profile.terminology:
            normalized = self._normalize(term)
            self.term_occurrences[normalized] = self.term_occurrences.get(normalized, 0) + 1

        # Seed abbreviations from the profile
        for abbr in profile.abbreviations:
            self.abbreviations[abbr.abbreviation.upper()] = abbr.full_form

        # Seed entities
        for entity in profile.entities:
            normalized = self._normalize(entity)
            self.term_occurrences[normalized] = self.term_occurrences.get(normalized, 0) + 1

    def initialize_from_blocks(self, blocks: list[dict]) -> None:
        """Pre-populate memory from blocks if no profile is available.

        Scans blocks for potential abbreviations and repeated terms.
        This is a fallback when the Document Analyzer is not used.
        """
        import re

        # Scan for potential abbreviations (ALL CAPS words 2-5 chars)
        all_text = " ".join(b.get("text", "") for b in blocks)
        potential_abbrs = set(re.findall(r'\b[A-Z]{2,5}\b', all_text))
        for abbr in potential_abbrs:
            if abbr not in self.abbreviations:
                self.abbreviations[abbr] = ""  # Unknown for now

        # Count word frequencies to find repeated terms
        words = re.findall(r'\b[a-zA-Z]{4,}\b', all_text.lower())
        word_counts: dict[str, int] = {}
        for w in words:
            word_counts[w] = word_counts.get(w, 0) + 1

        # Store frequently occurring words as potential terminology
        for word, count in word_counts.items():
            if count >= 3:
                self.term_occurrences[word] = self.term_occurrences.get(word, 0) + count

    # ── Translation Recording ──────────────────────────────────────────────

    def record_translation(self, source: str, target: str,
                           block_index: int) -> None:
        """Record a translation decision.

        Args:
            source: Original source text.
            target: Translated text.
            block_index: Which block this translation belongs to.
        """
        # Find terms used in this source text
        terms_used = self._find_terms_in_text(source)

        record = TranslationRecord(
            source=source[:200],  # Truncate to save memory
            target=target[:200],
            block_index=block_index,
            terms_used=terms_used,
        )

        self.recent_context.append(record)
        self.all_translations.append(record)
        self.translated_chunks += 1

    def extract_terms(self, source: str, target: str) -> None:
        """Extract and record terminology from a chunk translation.

        This is a heuristic approach — it finds multi-word phrases that
        appear to be domain-specific by comparing source and target.

        Args:
            source: Original source text.
            target: Translated text.
        """
        import re

        # Look for capitalized multi-word phrases (likely named concepts)
        phrases = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', source)
        for phrase in phrases:
            normalized = self._normalize(phrase)
            if normalized not in self.terminology:
                self.term_occurrences[normalized] = self.term_occurrences.get(normalized, 0) + 1

    def update_abbreviations(self, source: str) -> None:
        """Try to expand abbreviations by scanning context.

        Looks for patterns like "Full Form (FF)" or "FF (Full Form)".
        """
        import re

        # Pattern: Full Form (ABBR)
        pattern1 = re.findall(r'([A-Z][a-z]+ [A-Z][a-z]+)\s*\(([A-Z]{2,5})\)', source)
        for full, abbr in pattern1:
            self.abbreviations[abbr.upper()] = full

        # Pattern: ABBR (Full Form)
        pattern2 = re.findall(r'([A-Z]{2,5})\s*\(([A-Z][a-z]+ [A-Z][a-z]+)\)', source)
        for abbr, full in pattern2:
            self.abbreviations[abbr.upper()] = full

    def record_entity_translation(self, entity: str, translation: str) -> None:
        """Record the chosen translation for a named entity."""
        normalized = self._normalize(entity)
        self.entities[normalized] = translation
        self.translation_decisions[normalized] = translation

    def record_term_translation(self, term: str, translation: str) -> None:
        """Record the chosen translation for a terminology term."""
        normalized = self._normalize(term)
        self.terminology[normalized] = translation
        self.translation_decisions[normalized] = translation

    # ── Context Building ──────────────────────────────────────────────────

    def get_context_for_block(self, block: dict,
                              block_index: int) -> str:
        """Build a context string for a specific block.

        The context includes:
        - Document type and writing style (once)
        - Abbreviations relevant to this block's text
        - Recent translations (last 3 chunks)
        - Terminology hints for terms appearing in this block

        Args:
            block: The block dict (with 'text' and 'type' keys).
            block_index: Index of this block in the document.

        Returns:
            A context string suitable for TranslationRequest.context_hint.
        """
        parts = []

        # 1. Document type (if available)
        if self.profile:
            parts.append(
                f"Document: {self.profile.document_type} "
                f"[{self.profile.writing_style}, {self.profile.language}]"
            )

        block_text = block.get("text", "")

        # 2. Abbreviations found in this block's text
        if self.abbreviations:
            relevant_abbrs = self._find_abbreviations_in_text(block_text)
            if relevant_abbrs:
                abbr_strs = [f"{a} = {f}" for a, f in relevant_abbrs]
                parts.append(f"Abbreviations: {'; '.join(abbr_strs)}")

        # 3. Terminology relevant to this block
        if self.terminology:
            relevant_terms = self._find_terms_in_text(block_text)
            if relevant_terms:
                term_strs = []
                for term in relevant_terms[:5]:  # Limit to 5
                    norm = self._normalize(term)
                    translation = self.terminology.get(norm)
                    if translation:
                        term_strs.append(f"{term} → {translation}")
                if term_strs:
                    parts.append(f"Terms: {'; '.join(term_strs)}")

        # 4. Recent context (last 3 chunks, but not from same block)
        if self.recent_context:
            recent = list(self.recent_context)[-3:]
            # Filter out entries from the same block
            recent = [r for r in recent if r.block_index != block_index]
            if recent:
                parts.append("Recent context:")
                for r in recent:
                    parts.append(f"  [{r.block_index}] {r.source[:80]}... → {r.target[:80]}...")

        return "\n".join(parts)

    def get_terminology_hint(self) -> str:
        """Build a terminology hint string for the translation prompt.

        Returns a compact string of known term-to-translation mappings.
        Empty string if no terminology has been recorded.
        """
        if not self.terminology:
            return ""

        terms = list(self.terminology.items())[:10]  # Limit to 10
        hints = [f"{source} = {target}" for source, target in terms]
        return "Terminology: " + "; ".join(hints)

    def resolve_abbreviation(self, abbreviation: str) -> str | None:
        """Look up an abbreviation's full form.

        Args:
            abbreviation: The abbreviation to look up.

        Returns:
            The full form if known, None otherwise.
        """
        return self.abbreviations.get(abbreviation.upper())

    # ── Lookup ────────────────────────────────────────────────────────────

    def get_translation_for(self, source: str) -> str | None:
        """Get a previously recorded translation for a source text.

        Uses exact matching on the first 100 characters.

        Args:
            source: Source text to look up.

        Returns:
            Previously recorded translation, or None if not found.
        """
        source_prefix = source[:100]
        for record in reversed(self.all_translations):
            if record.source.startswith(source_prefix):
                return record.target
        return None

    def has_term(self, term: str) -> bool:
        """Check if a term is known to the memory."""
        normalized = self._normalize(term)
        return normalized in self.terminology

    def get_entity_translation(self, entity: str) -> str | None:
        """Get the chosen translation for a named entity."""
        normalized = self._normalize(entity)
        return self.entities.get(normalized)

    # ── Stats ─────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return memory statistics for logging."""
        return {
            "translated_chunks": self.translated_chunks,
            "terminology_entries": len(self.terminology),
            "abbreviations": len(self.abbreviations),
            "entities": len(self.entities),
            "translation_decisions": len(self.translation_decisions),
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all memory. Called at the end of a document translation."""
        self.profile = None
        self.terminology.clear()
        self.abbreviations.clear()
        self.entities.clear()
        self.translation_decisions.clear()
        self.recent_context.clear()
        self.all_translations.clear()
        self.term_occurrences.clear()
        self.translated_chunks = 0

    # ── Internal Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize a term for dictionary lookup."""
        return text.lower().strip()

    def _find_terms_in_text(self, text: str) -> list[str]:
        """Find known terminology terms that appear in a text."""
        text_lower = text.lower()
        found = []
        for term in self.terminology:
            if term.lower() in text_lower:
                found.append(term)
        # Sort by length (longest match first) for best specificity
        found.sort(key=len, reverse=True)
        return found[:10]

    def _find_abbreviations_in_text(self, text: str) -> list[tuple[str, str]]:
        """Find abbreviations from memory that appear in a text."""
        import re
        found = []
        for abbr, full in self.abbreviations.items():
            if not full:  # Skip unresolved abbreviations
                continue
            if re.search(r'\b' + re.escape(abbr) + r'\b', text):
                found.append((abbr, full))
        return found[:5]