# -*- coding: utf-8 -*-
"""
Role Registry — defines all semantic roles and their detection patterns.
Central source of truth for the semantic role taxonomy.
"""

import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

from intelligence.graph.document_graph import SemanticRole


@dataclass
class RolePattern:
    """A detection pattern for a semantic role."""
    role: SemanticRole
    priority: int  # Higher = matched first
    patterns: list[str] = field(default_factory=list)  # Compiled regex patterns
    heuristic_fn: Optional[str] = None  # Name of heuristic function to call
    min_confidence: float = 0.85  # Minimum confidence to accept heuristic match
    requires_llm_fallback: bool = True  # If heuristic fails, try LLM


ROLE_PATTERNS: list[RolePattern] = [
    # ── Highest priority: Exact matches ──────────────────────────
    RolePattern(
        role=SemanticRole.ANSWER_BLANK,
        priority=100,
        patterns=[
            r"^_{2,}$",  # 2+ underscores
            r"^_{2,}\s*_{2,}$",  # Multiple blank groups
            r"^\s*_{6,}\s*$",  # 6+ underscores with optional spaces
        ],
        heuristic_fn="is_answer_blank",
        min_confidence=0.95,
        requires_llm_fallback=False,
    ),
    RolePattern(
        role=SemanticRole.ANSWER_KEY,
        priority=90,
        patterns=[
            r"^\d+\s*[\.\)][\s]*[A-D][\.\)]?",  # "1. A" or "1) A"
            r"^\d+[\.\)]\s*[A-D]",  # "1. A"
            r"^[A-D][\.\)]\s*\w+",  # "A. text" or "A) text"
        ],
        heuristic_fn="is_answer_key",
        min_confidence=0.90,
        requires_llm_fallback=False,
    ),
    RolePattern(
        role=SemanticRole.MULTIPLE_CHOICE_OPTION,
        priority=85,
        patterns=[
            r"^[A-D][\.\)]\s+\w",  # "A. Option" or "A) Option"
            r"^[a-d][\.\)]\s+\w",  # "a. option"
        ],
        heuristic_fn="is_mc_option",
        min_confidence=0.90,
        requires_llm_fallback=False,
    ),

    # ── High priority: Well-known educational phrases ────────────
    RolePattern(
        role=SemanticRole.LEARNING_OBJECTIVE,
        priority=80,
        patterns=[
            r"^what i need to know",
            r"^learning objectives?",
            r"^objectives?",
            r"^most essential learning",
            r"^after going through this",
            r"^at the end of this",
        ],
        min_confidence=0.80,
    ),
    RolePattern(
        role=SemanticRole.INSTRUCTION,
        priority=75,
        patterns=[
            r"^directions?:",
            r"^instructions?:",
            r"^read each",
            r"^choose the letter",
            r"^write your answer",
            r"^fill in the blank",
            r"^match column",
        ],
        min_confidence=0.80,
    ),
    RolePattern(
        role=SemanticRole.QUESTION_STEM,
        priority=70,
        patterns=[
            r"^\d+[\.\)]\s+(what|which|who|where|when|why|how)",
            r"^\d+[\.\)]\s+[A-Z][a-z]+.*\?$",  # Numbered question ending with ?
            r"^[A-Z][a-z]+.*\?$",  # Any sentence ending with ?
        ],
        heuristic_fn="is_question",
        min_confidence=0.75,
    ),

    # ── Medium priority: Structural ──────────────────────────────
    RolePattern(
        role=SemanticRole.HEADING_1,
        priority=60,
        patterns=[
            r"^module\s+\d+",
            r"^lesson\s+\d+",
            r"^quarter\s+\d+",
            r"^chapter\s+\d+",
        ],
        heuristic_fn="is_heading_1",
        min_confidence=0.80,
    ),
    RolePattern(
        role=SemanticRole.HEADING_2,
        priority=55,
        patterns=[
            r"^what['']?s?\s+(in|new|more)",
            r"^what i can do",
            r"^what i have learned",
            r"^assessment",
            r"^additional activities",
        ],
        min_confidence=0.80,
    ),
    RolePattern(
        role=SemanticRole.CAPTION,
        priority=50,
        patterns=[
            r"^figure\s+\d+",
            r"^table\s+\d+",
            r"^fig\.?\s+\d+",
            r"^image\s+\d+",
        ],
        min_confidence=0.85,
    ),
    RolePattern(
        role=SemanticRole.GLOSSARY_TERM,
        priority=45,
        patterns=[
            r"^\w+\s+[-–]+\s+\w",  # "term - definition"
            r"^\w+\s+[-–]+\s+[A-Z]",  # "Term – Definition"
        ],
        min_confidence=0.75,
    ),
    RolePattern(
        role=SemanticRole.REFERENCE_ENTRY,
        priority=40,
        patterns=[
            r"^references?:?$",
            r"^bibliography:?$",
            r"^\w+\.?\s*\(\d{4}\)",  # Author (year)
        ],
        min_confidence=0.80,
    ),
    RolePattern(
        role=SemanticRole.HYPERLINK_TEXT,
        priority=35,
        patterns=[
            r"^https?://",
            r"^www\.",
            r"^http://",
        ],
        min_confidence=0.95,
        requires_llm_fallback=False,
    ),

    # ── Lower priority: Generic ──────────────────────────────────
    RolePattern(
        role=SemanticRole.FIGURE_REFERENCE,
        priority=30,
        patterns=[
            r"see\s+(figure|table|fig\.?)\s+\d+",
            r"as shown in\s+(figure|table)",
            r"refer to\s+(figure|table)",
        ],
        min_confidence=0.75,
    ),
    RolePattern(
        role=SemanticRole.CITATION,
        priority=25,
        patterns=[
            r"\(\w+[,\s]+\d{4}\)",  # (Author, year)
            r"\(\w+ et al\.,?\s*\d{4}\)",  # (Author et al., year)
            r"\[\d+\]",  # [1], [2,3]
        ],
        min_confidence=0.80,
    ),
]


class RoleRegistry:
    """Registry for semantic role patterns and lookup utilities."""

    @staticmethod
    def get_patterns_for_role(role: SemanticRole) -> list[RolePattern]:
        """Get all patterns matching a specific role."""
        return [p for p in ROLE_PATTERNS if p.role == role]

    @staticmethod
    def get_patterns_by_priority() -> list[RolePattern]:
        """Get all patterns sorted by priority (highest first)."""
        return sorted(ROLE_PATTERNS, key=lambda p: -p.priority)

    @staticmethod
    def get_educational_roles() -> list[SemanticRole]:
        """Get all education-specific semantic roles."""
        return [
            SemanticRole.LEARNING_OBJECTIVE,
            SemanticRole.INSTRUCTION,
            SemanticRole.QUESTION_STEM,
            SemanticRole.MULTIPLE_CHOICE_OPTION,
            SemanticRole.ANSWER_BLANK,
            SemanticRole.ANSWER_KEY,
            SemanticRole.WORKSHEET_TITLE,
        ]

    @staticmethod
    def get_translatable_roles() -> list[SemanticRole]:
        """Get roles that should be translated (not skipped)."""
        return [r for r in SemanticRole if r not in (
            SemanticRole.ANSWER_BLANK,
            SemanticRole.HYPERLINK_TEXT,
        )]

    @staticmethod
    def get_role_display_name(role: SemanticRole) -> str:
        """Get a human-readable display name for a role."""
        names = {
            SemanticRole.LEARNING_OBJECTIVE: "Learning Objective",
            SemanticRole.INSTRUCTION: "Instruction",
            SemanticRole.QUESTION_STEM: "Question",
            SemanticRole.MULTIPLE_CHOICE_OPTION: "Multiple Choice Option",
            SemanticRole.ANSWER_BLANK: "Answer Blank",
            SemanticRole.ANSWER_KEY: "Answer Key",
            SemanticRole.HEADING_1: "Heading 1",
            SemanticRole.HEADING_2: "Heading 2",
            SemanticRole.HEADING_3: "Heading 3",
            SemanticRole.PARAGRAPH: "Paragraph",
            SemanticRole.CAPTION: "Caption",
            SemanticRole.TABLE_HEADER: "Table Header",
            SemanticRole.TABLE_CELL: "Table Cell",
            SemanticRole.FOOTER_TEXT: "Footer",
            SemanticRole.HEADER_TEXT: "Header",
            SemanticRole.FIGURE_REFERENCE: "Figure Reference",
            SemanticRole.CITATION: "Citation",
            SemanticRole.HYPERLINK_TEXT: "Hyperlink",
            SemanticRole.GLOSSARY_TERM: "Glossary Term",
            SemanticRole.REFERENCE_ENTRY: "Reference",
        }
        return names.get(role, role.name.replace("_", " ").title())