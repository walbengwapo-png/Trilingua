# -*- coding: utf-8 -*-
"""
Prepass prompt builders for two-pass context injection (Task 5).

The prepass runs before the main translation pass. It sends the first
500 tokens of the document to the provider and asks for:
1. A one-sentence document summary
2. The detected domain
3. Up to 10 key terms with likely Cebuano/Filipino equivalents

This context is injected into every block's system prompt for better
translation quality.

Controlled by TRANSLATION_PREPASS_ENABLED env var (default: true
in balanced and thorough modes).
"""


def build_prepass_system_prompt() -> str:
    """Build the system prompt for the prepass analysis.

    Returns:
        A system prompt that instructs the AI to analyze document context.
    """
    return (
        "You are a document analyst. Your task is to analyze the beginning "
        "of a document that needs translation. Extract key context that will "
        "help a translator produce better results.\n\n"
        "Return ONLY valid JSON with these fields:\n"
        "{\n"
        '  "summary": "One-sentence summary of the document",\n'
        '  "domain": "Detected domain (e.g., medical, legal, technical, academic, business, general)",\n'
        '  "terms": [\n'
        '    {"source": "key term in source language", '
        '"target": "likely equivalent in target language"}\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- The summary must be exactly one sentence.\n"
        "- The domain must be one word: medical, legal, technical, academic, "
        "business, marketing, conversational, or general.\n"
        "- Return up to 10 key terms. Fewer is fine if the text is short.\n"
        "- If unsure about a term's equivalent, make your best guess.\n"
        "- Return ONLY valid JSON, no preamble, no explanation."
    )


def build_prepass_user_prompt(doc_text: str, source_lang: str,
                               target_lang: str) -> str:
    """Build the user prompt for the prepass analysis.

    Args:
        doc_text: The beginning of the document (first ~500 tokens).
        source_lang: The source language name.
        target_lang: The target language name.

    Returns:
        A user prompt string.
    """
    return (
        f"Analyze this text that will be translated from {source_lang} "
        f"to {target_lang}. Provide a summary, domain, and key terms:\n\n"
        f"{doc_text}"
    )


def build_prepass_injection(summary: str, domain: str,
                            terms: list[tuple[str, str]]) -> str:
    """Build the context preamble to inject into every block's system prompt.

    Args:
        summary: One-sentence document summary from prepass.
        domain: Detected document domain.
        terms: List of (source_term, target_equivalent) tuples.

    Returns:
        A formatted preamble string.
    """
    parts = [f"Document context: {summary}"]

    if domain:
        parts.append(f"Domain: {domain}")

    if terms:
        term_lines = [f"  {src} → {tgt}" for src, tgt in terms[:10]]
        parts.append("Key terminology:\n" + "\n".join(term_lines))

    return "\n\n" + "\n".join(parts)