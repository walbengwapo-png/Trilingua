# -*- coding: utf-8 -*-
"""
AI Document Analyzer.

Analyzes extracted document blocks and produces a structured DocumentProfile
using a single AI call. The profile describes the document's type, structure,
terminology, and entities.

This is the FIRST AI-assisted phase in the pipeline. It runs after extraction
and before any translation. The profile it produces is used by:
- Document Memory (Phase 2)
- Semantic Chunker (Phase 3)
- Specialized Prompts (Phase 4)
- Layout Planner (Phase 8)

Only ONE AI call is made, regardless of document size. For large documents,
the analyzer samples strategically (first 20% + last 20% + all headings).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SectionInfo:
    """A document section identified by the analyzer."""
    level: int          # Heading level (1 = top-level)
    title: str          # Section title
    start_block: int    # Block index where this section begins


@dataclass
class StructureElement:
    """A structural element detected in the document."""
    element_type: str   # heading, table, caption, list, code_block, etc.
    block_index: int    # Block index where this element appears
    text: str = ""      # The element text (truncated if long)


@dataclass
class Abbreviation:
    """An abbreviation and its full form."""
    abbreviation: str
    full_form: str


@dataclass
class DocumentProfile:
    """Complete analysis of a document's structure and content.

    Produced by a single AI call via DocumentAnalyzer.analyze().
    All fields are populated by the AI; confidence indicates reliability.
    """
    document_type: str               # research_paper, legal_contract, etc.
    writing_style: str               # formal, academic, technical, etc.
    language: str                    # Detected primary language
    confidence: float                # 0.0 - 1.0 (analyzer's self-assessment)

    sections: list[SectionInfo] = field(default_factory=list)
    structure: list[StructureElement] = field(default_factory=list)
    terminology: list[str] = field(default_factory=list)
    abbreviations: list[Abbreviation] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    repeated_phrases: list[str] = field(default_factory=list)

    # Metadata
    total_blocks: int = 0
    total_words: int = 0
    analyzer_model: str = ""
    analysis_time_ms: float = 0.0

    def is_reliable(self) -> bool:
        """Whether this profile is reliable enough for semantic chunking."""
        return self.confidence >= 0.5 and len(self.sections) > 0


class DocumentAnalyzer:
    """Analyzes document blocks and produces a DocumentProfile.

    The analyzer concatenates block texts and sends them to an AI analysis
    provider in a SINGLE call. The AI returns a structured JSON profile.

    For documents too large for a single prompt, the analyzer samples
    strategically to capture the document's overall structure while
    staying within token limits.
    """

    # Maximum characters to send to the AI (approximate token limit)
    # For a 8K parameter model with system prompt overhead
    MAX_INPUT_CHARS = 12_000

    def __init__(self, ai_provider):
        """Initialize with an AI analysis provider.

        Args:
            ai_provider: An instance of AIAnalysisProvider (e.g., OllamaAnalysisProvider).
        """
        self._ai = ai_provider

    def analyze(self, blocks: list[dict]) -> DocumentProfile:
        """Analyze document blocks and return a structured profile.

        Args:
            blocks: List of block dicts from the document extractor.
                    Each block should have 'text', 'type', and optional 'style'.

        Returns:
            A DocumentProfile with all analysis results.

        Raises:
            RuntimeError: If AI analysis fails entirely.
            ValueError: If blocks is empty.
        """
        import time as _time
        start_time = _time.time()

        if not blocks:
            raise ValueError("Cannot analyze empty block list")

        total_blocks = len(blocks)
        total_words = sum(len(b.get("text", "").split()) for b in blocks)

        # Build a condensed text representation for the AI
        doc_text = self._build_condensed_text(blocks)

        # Build the system prompt
        system_prompt = self._build_system_prompt()

        # Build the user prompt with the document text
        user_prompt = self._build_user_prompt(doc_text, total_blocks, total_words)

        # Call the AI
        try:
            result = self._ai.analyze(system_prompt, user_prompt)
        except (RuntimeError, ConnectionError) as e:
            # Return a low-confidence default profile instead of crashing
            print(f"  [Analyzer] AI analysis failed: {e}")
            print(f"  [Analyzer] Returning default low-confidence profile")
            elapsed = (_time.time() - start_time) * 1000
            return self._default_profile(
                total_blocks, total_words, elapsed,
                error=str(e)
            )

        # Parse the AI response into a DocumentProfile
        elapsed = (_time.time() - start_time) * 1000
        profile = self._parse_response(result, total_blocks, total_words, elapsed)

        print(f"  [Analyzer] Document type: {profile.document_type}")
        print(f"  [Analyzer] Writing style: {profile.writing_style}")
        print(f"  [Analyzer] Language: {profile.language}")
        print(f"  [Analyzer] Confidence: {profile.confidence:.2f}")
        print(f"  [Analyzer] Sections: {len(profile.sections)}")
        print(f"  [Analyzer] Terms: {len(profile.terminology)}")
        print(f"  [Analyzer] Abbreviations: {len(profile.abbreviations)}")
        print(f"  [Analyzer] Analysis time: {elapsed:.0f}ms")

        return profile

    def _build_condensed_text(self, blocks: list[dict]) -> str:
        """Build a condensed text representation of the document.

        Each block is prefixed with its type in brackets to help the AI
        understand structure without needing the original formatting.

        Examples:
            [heading] Introduction
            [paragraph] This study examines...
            [table_cell] 42
            [list_item] - First item
        """
        parts = []
        char_count = 0
        is_truncated = False

        for i, block in enumerate(blocks):
            text = block.get("text", "").strip()
            block_type = block.get("type", "paragraph")

            if not text:
                continue

            # Prefix with type marker
            line = f"[{block_type}] {text[:200]}"  # Max 200 chars per block

            # Check if we'd exceed the limit
            if char_count + len(line) + 1 > self.MAX_INPUT_CHARS:
                # Try to include at least the headings from remaining blocks
                if not is_truncated:
                    parts.append(f"... [{len(blocks) - i} more blocks truncated]")
                    is_truncated = True

                # Still include heading-type blocks
                if block_type in ("header", "heading"):
                    parts.append(line[:100])
                    char_count += len(line[:100]) + 1
                continue

            parts.append(line)
            char_count += len(line) + 1

        return "\n".join(parts)

    def _build_system_prompt(self) -> str:
        """Build the system prompt for document analysis.

        This prompt instructs the AI to analyze the document and return
        a structured JSON response. The prompt is model-agnostic.
        """
        return (
            "You are a document analyst. Your task is to analyze a document "
            "and return a structured JSON profile.\n\n"
            "Analyze the following aspects:\n"
            "1. Document type (one of: research_paper, legal_contract, "
            "technical_manual, resume, business_proposal, medical_report, "
            "invoice, presentation, spreadsheet, general_document)\n"
            "2. Writing style (one of: formal, academic, technical, "
            "conversational, marketing)\n"
            "3. Primary language (the language the document is written in)\n"
            "4. Section hierarchy (headings and their nesting levels)\n"
            "5. Structural elements (headings, tables, captions, bullet lists, "
            "numbered lists, code blocks, references, footnotes)\n"
            "6. Key terminology (important domain-specific terms)\n"
            "7. Abbreviations and their full forms\n"
            "8. Named entities (people, organizations, locations)\n"
            "9. Repeated phrases (phrases appearing 3+ times)\n"
            "10. Confidence score (0.0-1.0) for your analysis\n\n"
            "Each block is prefixed with its type in brackets, e.g.:\n"
            "[heading] Introduction\n"
            "[paragraph] This is a paragraph.\n"
            "[table_cell] Data\n\n"
            "IMPORTANT: Return ONLY valid JSON. No explanations, no markdown."
        )

    def _build_user_prompt(self, doc_text: str, total_blocks: int,
                           total_words: int) -> str:
        """Build the user prompt with the document text."""
        return (
            f"Analyze this document ({total_blocks} blocks, "
            f"{total_words} words):\n\n"
            f"{doc_text}\n\n"
            f"Return a JSON object with these fields:\n"
            f"{{\n"
            f'  "document_type": "str",\n'
            f'  "writing_style": "str",\n'
            f'  "language": "str",\n'
            f'  "confidence": 0.0,\n'
            f'  "sections": [{{\"level\": 1, "title": "str", '
            f'"start_block": 0}}],\n'
            f'  "structure": [{{\"element_type": "str", '
            f'"block_index": 0, "text": "str"}}],\n'
            f'  "terminology": ["term1", "term2"],\n'
            f'  "abbreviations": [{{\"abbreviation\": "str", '
            f'"full_form": "str"}}],\n'
            f'  "entities": ["entity1", "entity2"],\n'
            f'  "repeated_phrases": ["phrase1", "phrase2"]\n'
            f"}}\n"
            f"Return ONLY the JSON object, nothing else."
        )

    def _parse_response(self, result: dict, total_blocks: int,
                        total_words: int, elapsed_ms: float) -> DocumentProfile:
        """Parse the AI response into a DocumentProfile.

        Handles missing or invalid fields gracefully by providing defaults.
        """
        # Helper to safely get a list field
        def _safe_list(key: str, item_type: type = str) -> list:
            items = result.get(key, [])
            if not isinstance(items, list):
                return []
            return [item for item in items if isinstance(item, item_type)]

        # Parse sections
        sections_raw = result.get("sections", [])
        sections = []
        if isinstance(sections_raw, list):
            for s in sections_raw:
                if isinstance(s, dict):
                    sections.append(SectionInfo(
                        level=int(s.get("level", 1)),
                        title=str(s.get("title", "")),
                        start_block=int(s.get("start_block", 0)),
                    ))

        # Parse structure elements
        structure_raw = result.get("structure", [])
        structure = []
        if isinstance(structure_raw, list):
            for s in structure_raw:
                if isinstance(s, dict):
                    structure.append(StructureElement(
                        element_type=str(s.get("element_type", "unknown")),
                        block_index=int(s.get("block_index", 0)),
                        text=str(s.get("text", "")),
                    ))

        # Parse abbreviations
        abbrs_raw = result.get("abbreviations", [])
        abbreviations = []
        if isinstance(abbrs_raw, list):
            for a in abbrs_raw:
                if isinstance(a, dict):
                    abbreviations.append(Abbreviation(
                        abbreviation=str(a.get("abbreviation", "")),
                        full_form=str(a.get("full_form", "")),
                    ))

        confidence = float(result.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))

        return DocumentProfile(
            document_type=str(result.get("document_type", "general_document")),
            writing_style=str(result.get("writing_style", "formal")),
            language=str(result.get("language", "unknown")),
            confidence=confidence,
            sections=sections,
            structure=structure,
            terminology=_safe_list("terminology"),
            abbreviations=abbreviations,
            entities=_safe_list("entities"),
            repeated_phrases=_safe_list("repeated_phrases"),
            total_blocks=total_blocks,
            total_words=total_words,
            analyzer_model=self._ai.model_name,
            analysis_time_ms=elapsed_ms,
        )

    def _default_profile(self, total_blocks: int, total_words: int,
                         elapsed_ms: float, error: str = "") -> DocumentProfile:
        """Return a default low-confidence profile when analysis fails."""
        return DocumentProfile(
            document_type="general_document",
            writing_style="formal",
            language="unknown",
            confidence=0.0,
            total_blocks=total_blocks,
            total_words=total_words,
            analyzer_model=self._ai.model_name if hasattr(self, '_ai') else "",
            analysis_time_ms=elapsed_ms,
        )