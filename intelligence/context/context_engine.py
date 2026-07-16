# -*- coding: utf-8 -*-
"""
Context Engine — Central orchestrator for all contextual information
during translation. Every pipeline component queries the Context Engine
rather than managing its own state.

Manages:
- Translation Memory (exact + fuzzy)
- Glossary (user + document)
- Neighbor objects (previous, next, parent, children)
- Cross-references ("see Figure X")
- Role hierarchy (question groups)
- Language pair knowledge (expansion ratios)
"""

import hashlib
import logging
from typing import Optional

from intelligence.graph.document_graph import (
    DocumentObject,
    DocumentObjectGraph,
    SemanticRole,
)

logger = logging.getLogger(__name__)


class TMEntry:
    """A single Translation Memory entry."""

    def __init__(
        self,
        source_text: str,
        translated_text: str,
        source_lang: str = "",
        target_lang: str = "",
        role: str = "",
        confidence: float = 1.0,
        source: str = "document",
    ):
        self.source_text = source_text
        self.translated_text = translated_text
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.role = role
        self.confidence = confidence
        self.source = source
        self.source_hash = hashlib.sha256(source_text.lower().encode()).hexdigest()


class ContextEngine:
    """Central orchestrator for all contextual information during translation."""

    def __init__(self, graph: DocumentObjectGraph):
        self.graph = graph

        # Translation Memory layers
        self._tm_exact: dict[str, TMEntry] = {}  # hash → TMEntry
        self._tm_fuzzy: list[TMEntry] = []  # For fuzzy matching (BK-tree)

        # Glossary
        self._glossary: dict[str, str] = {}  # source_term → translated_term

        # Per-document TM (within-document reuse)
        self._document_tm: dict[str, str] = {}  # hash → translated_text

        # Issues log
        self.issues: list[dict] = []

        # Stats
        self.tm_hits: int = 0
        self.tm_misses: int = 0
        self.tm_fuzzy_hits: int = 0

    # ── Initialization ──────────────────────────────────────────────

    def initialize(self) -> None:
        """Initialize the context engine from the document graph."""
        # Extract repeated phrases as potential TM entries
        self._extract_repeated_phrases()
        logger.info(
            f"Context Engine initialized: "
            f"{len(self._tm_exact)} TM entries, "
            f"{len(self._glossary)} glossary terms"
        )

    def _extract_repeated_phrases(self) -> None:
        """Extract phrases appearing 3+ times as TM entries."""
        phrase_counts: dict[str, int] = {}
        phrase_example: dict[str, str] = {}

        for obj in self.graph.all_objects.values():
            text = obj.original_text.strip()
            if text and 5 <= len(text.split()) <= 50:
                normalized = text.lower()
                phrase_counts[normalized] = phrase_counts.get(normalized, 0) + 1
                if normalized not in phrase_example:
                    phrase_example[normalized] = text

        # Phrases appearing 3+ times are added as pending TM entries
        for normalized_text, count in phrase_counts.items():
            if count >= 3:
                entry = TMEntry(
                    source_text=phrase_example[normalized_text],
                    translated_text="",  # Will be filled on first translation
                    role="repeated_phrase",
                    confidence=0.9,
                    source="document",
                )
                self._tm_exact[entry.source_hash] = entry

    # ── Translation Memory ─────────────────────────────────────────

    def get_translation(
        self, text: str, source_lang: str = "", target_lang: str = ""
    ) -> Optional[str]:
        """Look up a translation in TM.

        Returns translated text if found, None otherwise.
        Checks: exact match → document TM → fuzzy match.
        """
        text = text.strip()
        if not text:
            return None

        # Layer 1: Exact match in persistent TM
        text_hash = hashlib.sha256(text.lower().encode()).hexdigest()
        if text_hash in self._tm_exact:
            entry = self._tm_exact[text_hash]
            if entry.translated_text:
                self.tm_hits += 1
                return entry.translated_text

        # Layer 2: Document-level TM
        if text_hash in self._document_tm:
            self.tm_hits += 1
            return self._document_tm[text_hash]

        # Layer 3: Fuzzy match
        fuzzy_result = self._fuzzy_match(text)
        if fuzzy_result:
            self.tm_fuzzy_hits += 1
            return fuzzy_result

        self.tm_misses += 1
        return None

    def record_translation(
        self,
        source_text: str,
        translated_text: str,
        role: str = "",
        source_lang: str = "",
        target_lang: str = "",
    ) -> None:
        """Record a translation in TM."""
        text = source_text.strip()
        if not text or not translated_text:
            return

        text_hash = hashlib.sha256(text.lower().encode()).hexdigest()

        # Update in-memory TM
        self._document_tm[text_hash] = translated_text

        # Update persistent TM if entry exists
        if text_hash in self._tm_exact:
            self._tm_exact[text_hash].translated_text = translated_text
            self._tm_exact[text_hash].role = role
        else:
            self._tm_exact[text_hash] = TMEntry(
                source_text=text,
                translated_text=translated_text,
                role=role,
                confidence=0.95,
                source="pipeline",
            )
            self._tm_fuzzy.append(self._tm_exact[text_hash])

    def _fuzzy_match(self, text: str, threshold: float = 0.85) -> Optional[str]:
        """Simple fuzzy matching using word overlap."""
        if not self._tm_fuzzy:
            return None

        text_lower = text.lower()
        text_words = set(text_lower.split())

        best_match = None
        best_similarity = threshold

        for entry in self._tm_fuzzy:
            if not entry.translated_text:
                continue

            entry_words = set(entry.source_text.lower().split())
            if not entry_words:
                continue

            intersection = text_words & entry_words
            union = text_words | entry_words
            similarity = len(intersection) / len(union) if union else 0

            if similarity >= best_similarity:
                best_similarity = similarity
                best_match = entry.translated_text

        return best_match

    # ── Glossary ────────────────────────────────────────────────────

    def add_glossary_term(self, source: str, target: str) -> None:
        """Add a glossary term."""
        self._glossary[source.lower()] = target

    def get_glossary_terms(self, text: str) -> list[tuple[str, str]]:
        """Get glossary terms matching the given text.

        Returns: [(source_term, translated_term), ...]
        """
        matches = []
        text_lower = text.lower()
        for source, target in self._glossary.items():
            if source in text_lower:
                matches.append((source, target))
        return matches

    def apply_glossary(self, text: str) -> str:
        """Apply glossary replacements to text."""
        result = text
        for source, target in self._glossary.items():
            # Case-insensitive replacement
            idx = result.lower().find(source)
            if idx >= 0:
                result = result[:idx] + target + result[idx + len(source):]
        return result

    # ── Neighbors ──────────────────────────────────────────────────

    def get_neighbors(
        self, object_id: str, distance: int = 1
    ) -> list[DocumentObject]:
        """Get neighboring objects in reading order."""
        return self.graph.get_neighbors(object_id, distance=distance)

    def get_group_context(self, object_id: str) -> Optional[list[DocumentObject]]:
        """Get all objects in the same semantic group as this object."""
        for group in self.graph.groups:
            if object_id in group.member_ids:
                return self.graph.get_group_objects(group.id)
        return None

    # ── Prompt Building ─────────────────────────────────────────────

    def build_augmented_prompt(self, obj: DocumentObject) -> str:
        """Build an augmented translation prompt with full context.

        Includes:
        - Role-specific instruction
        - Neighbor context if relevant
        - Glossary terms if matching
        - Group context if in a group
        - TM result if available
        """
        prompt_parts = []

        # Role-specific prefix
        role_name = obj.semantic_role.name.replace("_", " ").title()
        prompt_parts.append(f"[Role: {role_name}]")

        # Role-specific instructions
        instructions = self._get_role_instructions(obj.semantic_role)
        if instructions:
            prompt_parts.append(f"[Instructions: {instructions}]")

        # TM hint
        tm_result = self.get_translation(obj.original_text)
        if tm_result:
            prompt_parts.append(f"[TM: {tm_result}]")

        # Glossary terms
        glossary_terms = self.get_glossary_terms(obj.original_text)
        if glossary_terms:
            term_str = "; ".join(f"{s} → {t}" for s, t in glossary_terms)
            prompt_parts.append(f"[Glossary: {term_str}]")

        # Neighbor context (if relevant)
        neighbors = self.get_neighbors(obj.id, distance=2)
        if neighbors:
            neighbor_texts = [
                n.original_text[:80] for n in neighbors if n.id != obj.id
            ]
            if neighbor_texts:
                prompt_parts.append("[Context: " + " | ".join(neighbor_texts) + "]")

        # Group context
        group_objects = self.get_group_context(obj.id)
        if group_objects and len(group_objects) > 1:
            group_texts = [
                f"{g.semantic_role.name}: {g.original_text[:60]}"
                for g in group_objects
                if g.id != obj.id
            ]
            if group_texts:
                prompt_parts.append("[Group: " + " | ".join(group_texts) + "]")

        # The actual text
        prompt_parts.append(f"\n{obj.original_text}")

        return "\n".join(prompt_parts)

    def _get_role_instructions(self, role: SemanticRole) -> str:
        """Get translation instructions for a specific semantic role."""
        instructions = {
            SemanticRole.LEARNING_OBJECTIVE: (
                "Translate this learning objective. Keep future/goal-oriented tone. "
                "Preserve any numbered prefix."
            ),
            SemanticRole.INSTRUCTION: (
                "Translate this instruction. Use imperative mood. "
                "Keep bullet markers if present."
            ),
            SemanticRole.QUESTION_STEM: (
                "Translate this question. Preserve the question mark. "
                "Keep any numbered prefix (e.g., '1.'). "
                "Do NOT fill in answer blanks (______)."
            ),
            SemanticRole.MULTIPLE_CHOICE_OPTION: (
                "Translate only the text after the choice letter. "
                "Preserve the choice letter (A., B., C., D.) exactly. "
                "Keep the translation short and parallel to other options."
            ),
            SemanticRole.ANSWER_BLANK: (
                "Do NOT translate. Keep the blank (______) exactly as is."
            ),
            SemanticRole.ANSWER_KEY: (
                "Translate only descriptive text. "
                "Preserve all answer letters (A, B, C, D) and numberings exactly. "
                "This is critical — do not change any letters."
            ),
            SemanticRole.TABLE_HEADER: (
                "Translate this table header. Keep capitalization consistent. "
                "Preserve the column structure."
            ),
            SemanticRole.CAPTION: (
                "Translate this caption. Preserve 'Figure', 'Table', 'Fig.' prefixes. "
                "Keep the figure/table number (e.g., 'Figure 1')."
            ),
            SemanticRole.FOOTER_TEXT: (
                "Translate this footer. Keep it concise (max 50 tokens). "
                "Preserve page numbers and any special formatting."
            ),
            SemanticRole.HEADER_TEXT: (
                "Translate this header. Keep consistent with document style. "
                "Preserve any document title or section reference."
            ),
            SemanticRole.HYPERLINK_TEXT: (
                "Do NOT translate. Keep the URL exactly as is."
            ),
            SemanticRole.CITATION: (
                "Translate only descriptive parts. "
                "Preserve parentheses, author names, years, and page numbers exactly."
            ),
            SemanticRole.REFERENCE_ENTRY: (
                "Translate only the title. "
                "Preserve author names, years, journal names, and DOIs exactly."
            ),
            SemanticRole.PARAGRAPH: (
                "Translate this paragraph. Maintain natural flow. "
                "Preserve any formatting markers or special characters."
            ),
            SemanticRole.HEADING_1: (
                "Translate this heading. Keep it concise. "
                "Preserve any numbering. Match the heading level style."
            ),
            SemanticRole.HEADING_2: (
                "Translate this heading. Keep it concise. "
                "Preserve any numbering. Match the heading level style."
            ),
            SemanticRole.HEADING_3: (
                "Translate this heading. Keep it concise. "
                "Preserve any numbering. Match the heading level style."
            ),
        }
        return instructions.get(role, "")

    # ── Stats ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get usage statistics for this context engine instance."""
        return {
            "tm_hits": self.tm_hits,
            "tm_misses": self.tm_misses,
            "tm_fuzzy_hits": self.tm_fuzzy_hits,
            "tm_total_entries": len(self._tm_exact),
            "glossary_terms": len(self._glossary),
            "issues_count": len(self.issues),
        }

    def clear(self) -> None:
        """Clear all runtime data."""
        self._tm_exact.clear()
        self._tm_fuzzy.clear()
        self._glossary.clear()
        self._document_tm.clear()
        self.issues.clear()
        self.tm_hits = 0
        self.tm_misses = 0
        self.tm_fuzzy_hits = 0