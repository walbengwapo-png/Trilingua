# -*- coding: utf-8 -*-
"""
Hallucination detection and translation sanitization.

Extracted from document_translator_v3.py.
Responsible for detecting common hallucination patterns in AI translations.
Contains NO provider-specific code.
"""

import re


def sanitize_translation(translated_text, original_text):
    """
    Clean up a translated string by removing leaked context delimiters,
    stray markers, and detecting hallucinated repetition.
    """
    # 1. Strip leaked `|||` delimiters
    cleaned = re.sub(r'\s*\|\|\|\s*', ' ', translated_text)

    # 2. Strip stray "[Context:" markers if any leak through
    cleaned = re.sub(r'\[Context:[^\]]*\]', '', cleaned)

    # 3. Collapse repeated duplicate sentences (hallucination pattern)
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    if len(sentences) >= 3:
        unique_sentences = []
        for s in sentences:
            s_norm = s.strip().lower()
            if not unique_sentences or s_norm != unique_sentences[-1].lower():
                unique_sentences.append(s.strip())
        if len(unique_sentences) < len(sentences):
            cleaned = ' '.join(unique_sentences)

    # 4. Adaptive hallucination threshold based on source text length
    orig_words = len(original_text.split())
    clean_words = len(cleaned.split())
    if orig_words > 0:
        if orig_words <= 3:
            threshold = 25   # 1-3 word headings expand significantly in Cebuano/Filipino
        elif orig_words <= 15:
            threshold = 10   # Short phrases
        else:
            threshold = 5    # Long text - true hallucination risk

        if clean_words > orig_words * threshold:
            print(f"  ⚠️  Hallucinated repetition detected ({clean_words} vs {orig_words} words, "
                  f"ratio={clean_words/orig_words:.1f}x > {threshold}x), retrying...")
            raise RuntimeError("Hallucinated repetition detected, will retry")

    # 5. Clean up excessive whitespace
    cleaned = re.sub(r' {2,}', ' ', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned.strip()


def detect_hallucination(translated_text, original_text):
    """
    Detect common hallucination patterns in translation output.

    Returns (is_hallucinated: bool, reason: str) tuple.
    """
    if not translated_text or not original_text:
        return False, ""

    t = translated_text.strip()
    o = original_text.strip()

    # ── 1. Explanatory phrases ────────────────────────────────────────────────
    EXPLANATORY_PATTERNS = [
        r'^(here\s+(is|are|\'s)\s+the\s+translat)',
        r'^(the\s+translat)',
        r'^(translat(ion|ed)\s*:)',
        r'^(below\s+is)',
        r'^(in\s+\w+\s*,?\s*the\s+translat)',
        r'^(this\s+(is|translates?\s+to))',
        r'^(my\s+translat)',
        r'(here\s+is\s+the\s+translat)',
        r'(i\s+hope\s+this\s+helps)',
        r'(let\s+me\s+know\s+if)',
        r'(note\s*:)',
        r'(explanation\s*:)',
    ]
    for pat in EXPLANATORY_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return True, f"Explanatory phrase detected: {pat}"

    # ── 2. Verbosity check ────────────────────────────────────────────────────
    src_words = len(o.split())
    tgt_words = len(t.split())
    if src_words > 0:
        if src_words <= 5:
            max_ratio = 8.0
        elif src_words <= 30:
            max_ratio = 3.0
        else:
            max_ratio = 2.0
        if tgt_words > src_words * max_ratio:
            return True, f"Excessive verbosity ({tgt_words}/{src_words} = {tgt_words/src_words:.1f}x > {max_ratio}x)"

    # ── 3. Sentence count inflation ───────────────────────────────────────────
    def _count_sentences(text):
        return len(re.findall(r'[.!?]+', text))

    src_sentences = _count_sentences(o)
    tgt_sentences = _count_sentences(t)
    if src_sentences > 0 and tgt_sentences > src_sentences * 3:
        return True, f"Sentence inflation ({tgt_sentences} vs {src_sentences} sentences)"
    if src_sentences == 0 and tgt_sentences >= 3:
        return True, f"Added sentence-ending punctuation ({tgt_sentences} found, source has none)"

    return False, ""