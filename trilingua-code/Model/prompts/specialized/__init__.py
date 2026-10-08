# -*- coding: utf-8 -*-
"""
Specialized translation prompt selector.

Automatically chooses the optimal translation prompt based on the
document type detected by the AI Document Analyzer (Phase 1).

Each specialized prompt optimizes terminology, tone, and constraints
for its document category. Falls back to the general system prompt
for document types without a specialized prompt.

Usage:
    from prompts.specialized import get_system_prompt
    system_msg = get_system_prompt(document_type, target_lang)
"""

from prompts.system import build_system_prompt

# Import specialized prompts
from .academic import ACADEMIC_PROMPT
from .legal import LEGAL_PROMPT
from .business import BUSINESS_PROMPT
from .medical import MEDICAL_PROMPT
from .technical import TECHNICAL_PROMPT
from .resume import RESUME_PROMPT
from .invoice import INVOICE_PROMPT
from .presentation import PRESENTATION_PROMPT

# Document type to prompt mapping
SPECIALIZED_PROMPTS = {
    "research_paper": ACADEMIC_PROMPT,
    "academic": ACADEMIC_PROMPT,
    "legal_contract": LEGAL_PROMPT,
    "legal": LEGAL_PROMPT,
    "contract": LEGAL_PROMPT,
    "business_proposal": BUSINESS_PROMPT,
    "business": BUSINESS_PROMPT,
    "proposal": BUSINESS_PROMPT,
    "medical_report": MEDICAL_PROMPT,
    "medical": MEDICAL_PROMPT,
    "clinical": MEDICAL_PROMPT,
    "technical_manual": TECHNICAL_PROMPT,
    "technical": TECHNICAL_PROMPT,
    "manual": TECHNICAL_PROMPT,
    "resume": RESUME_PROMPT,
    "cv": RESUME_PROMPT,
    "invoice": INVOICE_PROMPT,
    "presentation": PRESENTATION_PROMPT,
    "slides": PRESENTATION_PROMPT,
}


def get_system_prompt(document_type: str, target_lang: str = "") -> str:
    """Get the appropriate system prompt for a document type.

    Args:
        document_type: The document type detected by the analyzer.
                       (e.g., 'legal_contract', 'research_paper', 'general_document')
        target_lang: The target language name (for prompt customization).

    Returns:
        A system prompt string optimized for the document type,
        or the default general prompt if no specialization exists.
    """
    # Try exact match first
    prompt = SPECIALIZED_PROMPTS.get(document_type)

    # Try lowercase match
    if prompt is None:
        prompt = SPECIALIZED_PROMPTS.get(document_type.lower())

    if prompt is not None:
        return prompt.format(target_lang=target_lang)

    # Fallback to general prompt
    return build_system_prompt(target_lang)


def get_available_types() -> list[str]:
    """Return the list of document types with specialized prompts."""
    return sorted(set(
        key for key in SPECIALIZED_PROMPTS.keys()
        if not key.endswith(('_', ' ')) and len(key) > 3
    ))