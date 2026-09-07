# -*- coding: utf-8 -*-
"""
Document-level coherence polish pass (opt-in, default OFF).

After block-level translation a short pre-check decides whether a document
needs a coherence fix:

1. Deterministic heuristics — blocks that echo the source untranslated, or
   whose translated length is far out of line with the source, are flagged.
2. AI quality reviewer pre-check — when a reviewer is supplied, every
   non-passthrough block is batch-reviewed; blocks the reviewer wants
   retranslated are flagged too.

A single provider call then rewrites ONLY the flagged entries with
coherence-aware instructions (consistent terminology, pronoun and verb-focus
flow, no English word-for-word renderings). The block count, order, and
structural metadata are never changed, and the pass fails open (returns the
input unchanged) on any error.

Enable with TRANSLATION_COHERENCE_POLISH=true (default false). It is only
meaningful for languages where cross-block flow matters most (Cebuano,
Filipino); callers decide whether to invoke it.
"""

import os
import re

from pipeline.translation_pipeline import _is_echo_output, _parse_batch_response

_COHERENCE_POLISH_ENABLED = os.environ.get(
    "TRANSLATION_COHERENCE_POLISH", "false"
).lower() == "true"


def coherence_polish_enabled() -> bool:
    """Whether the document-level coherence polish pass is enabled."""
    return _COHERENCE_POLISH_ENABLED


def _text_of(maybe_block) -> str:
    """Extract the text from a block dict or a plain string."""
    if isinstance(maybe_block, dict):
        return maybe_block.get("text", "")
    return str(maybe_block or "")


def _pre_check_candidates(source_blocks, translated_blocks):
    """Deterministic flagging: echo output + word-count ratio outliers.

    Returns a list of (block_index, source_text, translated_text).
    """
    candidates = []
    for idx, (sb, tb) in enumerate(zip(source_blocks, translated_blocks)):
        src = _text_of(sb)
        tgt = _text_of(tb)
        if not src.strip() or not tgt.strip():
            continue
        if _is_echo_output(src, tgt):
            candidates.append((idx, src, tgt))
            continue
        src_words = len(src.split())
        tgt_words = len(tgt.split())
        if src_words > 0:
            ratio = tgt_words / src_words
            if ratio < 0.5 or ratio > 3.0:
                candidates.append((idx, src, tgt))
    return candidates


class CoherencePolishPass:
    """Rewrites flagged blocks for document-level coherence.

    Args:
        provider: The translation provider used for the polish call.
        quality_reviewer: Optional AIQualityReviewer for the pre-check.
    """

    def __init__(self, provider, quality_reviewer=None):
        self._provider = provider
        self._reviewer = quality_reviewer

    def polish_blocks(self, source_blocks, translated_blocks,
                      source_lang: str, target_lang: str,
                      document_type: str = "") -> list:
        """Polish *translated_blocks* in place of a new list of block dicts.

        Same count and order as the input; only the 'text' of flagged entries
        may change. Fails open: any error returns the input unchanged.
        """
        if not source_blocks or not translated_blocks:
            return translated_blocks

        candidates = _pre_check_candidates(source_blocks, translated_blocks)

        # AI quality reviewer pre-check over every non-passthrough block.
        if self._reviewer is not None:
            reviewed_entries = []
            for idx, (sb, tb) in enumerate(zip(source_blocks, translated_blocks)):
                src = _text_of(sb)
                tgt = _text_of(tb)
                if not src.strip() or not tgt.strip():
                    continue
                if src.strip() == tgt.strip():
                    continue
                reviewed_entries.append((idx, src, tgt))

            if reviewed_entries:
                try:
                    reviews = self._reviewer.batch_review(
                        reviewed_entries, document_type=document_type
                    )
                except Exception:
                    reviews = {}
                for idx, src, tgt in reviewed_entries:
                    review = reviews.get(idx)
                    if review is not None and self._reviewer.needs_retranslation(review):
                        if not any(c[0] == idx for c in candidates):
                            candidates.append((idx, src, tgt))

        if not candidates:
            return translated_blocks

        prompt = _build_polish_prompt(candidates, source_lang, target_lang)

        try:
            response = self._provider.translate(
                text=prompt,
                source_lang=source_lang,
                target_lang=target_lang,
                block_type="paragraph",
                context_hint=(
                    "Polish the flagged entries for document-level coherence; "
                    "keep numbers, names, and dates identical to the source."
                ),
                document_type=document_type,
            )
        except Exception:
            return translated_blocks

        if not response.success or not response.translated_text:
            return translated_blocks

        rewrites = _parse_batch_response(
            response.translated_text, [idx for idx, _, _ in candidates]
        )
        if not rewrites:
            return translated_blocks

        polished = [dict(b) for b in translated_blocks]
        changed = 0
        for idx, src, _tgt in candidates:
            new_text = rewrites.get(idx)
            if not new_text:
                continue
            new_text = new_text.strip()
            if not new_text or _is_echo_output(src, new_text):
                continue
            polished[idx]["text"] = new_text
            changed += 1

        if changed == 0:
            return translated_blocks
        return polished


def _build_polish_prompt(candidates, source_lang, target_lang) -> str:
    """Build the user prompt for the coherence polish provider call."""
    lines = [
        f"[BLOCK_{idx}] {src} ||| {tgt}" for idx, src, tgt in candidates
    ]
    return (
        f"You are polishing a {target_lang} translation for document-level "
        f"coherence. Each entry below is one flagged block:\n"
        f"[BLOCK_N] <{source_lang} source> ||| <current {target_lang} translation>\n\n"
        "Improve ONLY the translation side. Fix:\n"
        "- The same name or term translated differently across entries "
        "(pick one natural, consistent rendering)\n"
        "- Pronoun and verb-focus drift that breaks the flow between sentences\n"
        "- Untranslated source text left in the output\n"
        f"- Stiff, word-for-word English instead of natural {target_lang}\n\n"
        "STRICT RULES:\n"
        "1. Keep numbers, dates, proper names, URLs, and emails EXACTLY as in the source\n"
        "2. Do NOT add or remove sentences or information; keep the same meaning and length\n"
        "3. Use the SAME translation for the same repeated term in every entry\n"
        "4. If an entry is already correct, return it unchanged\n\n"
        f"Return ONLY valid JSON mapping each index to its polished {target_lang} "
        "translation, e.g. {\"0\": \"...\", \"2\": \"...\"}. No preamble.\n\n"
        "Entries:\n" + "\n".join(lines)
    )
