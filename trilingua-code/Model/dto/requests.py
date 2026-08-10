# -*- coding: utf-8 -*-
"""
Translation request DTOs.

These models define the input contracts for all translation operations.
They are provider-agnostic and contain no AI logic.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


# Supported language codes (kept from original)
LANGUAGES = {
    "English":  "eng_Latn",
    "Cebuano":  "ceb_Latn",
    "Filipino": "tgl_Latn",
}

CODE_TO_LANG = {v: k for k, v in LANGUAGES.items()}


@dataclass
class TranslationRequest:
    """A request to translate text or a document chunk."""
    text: str
    source_lang: str          # Human-readable name, e.g. "English"
    target_lang: str          # Human-readable name, e.g. "Cebuano"
    source_code: str = ""     # Language code, auto-filled from source_lang
    target_code: str = ""     # Language code, auto-filled from target_lang
    context_hint: str = ""    # Optional context from previous chunks
    block_type: str = "paragraph"  # paragraph, header, footer, table_cell, etc.
    document_type: str = ""   # Document type for specialized prompts (Phase 4)
    document_metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.source_code and self.source_lang in LANGUAGES:
            self.source_code = LANGUAGES[self.source_lang]
        if not self.target_code and self.target_lang in LANGUAGES:
            self.target_code = LANGUAGES[self.target_lang]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DocumentTranslationRequest:
    """A request to translate an entire document."""
    file_path: str
    source_lang: str
    target_lang: str
    pdf_column_mode: str = "auto"
    mode: str = "balanced"               # Processing mode: fast, balanced, thorough, auto
    glossary_pairs: Optional[list] = None  # List of (source, target) tuples
    reference_file: Optional[str] = None   # Optional BLEU reference

    def to_dict(self) -> dict:
        return asdict(self)