# -*- coding: utf-8 -*-
"""
Document chunker.

Responsible for splitting document text into translation-safe chunks.
Contains NO translation logic and NO provider-specific code.

Reused from document_translator_v3.py Chunk_Splitter.
"""


class ChunkSplitter:
    """Splits a long text block into translation-safe chunks at sentence boundaries.

    Uses a word-token model (one token = one whitespace-delimited word).
    Sentence boundaries are tokens that end with '.', '!', or '?'.
    """

    def split(
        self,
        text: str,
        max_tokens: int = 400,
        hard_cap: int = 600,
        min_tokens: int = 10,
    ) -> list:
        """Split *text* into chunks of at most *max_tokens* words, honouring
        sentence boundaries.

        Parameters
        ----------
        text:       The source text to split.
        max_tokens: Preferred maximum tokens (words) per chunk.
        hard_cap:   Absolute maximum tokens before giving up on splitting.
        min_tokens: Minimum tokens in a trailing chunk; smaller tails are merged
                    back into the previous chunk.

        Returns
        -------
        A list of strings whose concatenated words reproduce *text* exactly
        (round-trip property).
        """
        # Edge-case: empty or whitespace-only input.
        if not text or not text.strip():
            return [""]

        # Clamp max_tokens to at least 1 to avoid infinite loops.
        if max_tokens <= 0:
            max_tokens = 1

        tokens = text.split()

        # Step 1 — short-circuit: text already fits in one chunk.
        if len(tokens) <= max_tokens:
            return [text]

        # Steps 2-4 — find the best split boundary.
        best_boundary = None

        # Scan up to hard_cap (exclusive) to collect all candidates.
        scan_limit = min(hard_cap, len(tokens))

        # Pass 1: pick the LAST candidate within [0, max_tokens).
        for i in range(min(max_tokens, scan_limit)):
            if tokens[i].endswith(('.', '!', '?')):
                best_boundary = i

        # Pass 2: if nothing found in preferred zone, take the FIRST candidate
        # in the extended zone [max_tokens, hard_cap).
        if best_boundary is None:
            for i in range(max_tokens, scan_limit):
                if tokens[i].endswith(('.', '!', '?')):
                    best_boundary = i
                    break

        # Step 5 — no candidate anywhere within hard_cap → return unsplit.
        if best_boundary is None:
            return [text]

        # Step 6 — split at the chosen boundary.
        first_tokens = tokens[:best_boundary + 1]
        remainder_tokens = tokens[best_boundary + 1:]

        # Step 7 — merge short tails back.
        if len(remainder_tokens) < min_tokens:
            return [text]

        # Step 8 — recurse on the remainder.
        first_chunk = " ".join(first_tokens)
        remainder_text = " ".join(remainder_tokens)
        rest_chunks = self.split(remainder_text, max_tokens, hard_cap, min_tokens)

        return [first_chunk] + rest_chunks


def chunk_blocks(blocks, max_tokens_per_chunk=400):
    """Split a list of text blocks into chunks suitable for translation.

    Each block is independently chunked if it exceeds max_tokens.
    Returns a list of (block_index, chunk_text) tuples.
    """
    splitter = ChunkSplitter()
    result = []
    for idx, block in enumerate(blocks):
        text = block.get("text", "")
        if not text.strip():
            continue
        chunks = splitter.split(text, max_tokens=max_tokens_per_chunk)
        for chunk in chunks:
            result.append((idx, chunk))
    return result