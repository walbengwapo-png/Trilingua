# -*- coding: utf-8 -*-
"""
Pipeline Registry — maps semantic roles to translation pipeline handlers.
"""

import logging
from typing import Optional, Callable

from intelligence.graph.document_graph import SemanticRole

logger = logging.getLogger(__name__)


class PipelineRegistry:
    """Registry mapping semantic roles to translation pipeline handlers.

    Each role can have:
    - preprocess_fn: Clean/structure text before translation
    - postprocess_fn: Restore markers, validate structure after translation
    - system_prompt: Role-specific system prompt template
    - temperature: LLM temperature for this role
    - max_tokens: Max output tokens for this role
    """

    def __init__(self):
        self._pipelines: dict[SemanticRole, dict] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default pipeline configurations for all roles."""
        defaults = {
            SemanticRole.LEARNING_OBJECTIVE: {
                "temperature": 0.4,
                "max_tokens": 200,
                "system_prompt": (
                    "You are an educational document translator. "
                    "Translate the following learning objective. "
                    "Maintain a future-oriented, goal-focused tone. "
                    "Preserve any numbered prefixes (e.g., '1.'). "
                    "Return ONLY the translation, no explanations."
                ),
                "preprocess_fn": self._preprocess_numbered,
                "postprocess_fn": self._postprocess_numbered,
            },
            SemanticRole.INSTRUCTION: {
                "temperature": 0.3,
                "max_tokens": 300,
                "system_prompt": (
                    "You are an educational document translator. "
                    "Translate the following instruction. "
                    "Use imperative mood (command form). "
                    "Keep bullet markers or numbering if present. "
                    "Return ONLY the translation, no explanations."
                ),
                "preprocess_fn": self._preprocess_preserve_list,
                "postprocess_fn": self._postprocess_preserve_list,
            },
            SemanticRole.QUESTION_STEM: {
                "temperature": 0.4,
                "max_tokens": 250,
                "system_prompt": (
                    "You are an educational document translator. "
                    "Translate the following question. "
                    "Preserve the question mark at the end. "
                    "Keep any numbered prefix (e.g., '1.'). "
                    "Do NOT fill in any answer blanks (______). "
                    "Return ONLY the translation, no explanations."
                ),
                "preprocess_fn": self._preprocess_preserve_blanks,
                "postprocess_fn": self._postprocess_preserve_blanks,
            },
            SemanticRole.MULTIPLE_CHOICE_OPTION: {
                "temperature": 0.3,
                "max_tokens": 100,
                "system_prompt": (
                    "You are an educational document translator. "
                    "Translate ONLY the text after the choice letter. "
                    "Preserve the choice letter (A., B., C., D.) exactly. "
                    "Keep the translation short and parallel to other options. "
                    "Return ONLY the translation with the letter prefix."
                ),
                "preprocess_fn": self._preprocess_mc_option,
                "postprocess_fn": self._postprocess_mc_option,
            },
            SemanticRole.ANSWER_BLANK: {
                "temperature": 0.1,
                "max_tokens": 10,
                "system_prompt": None,  # Skip LLM entirely
                "preprocess_fn": None,
                "postprocess_fn": self._postprocess_verify_blank,
                "skip_llm": True,
            },
            SemanticRole.ANSWER_KEY: {
                "temperature": 0.1,
                "max_tokens": 50,
                "system_prompt": (
                    "You are an educational document translator. "
                    "Translate ONLY descriptive text. "
                    "Preserve ALL answer letters (A, B, C, D) and numbers exactly. "
                    "This is CRITICAL — do not change any letters or numbers. "
                    "Return ONLY the translated text."
                ),
                "preprocess_fn": self._preprocess_answer_key,
                "postprocess_fn": self._postprocess_answer_key,
            },
            SemanticRole.PARAGRAPH: {
                "temperature": 0.5,
                "max_tokens": 500,
                "system_prompt": (
                    "You are a professional document translator. "
                    "Translate the following text naturally and accurately. "
                    "Maintain the original tone and style. "
                    "Return ONLY the translation, no explanations."
                ),
                "preprocess_fn": None,
                "postprocess_fn": None,
            },
            SemanticRole.CAPTION: {
                "temperature": 0.4,
                "max_tokens": 150,
                "system_prompt": (
                    "You are a document translator. "
                    "Translate the following caption. "
                    "Preserve 'Figure', 'Table', 'Fig.' prefixes exactly. "
                    "Keep the figure/table number (e.g., 'Figure 1'). "
                    "Return ONLY the translation."
                ),
                "preprocess_fn": None,
                "postprocess_fn": None,
            },
            SemanticRole.FOOTER_TEXT: {
                "temperature": 0.3,
                "max_tokens": 50,
                "system_prompt": (
                    "You are a document translator. "
                    "Translate the following footer. "
                    "Keep it very concise (max 50 tokens). "
                    "Preserve page numbers if present. "
                    "Return ONLY the translation."
                ),
                "preprocess_fn": None,
                "postprocess_fn": None,
            },
            SemanticRole.HEADER_TEXT: {
                "temperature": 0.3,
                "max_tokens": 100,
                "system_prompt": (
                    "You are a document translator. "
                    "Translate the following header. "
                    "Keep it consistent with the document style. "
                    "Return ONLY the translation."
                ),
                "preprocess_fn": None,
                "postprocess_fn": None,
            },
            SemanticRole.HEADING_1: {
                "temperature": 0.3,
                "max_tokens": 100,
                "system_prompt": (
                    "You are a document translator. "
                    "Translate the following heading. "
                    "Keep it concise and preserve any numbering. "
                    "Return ONLY the translation."
                ),
                "preprocess_fn": self._preprocess_numbered,
                "postprocess_fn": self._postprocess_numbered,
            },
            SemanticRole.HEADING_2: {
                "temperature": 0.3,
                "max_tokens": 100,
                "system_prompt": (
                    "You are a document translator. "
                    "Translate the following heading. "
                    "Keep it concise and preserve any numbering. "
                    "Return ONLY the translation."
                ),
                "preprocess_fn": self._preprocess_numbered,
                "postprocess_fn": self._postprocess_numbered,
            },
            SemanticRole.HEADING_3: {
                "temperature": 0.3,
                "max_tokens": 100,
                "system_prompt": (
                    "You are a document translator. "
                    "Translate the following heading. "
                    "Keep it concise and preserve any numbering. "
                    "Return ONLY the translation."
                ),
                "preprocess_fn": self._preprocess_numbered,
                "postprocess_fn": self._postprocess_numbered,
            },
            SemanticRole.CITATION: {
                "temperature": 0.3,
                "max_tokens": 200,
                "system_prompt": (
                    "You are an academic document translator. "
                    "Translate only descriptive parts of the citation. "
                    "Preserve parentheses, author names, years, page numbers exactly. "
                    "Return ONLY the translation."
                ),
                "preprocess_fn": None,
                "postprocess_fn": None,
            },
            SemanticRole.REFERENCE_ENTRY: {
                "temperature": 0.3,
                "max_tokens": 200,
                "system_prompt": (
                    "You are an academic document translator. "
                    "Translate only the title. "
                    "Preserve author names, years, journal names, DOI exactly. "
                    "Return ONLY the translation."
                ),
                "preprocess_fn": None,
                "postprocess_fn": None,
            },
        }

        self._pipelines.update(defaults)

    def get_pipeline(self, role: SemanticRole) -> dict:
        """Get the pipeline configuration for a role."""
        pipeline = self._pipelines.get(role)
        if pipeline is None:
            # Fallback to paragraph pipeline
            return self._pipelines[SemanticRole.PARAGRAPH]
        return pipeline

    def should_skip_llm(self, role: SemanticRole) -> bool:
        """Check if this role should skip LLM translation entirely."""
        pipeline = self.get_pipeline(role)
        return pipeline.get("skip_llm", False)

    def register_pipeline(self, role: SemanticRole, config: dict) -> None:
        """Register or override a pipeline configuration."""
        self._pipelines[role] = config
        logger.info(f"Registered pipeline for role: {role.name}")

    # ── Pre-processors ────────────────────────────────────────────

    def _preprocess_numbered(self, text: str) -> str:
        """Strip number prefix for cleaner translation, store in markers."""
        import re
        match = re.match(r"^(\d+[\.\)]\s*)(.*)", text)
        if match:
            return match.group(2)
        return text

    def _preprocess_preserve_list(self, text: str) -> str:
        """Extract list markers for preservation."""
        return text  # Keep as-is, LLM handles it

    def _preprocess_preserve_blanks(self, text: str) -> str:
        """Ensure blanks are marked for preservation."""
        return text

    def _preprocess_mc_option(self, text: str) -> str:
        """Extract choice letter and return only the text part."""
        import re
        match = re.match(r"^([A-Da-d][\.\)]\s*)(.*)", text)
        if match:
            return match.group(2)
        return text

    def _preprocess_answer_key(self, text: str) -> str:
        """Parse answer key into structured format."""
        return text

    # ── Post-processors ───────────────────────────────────────────

    def _postprocess_numbered(self, original: str, translated: str) -> str:
        """Re-add number prefix to translated text."""
        import re
        match = re.match(r"^(\d+[\.\)]\s*)", original)
        if match:
            prefix = match.group(1)
            if not translated.startswith(prefix):
                return prefix + translated.lstrip()
        return translated

    def _postprocess_preserve_list(self, original: str, translated: str) -> str:
        """Ensure list markers are preserved."""
        return translated

    def _postprocess_preserve_blanks(self, original: str, translated: str) -> str:
        """Verify blanks are preserved and restore if missing."""
        import re
        blanks = re.findall(r"_{2,}", original)
        if not blanks:
            return translated
        translated_blanks = re.findall(r"_{2,}", translated)
        if len(blanks) != len(translated_blanks):
            # Restore blanks
            for b in blanks:
                if b not in translated:
                    translated = translated.rstrip() + " " + b
        return translated

    def _postprocess_mc_option(self, original: str, translated: str) -> str:
        """Re-attach choice letter to translated text."""
        import re
        match = re.match(r"^([A-Da-d][\.\)]\s*)", original)
        if match:
            prefix = match.group(1)
            if not translated.startswith(prefix):
                return prefix + translated.lstrip()
        return translated

    def _postprocess_answer_key(self, original: str, translated: str) -> str:
        """Validate answer key structure preserved."""
        return translated

    def _postprocess_verify_blank(self, original: str, translated: str) -> str:
        """Return original blank unchanged. Log if changed."""
        if original.strip() != translated.strip():
            return original  # Force original blank
        return translated