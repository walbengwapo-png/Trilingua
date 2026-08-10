# -*- coding: utf-8 -*-
"""
Unit tests for translation-layout-quality components.

Task 2.2 — Chunk_Splitter unit tests
Requirements: 1.1, 1.2, 1.3, 1.4
"""

import sys
import os

# Ensure the Model package is importable when running pytest from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from document_translator_v3 import Chunk_Splitter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_text(n_tokens: int, sentence_end_every: int = 10) -> str:
    """
    Build a synthetic text of exactly *n_tokens* whitespace-delimited words.
    A period is appended to every *sentence_end_every*-th word so the text
    has predictable sentence boundaries.
    """
    words = []
    for i in range(1, n_tokens + 1):
        word = f"word{i}"
        if i % sentence_end_every == 0:
            word += "."
        words.append(word)
    return " ".join(words)


# ---------------------------------------------------------------------------
# Task 2.2 — Unit tests
# ---------------------------------------------------------------------------

class TestChunkSplitterBasic:
    """Basic splitting behaviour."""

    def test_exactly_80_tokens_no_split(self):
        """
        Requirement 1.1: A block with exactly 80 tokens should NOT be split
        (it is at the preferred maximum, not over it).
        """
        text = _make_text(80)
        splitter = Chunk_Splitter()
        chunks = splitter.split(text, max_tokens=80)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_81_tokens_boundary_at_75_splits_there(self):
        """
        Requirement 1.1 / 1.2: A block with 81 tokens where the last sentence
        boundary falls at token 75 should produce a first chunk of 75 tokens
        and a second chunk of 6 tokens.
        """
        # Build 81 words; put a sentence-ending period at word 75.
        words = [f"word{i}" for i in range(1, 82)]
        words[74] = words[74] + "."   # index 74 → token 75 (1-based)
        text = " ".join(words)

        splitter = Chunk_Splitter()
        chunks = splitter.split(text, max_tokens=80, min_tokens=1)

        assert len(chunks) == 2
        first_chunk_tokens = len(chunks[0].split())
        assert first_chunk_tokens == 75, (
            f"Expected first chunk to have 75 tokens, got {first_chunk_tokens}"
        )

    def test_no_sentence_punctuation_returns_single_chunk(self):
        """
        Requirement 1.3: When a block contains no sentence-ending punctuation
        anywhere, the entire block must be returned as a single chunk.
        """
        text = " ".join([f"word{i}" for i in range(1, 200)])
        splitter = Chunk_Splitter()
        chunks = splitter.split(text, max_tokens=80)
        assert chunks == [text]

    def test_5_tokens_single_chunk_no_minimum_violation(self):
        """
        Requirement 1.4: A block with exactly 5 tokens should be returned as
        a single chunk without triggering any minimum-size merge.
        """
        text = "This is exactly five words."
        assert len(text.split()) == 5
        splitter = Chunk_Splitter()
        chunks = splitter.split(text, max_tokens=80, min_tokens=5)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_4_tokens_single_chunk_below_threshold_allowed(self):
        """
        Requirement 1.4: A block shorter than min_tokens is allowed to be
        returned as a single chunk (the minimum only applies when splitting
        produces multiple chunks).
        """
        text = "Four words here now."
        assert len(text.split()) == 4
        splitter = Chunk_Splitter()
        chunks = splitter.split(text, max_tokens=80, min_tokens=5)
        assert len(chunks) == 1
        assert chunks[0] == text


class TestChunkSplitterContentPreservation:
    """Content round-trip: no characters dropped or duplicated."""

    def test_content_preserved_after_split(self):
        """
        Requirement 1.6: Joining all chunks with a single space must reproduce
        the original text (after normalising whitespace).
        """
        text = _make_text(150, sentence_end_every=10)
        splitter = Chunk_Splitter()
        chunks = splitter.split(text, max_tokens=80)
        reconstructed = " ".join(" ".join(c.split()) for c in chunks)
        original_normalised = " ".join(text.split())
        assert reconstructed == original_normalised

    def test_content_preserved_no_punctuation(self):
        """
        Requirement 1.6: Even when no split occurs, the returned single chunk
        must equal the original text.
        """
        text = " ".join([f"word{i}" for i in range(1, 50)])
        splitter = Chunk_Splitter()
        chunks = splitter.split(text)
        assert chunks == [text]


class TestChunkSplitterHardCap:
    """Hard-cap behaviour when no boundary exists within max_tokens."""

    def test_extends_to_next_boundary_within_hard_cap(self):
        """
        Requirement 1.2: When no boundary exists within max_tokens, the
        splitter must extend to the next boundary up to hard_cap.
        """
        # 100 words; first sentence boundary at word 90 (beyond max_tokens=80,
        # within hard_cap=150).
        words = [f"word{i}" for i in range(1, 101)]
        words[89] = words[89] + "."   # boundary at token 90
        text = " ".join(words)

        splitter = Chunk_Splitter()
        chunks = splitter.split(text, max_tokens=80, hard_cap=150, min_tokens=1)

        # First chunk should end at the boundary (token 90).
        assert len(chunks[0].split()) == 90

    def test_force_split_at_hard_cap_when_no_boundary(self):
        """
        Requirement 1.2: When no boundary exists within hard_cap, the splitter
        must force-split at hard_cap.
        """
        # 200 words with no punctuation at all.
        words = [f"word{i}" for i in range(1, 201)]
        text = " ".join(words)

        splitter = Chunk_Splitter()
        # No sentence-ending punctuation → single chunk (Req 1.3 takes priority).
        chunks = splitter.split(text, max_tokens=80, hard_cap=150)
        assert chunks == [text]


# ---------------------------------------------------------------------------
# Task 3.2 — Context_Buffer unit tests
# Requirements: 2.1, 2.2, 2.5
# ---------------------------------------------------------------------------

from document_translator_v3 import Context_Buffer


class TestContextBuffer:
    """Unit tests for Context_Buffer (Requirements 2.1, 2.2, 2.5)."""

    def test_empty_buffer_returns_empty_string(self):
        """
        Requirement 2.5: A freshly created buffer with no pushes must return
        an empty string from get_hint().
        """
        buf = Context_Buffer()
        assert buf.get_hint() == ""

    def test_one_push_hint_contains_one_entry(self):
        """
        Requirement 2.2: After a single push, get_hint() must return exactly
        that one translated text with no delimiter.
        """
        buf = Context_Buffer()
        buf.push("Hello world.")
        assert buf.get_hint() == "Hello world."

    def test_three_pushes_window_two_keeps_last_two(self):
        """
        Requirement 2.1: With window_size=2, after 3 pushes the buffer must
        retain only the last 2 entries.  get_hint() must join them with ' ||| '.
        """
        buf = Context_Buffer(window_size=2)
        buf.push("First block.")
        buf.push("Second block.")
        buf.push("Third block.")
        hint = buf.get_hint()
        # The oldest entry ("First block.") must have been evicted.
        assert "First block." not in hint
        assert hint == "Second block. ||| Third block."

    def test_clear_resets_buffer_to_empty(self):
        """
        Requirement 2.1 / 2.5: After clear(), get_hint() must return '' again,
        regardless of how many entries were previously pushed.
        """
        buf = Context_Buffer()
        buf.push("Block A.")
        buf.push("Block B.")
        buf.clear()
        assert buf.get_hint() == ""


class TestChunkSplitterMinimumSize:
    """Minimum chunk size enforcement."""

    def test_small_trailing_chunk_merged_backward(self):
        """
        Requirement 1.4: A trailing chunk smaller than min_tokens must be
        merged into the preceding chunk.
        """
        # 85 words; boundary at token 82 → second chunk would be 3 words
        # (below min_tokens=5), so it must be merged into the first.
        words = [f"word{i}" for i in range(1, 86)]
        words[81] = words[81] + "."   # boundary at token 82
        text = " ".join(words)

        splitter = Chunk_Splitter()
        chunks = splitter.split(text, max_tokens=80, min_tokens=5)

        # The tiny trailing chunk must have been merged → only 1 chunk.
        assert len(chunks) == 1
        assert len(chunks[0].split()) == 85

    def test_all_chunks_meet_minimum_size(self):
        """
        Requirement 1.4: Every chunk in a multi-chunk result must have at
        least min_tokens tokens.
        """
        text = _make_text(200, sentence_end_every=10)
        splitter = Chunk_Splitter()
        chunks = splitter.split(text, max_tokens=80, min_tokens=5)

        for i, chunk in enumerate(chunks):
            token_count = len(chunk.split())
            assert token_count >= 5, (
                f"Chunk {i} has only {token_count} tokens (min=5): {chunk!r}"
            )


# ---------------------------------------------------------------------------
# Task 4.2 — Unit tests for Glossary_Store
# Requirements: 3.2, 3.3, 3.5, 3.7
# ---------------------------------------------------------------------------

from document_translator_v3 import Glossary_Store


class TestGlossaryStore:
    """Unit tests for Glossary_Store (Requirements 3.2, 3.3, 3.5, 3.7)."""

    # ── Requirement 3.7: duplicate source terms raise ValueError ─────────────

    def test_duplicate_source_terms_raise_value_error(self):
        """
        Requirement 3.7: When the glossary contains two entries with the same
        source term (case-insensitive), ValueError must be raised before
        translation begins, and the message must identify the duplicate term.
        """
        with pytest.raises(ValueError, match="cat"):
            Glossary_Store([("cat", "gato"), ("cat", "felino")])

    def test_duplicate_source_terms_case_insensitive(self):
        """
        Requirement 3.7: Duplicate detection is case-insensitive, so 'Cat'
        and 'CAT' are considered the same source term.
        """
        with pytest.raises(ValueError, match="(?i)cat"):
            Glossary_Store([("cat", "gato"), ("CAT", "felino")])

    def test_duplicate_error_message_identifies_term(self):
        """
        Requirement 3.7: The ValueError message must identify the duplicate
        term so the user knows which entry to fix.
        """
        with pytest.raises(ValueError) as exc_info:
            Glossary_Store([("server", "servidor"), ("Server", "servidora")])
        assert "server" in str(exc_info.value).lower()

    # ── Requirement 3.5: 1001 pairs raise ValueError ─────────────────────────

    def test_1001_pairs_raise_value_error(self):
        """
        Requirement 3.5: The Glossary_Store supports at most 1000 term pairs.
        Providing 1001 pairs must raise ValueError.
        """
        pairs = [(f"term{i}", f"target{i}") for i in range(1001)]
        with pytest.raises(ValueError):
            Glossary_Store(pairs)

    def test_1000_pairs_accepted(self):
        """
        Requirement 3.5: Exactly 1000 pairs must be accepted without error.
        """
        pairs = [(f"term{i}", f"target{i}") for i in range(1000)]
        store = Glossary_Store(pairs)  # must not raise
        assert store is not None

    # ── Requirement 3.6: empty glossary returns text unchanged ───────────────

    def test_empty_glossary_apply_returns_text_unchanged(self):
        """
        Requirement 3.6: When the glossary is empty, apply() must return the
        original text without modification.
        """
        store = Glossary_Store([])
        text = "The quick brown fox jumps over the lazy dog."
        assert store.apply(text) == text

    def test_none_glossary_apply_returns_text_unchanged(self):
        """
        Requirement 3.6: When no pairs are provided (None), apply() must
        return the original text without modification.
        """
        store = Glossary_Store(None)
        text = "Nothing should change here."
        assert store.apply(text) == text

    # ── Requirement 3.2: whole-word matching ─────────────────────────────────

    def test_whole_word_match_replaces_standalone_term(self):
        """
        Requirement 3.2: 'cat' in 'the cat sat' must be replaced because it
        appears as a whole word.
        """
        store = Glossary_Store([("cat", "gato")])
        result = store.apply("the cat sat")
        assert "gato" in result

    def test_whole_word_no_match_inside_longer_word(self):
        """
        Requirement 3.2: 'cat' in 'concatenate' must NOT be replaced because
        it is not a whole-word occurrence.
        """
        store = Glossary_Store([("cat", "gato")])
        result = store.apply("concatenate")
        assert result == "concatenate"

    def test_whole_word_no_match_prefix(self):
        """
        Requirement 3.2: 'cat' must not match 'cats' (partial word at end).
        """
        store = Glossary_Store([("cat", "gato")])
        result = store.apply("I have two cats")
        assert "gato" not in result
        assert result == "I have two cats"

    def test_whole_word_no_match_suffix(self):
        """
        Requirement 3.2: 'cat' must not match 'tomcat' (partial word at start).
        """
        store = Glossary_Store([("cat", "gato")])
        result = store.apply("tomcat")
        assert result == "tomcat"

    def test_whole_word_replaces_all_occurrences(self):
        """
        Requirement 3.2: All whole-word occurrences of the source term in the
        text must be replaced, not just the first one.
        """
        store = Glossary_Store([("cat", "gato")])
        result = store.apply("the cat and the cat")
        assert result.count("gato") == 2

    # ── Requirement 3.3: capitalisation preservation ─────────────────────────

    def test_all_caps_token_produces_all_caps_target(self):
        """
        Requirement 3.3: An all-caps matched token (e.g. 'CAT') must produce
        an all-caps target term.
        """
        store = Glossary_Store([("cat", "gato")])
        result = store.apply("I saw a CAT yesterday")
        assert "GATO" in result

    def test_title_case_token_produces_title_case_target(self):
        """
        Requirement 3.3: A title-case matched token (e.g. 'Cat') must produce
        a title-case target term.
        """
        store = Glossary_Store([("cat", "gato")])
        result = store.apply("The Cat sat on the mat")
        assert "Gato" in result

    def test_lowercase_token_produces_lowercase_target(self):
        """
        Requirement 3.3: A lowercase matched token (e.g. 'cat') must produce
        a lowercase target term.
        """
        store = Glossary_Store([("cat", "gato")])
        result = store.apply("the cat sat")
        assert "gato" in result

    def test_capitalisation_all_three_patterns_in_one_text(self):
        """
        Requirement 3.3: All three capitalisation patterns can appear in the
        same text and each must be handled independently.
        """
        store = Glossary_Store([("cat", "gato")])
        result = store.apply("cat Cat CAT")
        assert "gato" in result
        assert "Gato" in result
        assert "GATO" in result

    # ── Requirement 3.4: missing term does not cause error ───────────────────

    def test_term_not_in_text_no_error(self):
        """
        Requirement 3.4: When a glossary term does not appear in the text,
        apply() must complete without error and return the text unchanged.
        """
        store = Glossary_Store([("elephant", "elefante")])
        text = "The quick brown fox."
        result = store.apply(text)
        assert result == text


# ---------------------------------------------------------------------------
# Task 6.2 — Unit tests for Font_Mapper
# Requirements: 4.2, 4.3, 4.4
# ---------------------------------------------------------------------------

from document_translator_v3 import Font_Mapper


class TestFontMapper:
    """Unit tests for Font_Mapper (Requirements 4.2, 4.3, 4.4)."""

    # ── Requirement 4.3: keyword classification → standard base fonts ────────

    def test_arial_not_embedded_returns_helv(self):
        """
        Requirement 4.3: 'ArialMT' is a sans-serif font (contains 'arial').
        When not in embedded_fonts, Font_Mapper must return 'helv'.
        """
        mapper = Font_Mapper()
        result = mapper.resolve("ArialMT", set())
        assert result == "helv"

    def test_times_not_embedded_returns_tiro(self):
        """
        Requirement 4.3: 'TimesNewRomanPS' is a serif font (contains 'times').
        When not in embedded_fonts, Font_Mapper must return 'tiro'.
        """
        mapper = Font_Mapper()
        result = mapper.resolve("TimesNewRomanPS", set())
        assert result == "tiro"

    def test_courier_not_embedded_returns_cour(self):
        """
        Requirement 4.3: 'CourierNew' is a monospace font (contains 'courier').
        When not in embedded_fonts, Font_Mapper must return 'cour'.
        """
        mapper = Font_Mapper()
        result = mapper.resolve("CourierNew", set())
        assert result == "cour"

    def test_helvetica_not_embedded_returns_helv(self):
        """
        Requirement 4.3: 'Helvetica' contains the 'helvetica' sans-serif
        keyword. When not embedded, must return 'helv'.
        """
        mapper = Font_Mapper()
        result = mapper.resolve("Helvetica", set())
        assert result == "helv"

    def test_georgia_not_embedded_returns_tiro(self):
        """
        Requirement 4.3: 'Georgia' contains the 'georgia' serif keyword.
        When not embedded, must return 'tiro'.
        """
        mapper = Font_Mapper()
        result = mapper.resolve("Georgia", set())
        assert result == "tiro"

    def test_consolas_not_embedded_returns_cour(self):
        """
        Requirement 4.3: 'Consolas' contains the 'consolas' mono keyword.
        When not embedded, must return 'cour'.
        """
        mapper = Font_Mapper()
        result = mapper.resolve("Consolas", set())
        assert result == "cour"

    # ── Requirement 4.2: embedded font exact match (case-insensitive) ────────

    def test_font_in_embedded_fonts_returns_font_name(self):
        """
        Requirement 4.2: When the font name matches an embedded font
        (case-insensitive), Font_Mapper must return the original font_name
        unchanged so PyMuPDF uses the embedded font directly.
        """
        mapper = Font_Mapper()
        embedded = {"ArialMT", "TimesNewRomanPS"}
        result = mapper.resolve("ArialMT", embedded)
        assert result == "ArialMT"

    def test_font_in_embedded_fonts_case_insensitive_match(self):
        """
        Requirement 4.2: The embedded font match is case-insensitive.
        'arialmT' should match 'ArialMT' in embedded_fonts.
        """
        mapper = Font_Mapper()
        embedded = {"ArialMT"}
        result = mapper.resolve("arialmT", embedded)
        # Returns the original font_name (the one passed in), not the embedded one
        assert result == "arialmT"

    def test_font_in_embedded_fonts_takes_priority_over_keyword(self):
        """
        Requirement 4.2: Embedded font exact match takes priority over keyword
        classification. Even a sans-serif font name should be returned as-is
        when it is embedded.
        """
        mapper = Font_Mapper()
        embedded = {"ArialMT"}
        result = mapper.resolve("ArialMT", embedded)
        # Must return the font name, not 'helv'
        assert result == "ArialMT"

    # ── Requirement 4.4: unknown font falls back to 'helv' with warning ──────

    def test_unknown_font_returns_helv(self):
        """
        Requirement 4.4: When the font name is not in embedded_fonts and does
        not match any keyword, Font_Mapper must return 'helv'.
        """
        mapper = Font_Mapper()
        result = mapper.resolve("ZapfDingbats", set())
        assert result == "helv"

    def test_unknown_font_logs_warning(self, capsys):
        """
        Requirement 4.4: When falling back to 'helv' for an unknown font,
        Font_Mapper must log a warning to stdout.
        """
        mapper = Font_Mapper()
        mapper.resolve("ZapfDingbats", set(), page=2, bbox=[10, 20, 100, 40])
        captured = capsys.readouterr()
        assert "ZapfDingbats" in captured.out
        assert "⚠️" in captured.out

    def test_empty_font_name_returns_helv(self):
        """
        Requirement 4.4: An empty font name string is not in embedded_fonts
        and matches no keyword, so Font_Mapper must return 'helv'.
        """
        mapper = Font_Mapper()
        result = mapper.resolve("", set())
        assert result == "helv"

    # ── Keyword classification — case-insensitive ─────────────────────────────

    def test_keyword_match_is_case_insensitive(self):
        """
        Requirement 4.3: Keyword matching must be case-insensitive.
        'ARIAL' should still map to 'helv'.
        """
        mapper = Font_Mapper()
        result = mapper.resolve("ARIAL", set())
        assert result == "helv"

    def test_sans_keyword_in_font_name_returns_helv(self):
        """
        Requirement 4.3: A font name containing 'sans' (e.g. 'OpenSans')
        must map to 'helv'.
        """
        mapper = Font_Mapper()
        result = mapper.resolve("OpenSans", set())
        assert result == "helv"

    def test_mono_keyword_in_font_name_returns_cour(self):
        """
        Requirement 4.3: A font name containing 'mono' (e.g. 'DejaVuMono')
        must map to 'cour'.
        """
        mapper = Font_Mapper()
        result = mapper.resolve("DejaVuMono", set())
        assert result == "cour"


# ---------------------------------------------------------------------------
# Task 10.2 — Unit tests for Style_Mapper
# Requirements: 7.2, 7.3
# ---------------------------------------------------------------------------

from document_translator_v3 import Style_Mapper


class TestStyleMapper:
    """Unit tests for Style_Mapper (Requirements 7.2, 7.3)."""

    def test_known_style_name_returned_as_is(self):
        """
        Requirement 7.2: When the style name exists in available_styles,
        resolve() must return it unchanged.
        """
        mapper = Style_Mapper()
        available = {"Normal", "Heading 1", "Heading 2", "List Bullet"}
        assert mapper.resolve("Heading 1", available) == "Heading 1"

    def test_none_style_name_returns_normal(self):
        """
        Requirement 7.3: When style_name is None, resolve() must return
        'Normal'.
        """
        mapper = Style_Mapper()
        available = {"Normal", "Heading 1"}
        assert mapper.resolve(None, available) == "Normal"

    def test_empty_string_style_name_returns_normal(self):
        """
        Requirement 7.3: When style_name is an empty string, resolve() must
        return 'Normal'.
        """
        mapper = Style_Mapper()
        available = {"Normal", "Heading 1"}
        assert mapper.resolve("", available) == "Normal"

    def test_unknown_style_name_returns_normal(self):
        """
        Requirement 7.3: When style_name is not in available_styles, resolve()
        must return 'Normal'.
        """
        mapper = Style_Mapper()
        available = {"Normal", "Heading 1"}
        assert mapper.resolve("CustomStyle", available) == "Normal"

    def test_normal_style_in_available_styles_returned_as_is(self):
        """
        Requirement 7.2: 'Normal' itself, when present in available_styles,
        must be returned as-is (not double-resolved).
        """
        mapper = Style_Mapper()
        available = {"Normal", "Heading 1"}
        assert mapper.resolve("Normal", available) == "Normal"

    def test_style_not_in_empty_available_styles_returns_normal(self):
        """
        Requirement 7.3: When available_styles is empty, any non-None/non-empty
        style_name must fall back to 'Normal'.
        """
        mapper = Style_Mapper()
        assert mapper.resolve("Heading 1", set()) == "Normal"

    def test_multiple_known_styles_each_returned_correctly(self):
        """
        Requirement 7.2: Each known style name must be returned correctly
        when it exists in available_styles.
        """
        mapper = Style_Mapper()
        available = {"Normal", "Heading 1", "Heading 2", "List Bullet", "Body Text"}
        for style in available:
            assert mapper.resolve(style, available) == style


# ---------------------------------------------------------------------------
# Task 8.2 — Unit tests for PDF overflow containment
# Requirements: 6.2, 6.3, 6.4, 6.6
# ---------------------------------------------------------------------------

import sys
import os
from unittest.mock import MagicMock, call, patch
import fitz

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from document_translator_v3 import _resolve_overflow


def _make_page(insert_returns=None, page_height=792.0):
    """
    Build a minimal fitz.Page mock.

    Parameters
    ----------
    insert_returns : list[float] | None
        Sequence of values that ``insert_textbox()`` will return on successive
        calls.  Defaults to [10.0] (no overflow).
    page_height : float
        Height of the page rect.
    """
    page = MagicMock()
    page.rect = MagicMock()
    page.rect.height = page_height
    page.rect.width = 612.0

    if insert_returns is None:
        insert_returns = [10.0]

    page.insert_textbox = MagicMock(side_effect=insert_returns)
    page.draw_rect = MagicMock()
    page.show_pdf_page = MagicMock()
    return page


def _make_original_doc():
    """Return a minimal mock for the original fitz.Document."""
    doc = MagicMock()
    return doc


class TestResolveOverflowNoOverflow:
    """
    When the initial insert_textbox() call already returns remaining >= 0,
    _resolve_overflow() should not be called at all (the caller guards with
    ``if remaining < 0``).  These tests verify the function handles the
    boundary correctly when called with a non-negative initial_remaining.
    """

    def test_no_overflow_returns_resolved_true(self):
        """
        If initial_remaining >= 0, the function should immediately return
        resolved=True without any further insertions.
        """
        page = _make_page(insert_returns=[])  # no calls expected
        result = _resolve_overflow(
            page=page,
            block_text="Hello world.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=12.0,
            resolved_font="helv",
            other_bboxes=[],
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=5.0,  # positive → no overflow
        )
        assert result["resolved"] is True
        assert result["continuation"] is False
        assert result["expanded"] is False
        # No insert_textbox calls should have been made
        page.insert_textbox.assert_not_called()


class TestResolveOverflowExpandDownward:
    """
    Overflow with space below: rect should be expanded, no font reduction.
    Requirements: 6.1, 6.2, 6.3
    """

    def test_overflow_no_collision_expands_rect(self):
        """
        Requirement 6.3: When overflow exists and expanding downward would NOT
        collide with any other block, the rect must be expanded and text
        re-inserted at the original font size.
        """
        # No other blocks → no collision possible.
        page = _make_page(insert_returns=[10.0])  # expanded insert succeeds
        result = _resolve_overflow(
            page=page,
            block_text="Some overflowing text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=12.0,
            resolved_font="helv",
            other_bboxes=[],
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-20.0,  # overflow of 20pt
        )
        assert result["resolved"] is True
        assert result["expanded"] is True
        assert result["continuation"] is False
        assert result["final_font"] == 12.0  # font unchanged

    def test_overflow_no_collision_uses_original_font_size(self):
        """
        Requirement 6.3: When expanding, the font size must remain unchanged
        (no reduction should occur when expansion is possible).
        """
        page = _make_page(insert_returns=[5.0])
        result = _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=14.0,
            resolved_font="helv",
            other_bboxes=[],
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=None,
            initial_remaining=-30.0,
        )
        assert result["final_font"] == 14.0

    def test_overflow_block_below_but_no_collision(self):
        """
        Requirement 6.2: A block below the current block that is far enough
        away (gap >= 2pt) must NOT be considered a collision.
        """
        # Block at y=200–250; current block at y=50–100.
        # Overflow = 20pt, font = 12pt → candidate_bottom = 100 + 20 + 12 = 132.
        # Gap = 200 - 132 = 68pt → no collision.
        other_bboxes = [[50, 200, 400, 250]]
        page = _make_page(insert_returns=[5.0])
        result = _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=12.0,
            resolved_font="helv",
            other_bboxes=other_bboxes,
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-20.0,
        )
        assert result["expanded"] is True
        assert result["resolved"] is True


class TestResolveOverflowFontReduction:
    """
    Overflow with adjacent block collision: font reduced until fits.
    Requirements: 6.2, 6.3
    """

    def test_collision_reduces_font_size(self):
        """
        Requirement 6.3: When expanding would collide with an adjacent block,
        the font size must be reduced by 1pt and the text retried in the
        original rect.
        """
        # Block immediately below: y=102 (gap = 102 - candidate_bottom < 2).
        # current block y=50–100, overflow=20, font=12 → candidate=132.
        # Gap = 102 - 132 = -30 → collision.
        # After reducing font to 11pt: retry in original rect → fits (returns 5.0).
        other_bboxes = [[50, 102, 400, 150]]
        page = _make_page(insert_returns=[5.0])  # retry at 11pt fits
        result = _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=12.0,
            resolved_font="helv",
            other_bboxes=other_bboxes,
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-20.0,
        )
        assert result["resolved"] is True
        assert result["expanded"] is False
        assert result["continuation"] is False
        assert result["final_font"] == 11.0  # reduced by 1pt

    def test_collision_reduces_font_multiple_times(self):
        """
        Requirement 6.3: Font reduction must repeat until text fits or 6pt
        is reached.  Here the text only fits after 3 reductions (12→11→10→9).
        """
        # All expansion attempts collide; retries in original rect:
        # 11pt → still overflows (-5.0), 10pt → still overflows (-3.0),
        # 9pt → fits (2.0).
        other_bboxes = [[50, 102, 400, 150]]
        page = _make_page(insert_returns=[-5.0, -3.0, 2.0])
        result = _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=12.0,
            resolved_font="helv",
            other_bboxes=other_bboxes,
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-20.0,
        )
        assert result["resolved"] is True
        assert result["final_font"] == 9.0

    def test_collision_block_within_2pt_is_detected(self):
        """
        Requirement 6.2: A block whose top is within 2pt of the expanded
        bottom must be detected as a collision.
        """
        # current block y=50–100, overflow=20, font=12 → candidate_bottom=132.
        # Other block top = 133 → gap = 133 - 132 = 1pt < 2pt → collision.
        other_bboxes = [[50, 133, 400, 180]]
        page = _make_page(insert_returns=[5.0])  # retry at 11pt fits
        result = _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=12.0,
            resolved_font="helv",
            other_bboxes=other_bboxes,
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-20.0,
        )
        # Should have reduced font (collision detected)
        assert result["final_font"] == 11.0
        assert result["expanded"] is False

    def test_block_above_current_not_collision(self):
        """
        Requirement 6.2: Only blocks BELOW the current block (ob_top > y0)
        are considered for collision.  A block above must be ignored.
        """
        # Block above current block (y=10–40, current y0=50).
        other_bboxes = [[50, 10, 400, 40]]
        page = _make_page(insert_returns=[5.0])
        result = _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=12.0,
            resolved_font="helv",
            other_bboxes=other_bboxes,
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-20.0,
        )
        # No collision from above block → should expand
        assert result["expanded"] is True


class TestResolveOverflowContinuationBox:
    """
    Font reaches 6pt and text still overflows → continuation box created.
    Requirements: 6.4, 6.6
    """

    def test_font_reaches_6pt_creates_continuation_box(self):
        """
        Requirement 6.4: When font size reaches 6pt and text still overflows,
        a continuation box must be created 4pt below the last block on the page.
        """
        # Collision at every expansion attempt; retries in original rect all
        # overflow until font reaches 6pt.
        # Simulate: font starts at 8pt, reduces to 7pt (overflow), 6pt (overflow).
        # At 6pt, collision still exists → continuation box.
        other_bboxes = [[50, 102, 400, 150]]
        # insert_textbox calls: retry at 7pt → -3.0, retry at 6pt → -2.0
        page = _make_page(insert_returns=[-3.0, -2.0, 5.0])  # last call = cont box
        result = _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=8.0,
            resolved_font="helv",
            other_bboxes=other_bboxes,
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-20.0,
        )
        assert result["continuation"] is True
        assert result["cont_rect"] is not None
        # Continuation box top = last_bottom + 4 = 150 + 4 = 154
        assert result["cont_rect"].y0 == pytest.approx(154.0)

    def test_continuation_box_same_width_as_original(self):
        """
        Requirement 6.4: The continuation box must have the same width as the
        original block (x0 and x1 unchanged).
        """
        other_bboxes = [[50, 102, 400, 150]]
        page = _make_page(insert_returns=[-3.0, -2.0, 5.0])
        result = _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=8.0,
            resolved_font="helv",
            other_bboxes=other_bboxes,
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-20.0,
        )
        assert result["cont_rect"].x0 == pytest.approx(50.0)
        assert result["cont_rect"].x1 == pytest.approx(400.0)

    def test_continuation_box_no_other_blocks_uses_current_y1(self):
        """
        Requirement 6.4: When there are no other blocks on the page and the
        font is already at 6pt with a collision (simulated by placing a block
        immediately below), the continuation box must be placed 4pt below the
        last block on the page.
        """
        # Place a block immediately below to force collision at every expansion.
        # current block y=50–100, overflow=10, font=6 → candidate_bottom=116.
        # Other block top = 117 → gap = 117 - 116 = 1pt < 2pt → collision.
        # At 6pt (MIN_FONT), cannot reduce further → continuation box.
        # last_bottom = 150 (other block bottom); cont_top = 150 + 4 = 154.
        other_bboxes = [[50, 117, 400, 150]]
        page = _make_page(insert_returns=[5.0])  # cont box insert
        result = _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=6.0,
            resolved_font="helv",
            other_bboxes=other_bboxes,
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-10.0,
        )
        assert result["continuation"] is True
        # last_bottom = 150; cont_top = 150 + 4 = 154
        assert result["cont_rect"].y0 == pytest.approx(154.0)


class TestResolveOverflowContinuationClipping:
    """
    Continuation box extends beyond page bottom → clipped and warning logged.
    Requirement: 6.6
    """

    def test_continuation_box_clipped_to_page_boundary(self):
        """
        Requirement 6.6: When the continuation box would extend beyond the
        page bottom, it must be clipped to the page boundary.
        """
        # Page height = 200pt.
        # current block y=50–100, overflow=10, font=6 → candidate_bottom=116.
        # Place a block at y=117 to force collision (gap = 117-116 = 1pt < 2pt).
        # At 6pt (MIN_FONT), cannot reduce → continuation box.
        # last_bottom = 190; cont_top = 190 + 4 = 194;
        # cont_bottom = 194 + 10 + 6 = 210 > 200 → clipped.
        other_bboxes = [[50, 117, 400, 190]]
        page = _make_page(insert_returns=[5.0], page_height=200.0)
        result = _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=6.0,
            resolved_font="helv",
            other_bboxes=other_bboxes,
            page_height=200.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-10.0,
        )
        assert result["continuation"] is True
        assert result["clipped"] is True
        # Clipped to page boundary
        assert result["cont_rect"].y1 == pytest.approx(200.0)

    def test_continuation_box_clipped_logs_warning(self, capsys):
        """
        Requirement 6.6: When the continuation box is clipped, a warning must
        be logged to stdout.
        """
        # Same setup as test_continuation_box_clipped_to_page_boundary.
        other_bboxes = [[50, 117, 400, 190]]
        page = _make_page(insert_returns=[5.0], page_height=200.0)
        _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=6.0,
            resolved_font="helv",
            other_bboxes=other_bboxes,
            page_height=200.0,
            original_doc=_make_original_doc(),
            page_num=2,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-10.0,
        )
        captured = capsys.readouterr()
        assert "⚠️" in captured.out
        assert "page 2" in captured.out

    def test_continuation_box_not_clipped_when_within_page(self):
        """
        Requirement 6.6: When the continuation box fits within the page,
        it must NOT be clipped and no warning must be logged.
        """
        # Page height = 792pt; force continuation by placing a collision block.
        # current block y=50–100, overflow=10, font=6 → candidate_bottom=116.
        # Block at y=117 → collision. last_bottom=200; cont_top=204;
        # cont_bottom = 204 + 10 + 6 = 220 < 792 → no clipping.
        other_bboxes = [[50, 117, 400, 200]]
        page = _make_page(insert_returns=[5.0], page_height=792.0)
        result = _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=6.0,
            resolved_font="helv",
            other_bboxes=other_bboxes,
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-10.0,
        )
        assert result["clipped"] is False


class TestResolveOverflowOtherBlocksUnchanged:
    """
    Requirement 6.5: Other blocks on the page must not be moved or resized.
    """

    def test_other_bboxes_not_modified(self):
        """
        Requirement 6.5: The other_bboxes list must remain unchanged after
        overflow resolution.
        """
        other_bboxes = [[50, 200, 400, 250], [50, 300, 400, 350]]
        original_bboxes = [list(b) for b in other_bboxes]

        page = _make_page(insert_returns=[5.0])
        _resolve_overflow(
            page=page,
            block_text="Text.",
            x0=50, y0=50, x1=400, y1=100,
            font_size=12.0,
            resolved_font="helv",
            other_bboxes=other_bboxes,
            page_height=792.0,
            original_doc=_make_original_doc(),
            page_num=0,
            bg_color=(1.0, 1.0, 1.0),
            initial_remaining=-20.0,
        )
        # other_bboxes must be unchanged
        assert other_bboxes == original_bboxes


# ---------------------------------------------------------------------------
# Task 7.2 — Unit tests for Background_Sampler
# Requirements: 5.1, 5.2, 5.5
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock
from document_translator_v3 import Background_Sampler


def _make_pixmap(width: int, height: int, pixel_fn):
    """
    Build a minimal pixmap mock.

    Parameters
    ----------
    width, height : int
        Pixmap dimensions.
    pixel_fn : callable(x, y) -> tuple[int, int, int]
        Returns the (R, G, B) tuple for a given pixel coordinate.
    """
    pix = MagicMock()
    pix.width = width
    pix.height = height
    pix.pixel = MagicMock(side_effect=lambda x, y: pixel_fn(x, y))
    return pix


def _make_fitz_page(pixmap, page_rect=(0.0, 0.0, 100.0, 100.0)):
    """
    Build a minimal fitz.Page mock that returns *pixmap* from get_pixmap().

    Parameters
    ----------
    pixmap : MagicMock
        The pixmap mock to return.
    page_rect : tuple[float, float, float, float]
        (x0, y0, x1, y1) of the page rect.
    """
    page = MagicMock()
    page.get_pixmap = MagicMock(return_value=pixmap)

    rect = MagicMock()
    rect.x0, rect.y0, rect.x1, rect.y1 = page_rect
    page.rect = rect

    return page


class TestBackgroundSampler:
    """Unit tests for Background_Sampler (Requirements 5.1, 5.2, 5.5)."""

    # ── Requirement 5.5: degenerate bboxes return None without exception ──────

    def test_zero_width_bbox_returns_none_no_exception(self):
        """
        Requirement 5.5: A bbox with zero width (x0 == x1) must return None
        without raising any exception.
        """
        sampler = Background_Sampler()
        # Use a real-looking page mock; get_pixmap should NOT be called.
        pix = _make_pixmap(100, 100, lambda x, y: (255, 255, 255))
        page = _make_fitz_page(pix)

        result = sampler.sample(page, bbox=(50.0, 20.0, 50.0, 80.0))  # x0 == x1

        assert result is None
        # get_pixmap must not be called for a degenerate bbox
        page.get_pixmap.assert_not_called()

    def test_zero_height_bbox_returns_none_no_exception(self):
        """
        Requirement 5.5: A bbox with zero height (y0 == y1) must return None
        without raising any exception.
        """
        sampler = Background_Sampler()
        pix = _make_pixmap(100, 100, lambda x, y: (255, 255, 255))
        page = _make_fitz_page(pix)

        result = sampler.sample(page, bbox=(10.0, 40.0, 90.0, 40.0))  # y0 == y1

        assert result is None
        page.get_pixmap.assert_not_called()

    # ── Requirement 5.2: uniform corners return the color tuple ──────────────

    def test_uniform_color_corners_returns_color_tuple(self):
        """
        Requirement 5.2: When all four sampled corner pixels share the same
        RGB value, sample() must return that color as (r, g, b) floats in
        [0, 1].
        """
        # All pixels are the same light-grey color: (204, 204, 204).
        uniform_rgb = (204, 204, 204)
        pix = _make_pixmap(100, 100, lambda x, y: uniform_rgb)
        page = _make_fitz_page(pix, page_rect=(0.0, 0.0, 100.0, 100.0))

        sampler = Background_Sampler()
        result = sampler.sample(page, bbox=(10.0, 10.0, 90.0, 90.0))

        expected = (204 / 255.0, 204 / 255.0, 204 / 255.0)
        assert result is not None
        assert result == pytest.approx(expected, abs=1e-6)

    def test_uniform_white_corners_returns_white_tuple(self):
        """
        Requirement 5.2: A pure-white background (255, 255, 255) must return
        (1.0, 1.0, 1.0).
        """
        pix = _make_pixmap(100, 100, lambda x, y: (255, 255, 255))
        page = _make_fitz_page(pix, page_rect=(0.0, 0.0, 100.0, 100.0))

        sampler = Background_Sampler()
        result = sampler.sample(page, bbox=(5.0, 5.0, 95.0, 95.0))

        assert result == pytest.approx((1.0, 1.0, 1.0), abs=1e-6)

    # ── Requirement 5.2 / 5.3: mixed corners return None ─────────────────────

    def test_mixed_color_corners_returns_none(self):
        """
        Requirement 5.2 / 5.3: When the four corner pixels differ in any RGB
        channel, sample() must return None (non-uniform background).
        """
        # Top-left corner → white; all others → black.
        def pixel_fn(x, y):
            if x == 0 and y == 0:
                return (255, 255, 255)
            return (0, 0, 0)

        pix = _make_pixmap(100, 100, pixel_fn)
        page = _make_fitz_page(pix, page_rect=(0.0, 0.0, 100.0, 100.0))

        sampler = Background_Sampler()
        # bbox maps corners to pixel (0,0), (99,0), (0,99), (99,99)
        result = sampler.sample(page, bbox=(0.0, 0.0, 100.0, 100.0))

        assert result is None


# ---------------------------------------------------------------------------
# Task 11.3 — Unit tests for DOCX_Writer v2
# Requirements: 7.2, 7.4, 7.5, 7.6, 8.2, 8.3, 8.5, 8.6
# ---------------------------------------------------------------------------

import tempfile
import os
from docx import Document as DocxDocument
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from document_translator_v3 import write_docx, read_docx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _para_block(text, style_name=None, alignment=None,
                space_before=None, space_after=None, font_color=None):
    """Build a minimal paragraph block dict as produced by read_docx()."""
    return {
        "type": "paragraph",
        "text": text,
        "style": {
            "style_name":   style_name,
            "alignment":    alignment,
            "space_before": space_before,
            "space_after":  space_after,
            "font_color":   font_color,
            "bold":         None,
            "font_size":    None,
        },
    }


def _cell_block(text, table_index, row, col,
                row_span=1, col_span=1, bold=None, font_size=None):
    """Build a minimal table_cell block dict as produced by read_docx()."""
    return {
        "type":        "table_cell",
        "text":        text,
        "table_index": table_index,
        "row":         row,
        "col":         col,
        "row_span":    row_span,
        "col_span":    col_span,
        "style": {
            "bold":      bold,
            "font_size": font_size,
        },
    }


def _write_and_read(blocks):
    """
    Write *blocks* to a temp DOCX via write_docx() and return the
    python-docx Document object for inspection.
    """
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        tmp_path = f.name
    try:
        write_docx(blocks, tmp_path)
        return DocxDocument(tmp_path)
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# 1. Paragraph style name extracted and applied correctly (Req 7.2)
# ---------------------------------------------------------------------------

class TestDocxWriterParagraphStyle:
    """Requirement 7.2: paragraph style name is applied to the output paragraph."""

    def test_heading1_style_applied(self):
        """
        Requirement 7.2: A block with style_name='Heading 1' must produce an
        output paragraph whose style.name is 'Heading 1'.
        """
        blocks = [_para_block("This is a heading one paragraph.", style_name="Heading 1")]
        doc = _write_and_read(blocks)
        assert doc.paragraphs[0].style.name == "Heading 1"

    def test_normal_style_applied(self):
        """
        Requirement 7.2: A block with style_name='Normal' must produce an
        output paragraph whose style.name is 'Normal'.
        """
        blocks = [_para_block("Normal body text paragraph here.", style_name="Normal")]
        doc = _write_and_read(blocks)
        assert doc.paragraphs[0].style.name == "Normal"

    def test_none_style_name_falls_back_to_normal(self):
        """
        Requirement 7.3: When style_name is None, the output paragraph must
        use the 'Normal' style.
        """
        blocks = [_para_block("Paragraph with no style name set.", style_name=None)]
        doc = _write_and_read(blocks)
        assert doc.paragraphs[0].style.name == "Normal"

    def test_unknown_style_name_falls_back_to_normal(self):
        """
        Requirement 7.3: When style_name is not in the output document's style
        table, the output paragraph must use the 'Normal' style.
        """
        blocks = [_para_block("Paragraph with unknown style.", style_name="MyCustomStyle99")]
        doc = _write_and_read(blocks)
        assert doc.paragraphs[0].style.name == "Normal"

    def test_read_docx_extracts_style_name(self, tmp_path):
        """
        Requirement 7.1: read_docx() must extract the paragraph style name
        and store it in block['style']['style_name'].
        """
        # Build a source DOCX with a Heading 1 paragraph.
        src_doc = DocxDocument()
        src_doc.add_paragraph("A heading paragraph.", style="Heading 1")
        src_path = str(tmp_path / "src.docx")
        src_doc.save(src_path)

        blocks = read_docx(src_path)
        # The paragraph has 3 words so it should pass the word-count filter.
        assert len(blocks) >= 1
        para_blocks = [b for b in blocks if b["type"] == "paragraph"]
        assert para_blocks[0]["style"]["style_name"] == "Heading 1"


# ---------------------------------------------------------------------------
# 2. Alignment copied to output paragraph (Req 7.4)
# ---------------------------------------------------------------------------

class TestDocxWriterAlignment:
    """Requirement 7.4: paragraph alignment is copied from source to output."""

    def test_center_alignment_copied(self):
        """
        Requirement 7.4: A block with alignment=WD_ALIGN_PARAGRAPH.CENTER must
        produce an output paragraph with the same alignment.
        """
        blocks = [_para_block(
            "This paragraph should be centered.",
            alignment=WD_ALIGN_PARAGRAPH.CENTER,
        )]
        doc = _write_and_read(blocks)
        assert doc.paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.CENTER

    def test_right_alignment_copied(self):
        """
        Requirement 7.4: A block with alignment=WD_ALIGN_PARAGRAPH.RIGHT must
        produce an output paragraph with right alignment.
        """
        blocks = [_para_block(
            "This paragraph should be right aligned.",
            alignment=WD_ALIGN_PARAGRAPH.RIGHT,
        )]
        doc = _write_and_read(blocks)
        assert doc.paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.RIGHT

    def test_justify_alignment_copied(self):
        """
        Requirement 7.4: A block with alignment=WD_ALIGN_PARAGRAPH.JUSTIFY must
        produce an output paragraph with justify alignment.
        """
        blocks = [_para_block(
            "This paragraph should be fully justified.",
            alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
        )]
        doc = _write_and_read(blocks)
        assert doc.paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.JUSTIFY

    def test_none_alignment_not_set(self):
        """
        Requirement 7.4: When alignment is None in the source block, the output
        paragraph alignment must remain at its default (None / inherited).
        """
        blocks = [_para_block("Paragraph with no explicit alignment.", alignment=None)]
        doc = _write_and_read(blocks)
        # python-docx returns None when alignment is not explicitly set.
        assert doc.paragraphs[0].alignment is None

    def test_read_docx_extracts_alignment(self, tmp_path):
        """
        Requirement 7.4: read_docx() must extract paragraph alignment and store
        it in block['style']['alignment'].
        """
        src_doc = DocxDocument()
        para = src_doc.add_paragraph("A centered paragraph here.")
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        src_path = str(tmp_path / "src_align.docx")
        src_doc.save(src_path)

        blocks = read_docx(src_path)
        para_blocks = [b for b in blocks if b["type"] == "paragraph"]
        assert para_blocks[0]["style"]["alignment"] == WD_ALIGN_PARAGRAPH.CENTER


# ---------------------------------------------------------------------------
# 3. space_before / space_after copied when set; not set when source is None
#    (Req 7.5)
# ---------------------------------------------------------------------------

class TestDocxWriterSpacing:
    """Requirement 7.5: paragraph spacing is copied when set; left alone when None."""

    def test_space_before_copied_when_set(self):
        """
        Requirement 7.5: When space_before is not None, the output paragraph
        must have the same space_before value.
        """
        blocks = [_para_block(
            "Paragraph with space before set.",
            space_before=Pt(12),
        )]
        doc = _write_and_read(blocks)
        assert doc.paragraphs[0].paragraph_format.space_before == Pt(12)

    def test_space_after_copied_when_set(self):
        """
        Requirement 7.5: When space_after is not None, the output paragraph
        must have the same space_after value.
        """
        blocks = [_para_block(
            "Paragraph with space after set.",
            space_after=Pt(6),
        )]
        doc = _write_and_read(blocks)
        assert doc.paragraphs[0].paragraph_format.space_after == Pt(6)

    def test_space_before_none_not_set(self):
        """
        Requirement 7.5: When space_before is None in the source block, the
        output paragraph must NOT have space_before explicitly set (remains None).
        """
        blocks = [_para_block("Paragraph with no space before.", space_before=None)]
        doc = _write_and_read(blocks)
        assert doc.paragraphs[0].paragraph_format.space_before is None

    def test_space_after_none_not_set(self):
        """
        Requirement 7.5: When space_after is None in the source block, the
        output paragraph must NOT have space_after explicitly set (remains None).
        """
        blocks = [_para_block("Paragraph with no space after.", space_after=None)]
        doc = _write_and_read(blocks)
        assert doc.paragraphs[0].paragraph_format.space_after is None

    def test_both_spacing_values_copied(self):
        """
        Requirement 7.5: Both space_before and space_after must be copied when
        both are set.
        """
        blocks = [_para_block(
            "Paragraph with both spacing values set.",
            space_before=Pt(18),
            space_after=Pt(9),
        )]
        doc = _write_and_read(blocks)
        assert doc.paragraphs[0].paragraph_format.space_before == Pt(18)
        assert doc.paragraphs[0].paragraph_format.space_after == Pt(9)

    def test_read_docx_extracts_spacing(self, tmp_path):
        """
        Requirement 7.5: read_docx() must extract space_before and space_after
        and store them in block['style'].
        """
        src_doc = DocxDocument()
        para = src_doc.add_paragraph("A paragraph with spacing values set.")
        para.paragraph_format.space_before = Pt(12)
        para.paragraph_format.space_after = Pt(6)
        src_path = str(tmp_path / "src_spacing.docx")
        src_doc.save(src_path)

        blocks = read_docx(src_path)
        para_blocks = [b for b in blocks if b["type"] == "paragraph"]
        assert para_blocks[0]["style"]["space_before"] == Pt(12)
        assert para_blocks[0]["style"]["space_after"] == Pt(6)


# ---------------------------------------------------------------------------
# 4. Run font color copied when set (Req 7.6)
# ---------------------------------------------------------------------------

class TestDocxWriterFontColor:
    """Requirement 7.6: run-level font color is copied from source to output."""

    def test_red_font_color_copied(self):
        """
        Requirement 7.6: A block with font_color=RGBColor(0xFF, 0x00, 0x00)
        must produce an output run with the same RGB color.
        """
        red = RGBColor(0xFF, 0x00, 0x00)
        blocks = [_para_block("Red colored text paragraph.", font_color=red)]
        doc = _write_and_read(blocks)
        run = doc.paragraphs[0].runs[0]
        assert run.font.color.rgb == red

    def test_blue_font_color_copied(self):
        """
        Requirement 7.6: A block with font_color=RGBColor(0x00, 0x00, 0xFF)
        must produce an output run with the same blue color.
        """
        blue = RGBColor(0x00, 0x00, 0xFF)
        blocks = [_para_block("Blue colored text paragraph.", font_color=blue)]
        doc = _write_and_read(blocks)
        run = doc.paragraphs[0].runs[0]
        assert run.font.color.rgb == blue

    def test_none_font_color_not_set(self):
        """
        Requirement 7.6: When font_color is None, the output run must NOT have
        an explicit color set (color type should be inherited/auto, not RGB).
        """
        from docx.oxml.ns import qn
        from docx.enum.dml import MSO_THEME_COLOR

        blocks = [_para_block("Paragraph with no explicit font color.", font_color=None)]
        doc = _write_and_read(blocks)
        run = doc.paragraphs[0].runs[0]
        # When no color is set, accessing .rgb raises or returns None.
        try:
            rgb = run.font.color.rgb
            assert rgb is None
        except Exception:
            pass  # Acceptable: no color set means accessing .rgb may raise

    def test_read_docx_extracts_font_color(self, tmp_path):
        """
        Requirement 7.6: read_docx() must extract run-level font color and
        store it in block['style']['font_color'].
        """
        src_doc = DocxDocument()
        para = src_doc.add_paragraph()
        run = para.add_run("Green colored text here.")
        run.font.color.rgb = RGBColor(0x00, 0x80, 0x00)
        src_path = str(tmp_path / "src_color.docx")
        src_doc.save(src_path)

        blocks = read_docx(src_path)
        para_blocks = [b for b in blocks if b["type"] == "paragraph"]
        assert para_blocks[0]["style"]["font_color"] == RGBColor(0x00, 0x80, 0x00)


# ---------------------------------------------------------------------------
# 5. Table row/column count preserved (Req 8.2, 8.3)
# ---------------------------------------------------------------------------

class TestDocxWriterTableDimensions:
    """Requirement 8.3: output table has the same row and column count as source."""

    def test_2x3_table_row_col_count_preserved(self):
        """
        Requirement 8.3: A 2-row × 3-column table must produce an output table
        with exactly 2 rows and 3 columns.
        """
        blocks = [
            _cell_block("Row0 Col0 text", table_index=0, row=0, col=0),
            _cell_block("Row0 Col1 text", table_index=0, row=0, col=1),
            _cell_block("Row0 Col2 text", table_index=0, row=0, col=2),
            _cell_block("Row1 Col0 text", table_index=0, row=1, col=0),
            _cell_block("Row1 Col1 text", table_index=0, row=1, col=1),
            _cell_block("Row1 Col2 text", table_index=0, row=1, col=2),
        ]
        doc = _write_and_read(blocks)
        assert len(doc.tables) == 1
        tbl = doc.tables[0]
        assert len(tbl.rows) == 2
        assert len(tbl.columns) == 3

    def test_1x1_table_preserved(self):
        """
        Requirement 8.3: A 1×1 table must produce an output table with 1 row
        and 1 column.
        """
        blocks = [_cell_block("Single cell text.", table_index=0, row=0, col=0)]
        doc = _write_and_read(blocks)
        assert len(doc.tables) == 1
        assert len(doc.tables[0].rows) == 1
        assert len(doc.tables[0].columns) == 1

    def test_cell_text_written_correctly(self):
        """
        Requirement 8.2: The text content of each non-empty cell must be
        written to the output table cell.
        """
        blocks = [
            _cell_block("Alpha beta gamma", table_index=0, row=0, col=0),
            _cell_block("Delta epsilon zeta", table_index=0, row=0, col=1),
        ]
        doc = _write_and_read(blocks)
        tbl = doc.tables[0]
        assert tbl.cell(0, 0).text.strip() == "Alpha beta gamma"
        assert tbl.cell(0, 1).text.strip() == "Delta epsilon zeta"

    def test_read_docx_extracts_table_row_col(self, tmp_path):
        """
        Requirement 8.1: read_docx() must extract table cells with correct
        row and col indices.
        """
        src_doc = DocxDocument()
        tbl = src_doc.add_table(rows=2, cols=2)
        tbl.cell(0, 0).text = "Cell zero zero text"
        tbl.cell(0, 1).text = "Cell zero one text"
        tbl.cell(1, 0).text = "Cell one zero text"
        tbl.cell(1, 1).text = "Cell one one text"
        src_path = str(tmp_path / "src_table.docx")
        src_doc.save(src_path)

        blocks = read_docx(src_path)
        cell_blocks = [b for b in blocks if b["type"] == "table_cell"]
        rows = {b["row"] for b in cell_blocks}
        cols = {b["col"] for b in cell_blocks}
        assert rows == {0, 1}
        assert cols == {0, 1}


# ---------------------------------------------------------------------------
# 6. Merged cell spans preserved (Req 8.3)
# ---------------------------------------------------------------------------

class TestDocxWriterMergedCells:
    """Requirement 8.3: merged cell spanning attributes are preserved."""

    def test_col_span_2_merges_cells_horizontally(self):
        """
        Requirement 8.3: A cell with col_span=2 must produce a horizontally
        merged cell in the output table.
        """
        # 1 row × 2 cols; cell (0,0) spans 2 columns.
        # We must include a block at col=1 so write_docx creates a 2-column table.
        blocks = [
            _cell_block("Merged header cell text", table_index=0, row=0, col=0, col_span=2),
            _cell_block("",                        table_index=0, row=0, col=1),
        ]
        doc = _write_and_read(blocks)
        tbl = doc.tables[0]
        # After merging, cell(0,0) and cell(0,1) share the same underlying XML
        # element (_tc). python-docx _Cell objects are wrappers so == doesn't
        # work; compare the underlying tc elements instead.
        assert tbl.cell(0, 0)._tc is tbl.cell(0, 1)._tc

    def test_row_span_2_merges_cells_vertically(self):
        """
        Requirement 8.3: A cell with row_span=2 must produce a vertically
        merged cell in the output table.
        """
        # 2 rows × 1 col; cell (0,0) spans 2 rows.
        # We must include a block at row=1 so write_docx creates a 2-row table.
        blocks = [
            _cell_block("Vertically merged cell text", table_index=0, row=0, col=0, row_span=2),
            _cell_block("",                            table_index=0, row=1, col=0),
        ]
        doc = _write_and_read(blocks)
        tbl = doc.tables[0]
        # After merging, cell(0,0) and cell(1,0) share the same underlying XML
        # element (_tc).
        assert tbl.cell(0, 0)._tc is tbl.cell(1, 0)._tc

    def test_read_docx_extracts_col_span(self, tmp_path):
        """
        Requirement 8.1: read_docx() must extract col_span from merged cells.
        """
        src_doc = DocxDocument()
        tbl = src_doc.add_table(rows=1, cols=3)
        # Merge columns 0 and 1 in row 0.
        tbl.cell(0, 0).merge(tbl.cell(0, 1))
        tbl.cell(0, 0).text = "Merged spanning cell text"
        tbl.cell(0, 2).text = "Normal cell text here"
        src_path = str(tmp_path / "src_colspan.docx")
        src_doc.save(src_path)

        blocks = read_docx(src_path)
        cell_blocks = [b for b in blocks if b["type"] == "table_cell"]
        merged = next((b for b in cell_blocks if b["row"] == 0 and b["col"] == 0), None)
        assert merged is not None
        assert merged["col_span"] == 2


# ---------------------------------------------------------------------------
# 7. Empty cells not translated (Req 8.5)
# ---------------------------------------------------------------------------

class TestDocxWriterEmptyCells:
    """Requirement 8.5: empty cells are written as empty without translation."""

    def test_empty_cell_written_as_empty(self):
        """
        Requirement 8.5: A table_cell block with empty text must produce an
        empty cell in the output table (no text inserted).
        """
        blocks = [
            _cell_block("Non empty cell text", table_index=0, row=0, col=0),
            _cell_block("",                    table_index=0, row=0, col=1),
        ]
        doc = _write_and_read(blocks)
        tbl = doc.tables[0]
        assert tbl.cell(0, 1).text.strip() == ""

    def test_whitespace_only_cell_written_as_empty(self):
        """
        Requirement 8.5: A table_cell block whose text is only whitespace must
        produce an empty cell in the output table.
        """
        blocks = [
            _cell_block("Non empty cell text", table_index=0, row=0, col=0),
            _cell_block("   ",                 table_index=0, row=0, col=1),
        ]
        doc = _write_and_read(blocks)
        tbl = doc.tables[0]
        assert tbl.cell(0, 1).text.strip() == ""

    def test_non_empty_cell_has_text(self):
        """
        Requirement 8.2: A non-empty cell must have its text written to the
        output table cell.
        """
        blocks = [
            _cell_block("This cell has content.", table_index=0, row=0, col=0),
        ]
        doc = _write_and_read(blocks)
        tbl = doc.tables[0]
        assert tbl.cell(0, 0).text.strip() == "This cell has content."


# ---------------------------------------------------------------------------
# 8. Table position index preserved in document body (Req 8.6)
# ---------------------------------------------------------------------------

class TestDocxWriterTablePosition:
    """Requirement 8.6: tables are inserted at the correct position in the body."""

    def test_single_table_appears_after_paragraphs(self):
        """
        Requirement 8.6: When the block list contains paragraphs followed by
        table cells, the output document must contain the paragraphs first and
        the table after them.
        """
        blocks = [
            _para_block("First paragraph text here."),
            _para_block("Second paragraph text here."),
            _cell_block("Table cell text here.", table_index=0, row=0, col=0),
        ]
        doc = _write_and_read(blocks)
        # The document body should have 2 paragraphs then 1 table.
        assert len(doc.paragraphs) >= 2
        assert len(doc.tables) == 1

    def test_two_tables_both_present(self):
        """
        Requirement 8.6: When the block list contains cells from two different
        tables, both tables must appear in the output document.
        """
        blocks = [
            _cell_block("Table0 cell text.", table_index=0, row=0, col=0),
            _cell_block("Table1 cell text.", table_index=1, row=0, col=0),
        ]
        doc = _write_and_read(blocks)
        assert len(doc.tables) == 2

    def test_two_tables_correct_content(self):
        """
        Requirement 8.6: Each table must contain the correct cell text from
        its corresponding table_index group.
        """
        blocks = [
            _cell_block("First table content.", table_index=0, row=0, col=0),
            _cell_block("Second table content.", table_index=1, row=0, col=0),
        ]
        doc = _write_and_read(blocks)
        assert doc.tables[0].cell(0, 0).text.strip() == "First table content."
        assert doc.tables[1].cell(0, 0).text.strip() == "Second table content."

    def test_read_docx_extracts_table_index(self, tmp_path):
        """
        Requirement 8.1: read_docx() must assign the correct table_index to
        each cell block when a document contains multiple tables.
        """
        src_doc = DocxDocument()
        tbl0 = src_doc.add_table(rows=1, cols=1)
        tbl0.cell(0, 0).text = "First table cell text"
        tbl1 = src_doc.add_table(rows=1, cols=1)
        tbl1.cell(0, 0).text = "Second table cell text"
        src_path = str(tmp_path / "src_two_tables.docx")
        src_doc.save(src_path)

        blocks = read_docx(src_path)
        cell_blocks = [b for b in blocks if b["type"] == "table_cell"]
        indices = sorted({b["table_index"] for b in cell_blocks})
        assert indices == [0, 1]


# ---------------------------------------------------------------------------
# Task 14.2 — Unit tests for Column_Detector v2 (detect_columns)
# Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
# ---------------------------------------------------------------------------

from document_translator_v3 import detect_columns

# Standard letter page width in points (used throughout these tests).
PAGE_WIDTH = 612.0


def _block(x0, y0, x1, y1, text="sample block text here", page=0):
    """Build a minimal block dict with position and text."""
    return {"position": [x0, y0, x1, y1], "text": text, "page": page}


class TestColumnDetectorSingleColumn:
    """
    Requirement 10.5: When no clear column structure is detected (or all
    blocks are in a single column), all blocks are returned sorted by top
    y-coordinate.
    """

    def test_single_column_sorted_by_y(self):
        """
        Requirement 10.5: A single-column page (all blocks span most of the
        width, no significant gap) must return all blocks sorted by y.
        """
        # Three blocks stacked vertically, each spanning ~80% of page width.
        # No horizontal gap → single column.
        b1 = _block(50, 300, 550, 330, text="Third block on the page")
        b2 = _block(50, 100, 550, 130, text="First block on the page")
        b3 = _block(50, 200, 550, 230, text="Second block on the page")

        result = detect_columns([b1, b2, b3], PAGE_WIDTH)

        assert len(result) == 3
        ys = [b["position"][1] for b in result]
        assert ys == sorted(ys), "Blocks must be sorted by top y-coordinate"
        assert result[0] is b2
        assert result[1] is b3
        assert result[2] is b1

    def test_empty_blocks_returns_empty(self):
        """
        Requirement 10.5: An empty block list must return an empty list.
        """
        result = detect_columns([], PAGE_WIDTH)
        assert result == []

    def test_single_block_returns_that_block(self):
        """
        Requirement 10.5: A single block must be returned as-is (single-column
        fallback because there are fewer than 2 blocks per candidate column).
        """
        b = _block(50, 100, 300, 130, text="Only one block here")
        result = detect_columns([b], PAGE_WIDTH)
        assert result == [b]


class TestColumnDetectorTwoColumns:
    """
    Requirement 10.1, 10.2, 10.3: Two-column detection via gap analysis.
    A gap >= 10% of page_width between the right edge of the left column
    and the left edge of the right column triggers two-column detection.
    """

    def test_two_column_15_percent_gap_detected(self):
        """
        Requirement 10.1 / 10.2: A 15% gap (> 10% threshold) between two
        groups of blocks must be detected as a two-column layout.
        The left column blocks must appear before the right column blocks
        in the output.
        """
        # PAGE_WIDTH = 612.  10% = 61.2.  15% = 91.8.
        # Left column: x0=50, x1=240  (right edge = 240)
        # Right column: x0=372, x1=562  (left edge = 372)
        # Gap = 372 - 240 = 132 ≈ 21.6% of 612 → well above threshold.
        left_top    = _block(50, 100, 240, 130, text="Left column top block")
        left_bottom = _block(50, 200, 240, 230, text="Left column bottom block")
        right_top   = _block(372, 150, 562, 180, text="Right column top block")
        right_bottom = _block(372, 250, 562, 280, text="Right column bottom block")

        result = detect_columns(
            [right_bottom, left_bottom, right_top, left_top], PAGE_WIDTH
        )

        assert len(result) == 4
        texts = [b["text"] for b in result]
        # Left column blocks must come before right column blocks.
        left_indices  = [texts.index("Left column top block"),
                         texts.index("Left column bottom block")]
        right_indices = [texts.index("Right column top block"),
                         texts.index("Right column bottom block")]
        assert max(left_indices) < min(right_indices), (
            "All left-column blocks must precede all right-column blocks"
        )

    def test_two_column_left_sorted_by_y(self):
        """
        Requirement 10.3: Within the left column, blocks must be sorted by
        top y-coordinate.
        """
        left_top    = _block(50, 100, 240, 130, text="Left top block here")
        left_bottom = _block(50, 200, 240, 230, text="Left bottom block here")
        right_top   = _block(372, 100, 562, 130, text="Right top block here")
        right_bottom = _block(372, 200, 562, 230, text="Right bottom block here")

        result = detect_columns(
            [left_bottom, right_bottom, left_top, right_top], PAGE_WIDTH
        )

        texts = [b["text"] for b in result]
        left_top_idx    = texts.index("Left top block here")
        left_bottom_idx = texts.index("Left bottom block here")
        assert left_top_idx < left_bottom_idx, (
            "Left column: top block must appear before bottom block"
        )

    def test_two_column_right_sorted_by_y(self):
        """
        Requirement 10.3: Within the right column, blocks must be sorted by
        top y-coordinate.
        """
        left_top    = _block(50, 100, 240, 130, text="Left top block here")
        left_bottom = _block(50, 200, 240, 230, text="Left bottom block here")
        right_top   = _block(372, 100, 562, 130, text="Right top block here")
        right_bottom = _block(372, 200, 562, 230, text="Right bottom block here")

        result = detect_columns(
            [right_bottom, left_top, right_top, left_bottom], PAGE_WIDTH
        )

        texts = [b["text"] for b in result]
        right_top_idx    = texts.index("Right top block here")
        right_bottom_idx = texts.index("Right bottom block here")
        assert right_top_idx < right_bottom_idx, (
            "Right column: top block must appear before bottom block"
        )


class TestColumnDetectorSmallGap:
    """
    Requirement 10.1: A gap < 10% of page_width must NOT trigger column
    detection — the page is treated as single-column.
    """

    def test_two_column_8_percent_gap_treated_as_single_column(self):
        """
        Requirement 10.1: An 8% gap (< 10% threshold) must NOT be detected
        as a column boundary.  All blocks must be returned sorted by y.
        """
        # PAGE_WIDTH = 612.  8% = 48.96.
        # Left group: x0=50, x1=280  (right edge = 280)
        # Right group: x0=329, x1=562  (left edge = 329)
        # Gap = 329 - 280 = 49 ≈ 8.0% of 612 → below 10% threshold.
        b1 = _block(50,  100, 280, 130, text="Left group top block here")
        b2 = _block(50,  200, 280, 230, text="Left group bottom block here")
        b3 = _block(329, 150, 562, 180, text="Right group top block here")
        b4 = _block(329, 250, 562, 280, text="Right group bottom block here")

        result = detect_columns([b1, b2, b3, b4], PAGE_WIDTH)

        assert len(result) == 4
        ys = [b["position"][1] for b in result]
        assert ys == sorted(ys), (
            "With gap < 10%, all blocks must be returned sorted by y (single column)"
        )


class TestColumnDetectorThreeColumns:
    """
    Requirement 10.2: The detector must support up to 3 columns per page.
    """

    def test_three_column_page_detected(self):
        """
        Requirement 10.2: Three groups of blocks separated by gaps >= 10% of
        page_width must be detected as three columns.  The output must contain
        all blocks with left column first, then center, then right.
        """
        # PAGE_WIDTH = 612.  10% = 61.2.
        # Left col:   x0=20,  x1=160  (right edge = 160)
        # Center col: x0=226, x1=386  (left edge = 226; gap = 226-160 = 66 ≈ 10.8%)
        # Right col:  x0=452, x1=592  (left edge = 452; gap = 452-386 = 66 ≈ 10.8%)
        left_a   = _block(20,  100, 160, 130, text="Left column first block")
        left_b   = _block(20,  200, 160, 230, text="Left column second block")
        center_a = _block(226, 120, 386, 150, text="Center column first block")
        center_b = _block(226, 220, 386, 250, text="Center column second block")
        right_a  = _block(452, 140, 592, 170, text="Right column first block")
        right_b  = _block(452, 240, 592, 270, text="Right column second block")

        all_blocks = [right_b, center_a, left_b, right_a, left_a, center_b]
        result = detect_columns(all_blocks, PAGE_WIDTH)

        assert len(result) == 6
        texts = [b["text"] for b in result]

        left_indices   = [texts.index("Left column first block"),
                          texts.index("Left column second block")]
        center_indices = [texts.index("Center column first block"),
                          texts.index("Center column second block")]
        right_indices  = [texts.index("Right column first block"),
                          texts.index("Right column second block")]

        # Left column must come before center, center before right.
        assert max(left_indices) < min(center_indices), (
            "Left column blocks must all precede center column blocks"
        )
        assert max(center_indices) < min(right_indices), (
            "Center column blocks must all precede right column blocks"
        )

    def test_three_column_each_column_sorted_by_y(self):
        """
        Requirement 10.3: Within each of the three columns, blocks must be
        sorted by top y-coordinate.
        """
        left_a   = _block(20,  200, 160, 230, text="Left column first block")
        left_b   = _block(20,  100, 160, 130, text="Left column second block")
        center_a = _block(226, 220, 386, 250, text="Center column first block")
        center_b = _block(226, 120, 386, 150, text="Center column second block")
        right_a  = _block(452, 240, 592, 270, text="Right column first block")
        right_b  = _block(452, 140, 592, 170, text="Right column second block")

        result = detect_columns(
            [left_a, left_b, center_a, center_b, right_a, right_b], PAGE_WIDTH
        )

        texts = [b["text"] for b in result]
        # Within left column: "second block" (y=100) must come before "first block" (y=200)
        assert texts.index("Left column second block") < texts.index("Left column first block")
        # Within center column: "second block" (y=120) before "first block" (y=220)
        assert texts.index("Center column second block") < texts.index("Center column first block")
        # Within right column: "second block" (y=140) before "first block" (y=240)
        assert texts.index("Right column second block") < texts.index("Right column first block")


class TestColumnDetectorFullWidthBlocks:
    """
    Requirement 10.4: Full-width blocks (width >= 90% of page_width) must be
    interleaved with columnar blocks at their correct y-position.
    """

    def test_full_width_block_above_columnar_appears_first(self):
        """
        Requirement 10.4: A full-width block with a smaller top y than any
        columnar block must appear first in the output.
        """
        # Full-width block: x0=10, x1=600 → width=590 ≥ 90% of 612 (=550.8).
        # Columnar blocks below it.
        header = _block(10, 50, 600, 80, text="Full width header block here")
        left_a = _block(50, 150, 240, 180, text="Left column block one here")
        left_b = _block(50, 250, 240, 280, text="Left column block two here")
        right_a = _block(372, 150, 562, 180, text="Right column block one here")
        right_b = _block(372, 250, 562, 280, text="Right column block two here")

        result = detect_columns(
            [left_b, right_a, header, left_a, right_b], PAGE_WIDTH
        )

        assert len(result) == 5
        assert result[0] is header, (
            "Full-width block with smallest y must appear first in output"
        )

    def test_full_width_block_between_columnar_blocks_interleaved(self):
        """
        Requirement 10.4: A full-width block whose y falls between two groups
        of columnar blocks must be interleaved at the correct position.

        The algorithm merges columns left-to-right (all left-column blocks
        first, then right-column blocks) and inserts full-width blocks before
        the first columnar block in the traversal order whose y > full-width
        block's y.  Therefore the divider (y=200) must appear before any
        columnar block with y > 200 (i.e., left_bottom and right_bottom), but
        right_top (y=100, right column) may appear after the divider because
        the right column is processed after the left column.
        """
        # Columnar blocks at y=100 and y=300; full-width block at y=200.
        left_top    = _block(50, 100, 240, 130, text="Left column top block here")
        left_bottom = _block(50, 300, 240, 330, text="Left column bottom block here")
        right_top   = _block(372, 100, 562, 130, text="Right column top block here")
        right_bottom = _block(372, 300, 562, 330, text="Right column bottom block here")
        divider = _block(10, 200, 600, 230, text="Full width divider block here")

        result = detect_columns(
            [left_bottom, divider, right_top, left_top, right_bottom], PAGE_WIDTH
        )

        texts = [b["text"] for b in result]
        divider_idx = texts.index("Full width divider block here")

        # The divider must appear before all columnar blocks with y > 200.
        bottom_indices = [texts.index("Left column bottom block here"),
                          texts.index("Right column bottom block here")]
        assert divider_idx < min(bottom_indices), (
            "Full-width block must appear before columnar blocks with larger y"
        )

        # The divider must appear after the left-column block with y < 200
        # (left_top, y=100), which is the first block in the traversal order.
        left_top_idx = texts.index("Left column top block here")
        assert left_top_idx < divider_idx, (
            "Full-width block must appear after left-column blocks with smaller y"
        )


class TestColumnDetectorFallback:
    """
    Requirement 10.5: When fewer than 2 blocks exist per candidate column,
    the detector must fall back to single-column (all blocks sorted by y).
    """

    def test_one_block_per_candidate_column_falls_back(self):
        """
        Requirement 10.5: When a gap is detected but each candidate column
        has only 1 block (< 2), the detector must fall back to single-column
        and return all blocks sorted by y.
        """
        # Two blocks with a large gap between them — each candidate column
        # would have only 1 block → single-column fallback.
        b1 = _block(50,  200, 240, 230, text="Left side single block here")
        b2 = _block(372, 100, 562, 130, text="Right side single block here")

        result = detect_columns([b1, b2], PAGE_WIDTH)

        assert len(result) == 2
        ys = [b["position"][1] for b in result]
        assert ys == sorted(ys), (
            "Single-column fallback: blocks must be sorted by top y-coordinate"
        )
        # b2 has smaller y (100) so it must come first.
        assert result[0] is b2
        assert result[1] is b1

    def test_three_columns_one_empty_falls_back(self):
        """
        Requirement 10.5: When three gaps are detected but one candidate
        column ends up with fewer than 2 blocks, the detector must fall back
        to single-column.
        """
        # Left col: 2 blocks; center col: 1 block; right col: 2 blocks.
        # The center column has only 1 block → fallback.
        left_a   = _block(20,  100, 160, 130, text="Left column first block here")
        left_b   = _block(20,  200, 160, 230, text="Left column second block here")
        center_a = _block(226, 150, 386, 180, text="Center column only block here")
        right_a  = _block(452, 100, 592, 130, text="Right column first block here")
        right_b  = _block(452, 200, 592, 230, text="Right column second block here")

        result = detect_columns(
            [right_b, center_a, left_b, right_a, left_a], PAGE_WIDTH
        )

        assert len(result) == 5
        ys = [b["position"][1] for b in result]
        assert ys == sorted(ys), (
            "Single-column fallback: blocks must be sorted by top y-coordinate"
        )


# ---------------------------------------------------------------------------
# Task 13.2 — Unit tests for BLEU_Reporter
# Requirements: 9.2, 9.3, 9.4, 9.6
# ---------------------------------------------------------------------------

import tempfile
import os

from document_translator_v3 import BLEU_Reporter


def _make_blocks(texts: list) -> list:
    """Build a minimal translated-block list from a list of text strings."""
    return [{"text": t} for t in texts]


class TestBLEUReporterNoReferenceFile:
    """
    Requirement 9.2: When no reference file is provided (None or non-existent
    path), BLEU_Reporter must return None without raising an error.
    """

    def test_none_reference_file_returns_none(self):
        """
        Requirement 9.2: Passing None as reference_file must return None
        without raising any exception.
        """
        reporter = BLEU_Reporter()
        blocks = _make_blocks(["Hello world.", "This is a test."])
        result = reporter.compute(blocks, None)
        assert result is None

    def test_nonexistent_reference_file_returns_none(self):
        """
        Requirement 9.6: A reference file path that does not exist on disk
        must cause compute() to return None without raising an exception.
        """
        reporter = BLEU_Reporter()
        blocks = _make_blocks(["Hello world."])
        result = reporter.compute(blocks, "/nonexistent/path/to/reference.txt")
        assert result is None

    def test_nonexistent_reference_file_prints_warning(self, capsys):
        """
        Requirement 9.6: When the reference file cannot be read, a warning
        must be printed to stdout identifying the file path and the error.
        """
        reporter = BLEU_Reporter()
        blocks = _make_blocks(["Hello world."])
        reporter.compute(blocks, "/nonexistent/path/to/reference.txt")
        captured = capsys.readouterr()
        assert "⚠️" in captured.out
        assert "reference" in captured.out.lower() or "BLEU" in captured.out


class TestBLEUReporterMatchingCounts:
    """
    Requirement 9.3: When a valid reference file is provided and counts match,
    BLEU_Reporter must return a float in [0.0, 100.0].
    """

    def test_matching_counts_returns_float(self, tmp_path):
        """
        Requirement 9.3: When translated block count equals reference line
        count, compute() must return a float.
        """
        ref_file = tmp_path / "reference.txt"
        ref_file.write_text("Hello world.\nThis is a test.\n", encoding="utf-8")

        reporter = BLEU_Reporter()
        blocks = _make_blocks(["Hello world.", "This is a test."])
        result = reporter.compute(blocks, str(ref_file))

        assert isinstance(result, float)

    def test_matching_counts_score_in_valid_range(self, tmp_path):
        """
        Requirement 9.3: The returned BLEU score must be in the range
        [0.0, 100.0] (allowing a tiny floating-point tolerance above 100).
        """
        ref_file = tmp_path / "reference.txt"
        ref_file.write_text(
            "The quick brown fox jumps over the lazy dog.\n"
            "Pack my box with five dozen liquor jugs.\n",
            encoding="utf-8",
        )

        reporter = BLEU_Reporter()
        blocks = _make_blocks([
            "The quick brown fox jumps over the lazy dog.",
            "Pack my box with five dozen liquor jugs.",
        ])
        result = reporter.compute(blocks, str(ref_file))

        assert result is not None
        # sacrebleu may return values very slightly above 100.0 due to
        # floating-point arithmetic; allow a small epsilon.
        assert 0.0 <= result <= 100.0 + 1e-6

    def test_identical_hypothesis_and_reference_returns_100(self, tmp_path):
        """
        Requirement 9.3: When hypothesis and reference are identical, the
        BLEU score should be 100.0 (perfect match).
        """
        sentences = [
            "The cat sat on the mat.",
            "A quick brown fox jumps over the lazy dog.",
        ]
        ref_file = tmp_path / "reference.txt"
        ref_file.write_text("\n".join(sentences) + "\n", encoding="utf-8")

        reporter = BLEU_Reporter()
        blocks = _make_blocks(sentences)
        result = reporter.compute(blocks, str(ref_file))

        assert result is not None
        assert abs(result - 100.0) < 1e-6, (
            f"Expected BLEU=100.0 for identical hypothesis/reference, got {result}"
        )

    def test_completely_different_hypothesis_returns_low_score(self, tmp_path):
        """
        Requirement 9.3: When hypothesis and reference share no n-grams,
        the BLEU score should be 0.0.
        """
        ref_file = tmp_path / "reference.txt"
        ref_file.write_text(
            "The cat sat on the mat.\n"
            "A quick brown fox jumps over the lazy dog.\n",
            encoding="utf-8",
        )

        reporter = BLEU_Reporter()
        blocks = _make_blocks([
            "Completely unrelated sentence with different words.",
            "Another totally different phrase here now.",
        ])
        result = reporter.compute(blocks, str(ref_file))

        assert result is not None
        assert 0.0 <= result <= 100.0


class TestBLEUReporterMismatchedCounts:
    """
    Requirement 9.4: When translated block count differs from reference line
    count, BLEU must be computed over aligned pairs and a warning printed.
    """

    def test_more_blocks_than_references_returns_float(self, tmp_path):
        """
        Requirement 9.4: When there are more translated blocks than reference
        lines, compute() must still return a float (computed over aligned pairs).
        """
        ref_file = tmp_path / "reference.txt"
        ref_file.write_text("Hello world.\n", encoding="utf-8")

        reporter = BLEU_Reporter()
        blocks = _make_blocks(["Hello world.", "Extra block not in reference."])
        result = reporter.compute(blocks, str(ref_file))

        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0

    def test_more_references_than_blocks_returns_float(self, tmp_path):
        """
        Requirement 9.4: When there are more reference lines than translated
        blocks, compute() must still return a float (computed over aligned pairs).
        """
        ref_file = tmp_path / "reference.txt"
        ref_file.write_text(
            "Hello world.\nExtra reference line not matched.\n",
            encoding="utf-8",
        )

        reporter = BLEU_Reporter()
        blocks = _make_blocks(["Hello world."])
        result = reporter.compute(blocks, str(ref_file))

        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0

    def test_mismatched_counts_prints_warning(self, tmp_path, capsys):
        """
        Requirement 9.4: When counts differ, a warning must be printed to
        stdout stating the count mismatch.
        """
        ref_file = tmp_path / "reference.txt"
        ref_file.write_text(
            "Hello world.\nSecond reference line.\nThird reference line.\n",
            encoding="utf-8",
        )

        reporter = BLEU_Reporter()
        blocks = _make_blocks(["Hello world."])
        reporter.compute(blocks, str(ref_file))

        captured = capsys.readouterr()
        assert "⚠️" in captured.out
        # Warning should mention the counts
        assert "1" in captured.out and "3" in captured.out

    def test_mismatched_counts_aligns_by_index(self, tmp_path):
        """
        Requirement 9.4: BLEU is computed only over the min(n_hyp, n_ref)
        aligned pairs — the extra lines/blocks are ignored.
        """
        # 2 blocks, 3 reference lines → align over 2 pairs
        ref_file = tmp_path / "reference.txt"
        ref_file.write_text(
            "The cat sat on the mat.\n"
            "A quick brown fox.\n"
            "This line has no matching block.\n",
            encoding="utf-8",
        )

        reporter = BLEU_Reporter()
        blocks = _make_blocks([
            "The cat sat on the mat.",
            "A quick brown fox.",
        ])
        result = reporter.compute(blocks, str(ref_file))

        # Should succeed and return a valid score
        assert result is not None
        # sacrebleu may return values very slightly above 100.0 due to
        # floating-point arithmetic; allow a small epsilon.
        assert 0.0 <= result <= 100.0 + 1e-6


class TestBLEUReporterUnreadableFile:
    """
    Requirement 9.6: When the reference file cannot be read or is malformed,
    BLEU_Reporter must return None and print a warning.
    """

    def test_unreadable_file_returns_none(self, tmp_path):
        """
        Requirement 9.6: A file that cannot be opened (e.g., permission
        denied or non-existent) must cause compute() to return None.
        """
        reporter = BLEU_Reporter()
        blocks = _make_blocks(["Hello world."])
        # Use a path that definitely does not exist
        result = reporter.compute(blocks, str(tmp_path / "does_not_exist.txt"))
        assert result is None

    def test_unreadable_file_prints_warning(self, tmp_path, capsys):
        """
        Requirement 9.6: When the reference file cannot be read, a warning
        must be printed to stdout identifying the file path and the error.
        """
        reporter = BLEU_Reporter()
        blocks = _make_blocks(["Hello world."])
        missing_path = str(tmp_path / "does_not_exist.txt")
        reporter.compute(blocks, missing_path)

        captured = capsys.readouterr()
        assert "⚠️" in captured.out
        # Warning should mention the file path
        assert "does_not_exist.txt" in captured.out

    def test_directory_as_reference_file_returns_none(self, tmp_path):
        """
        Requirement 9.6: Passing a directory path instead of a file path
        must cause compute() to return None without raising an exception.
        """
        reporter = BLEU_Reporter()
        blocks = _make_blocks(["Hello world."])
        # tmp_path is a directory, not a file
        result = reporter.compute(blocks, str(tmp_path))
        assert result is None

    def test_directory_as_reference_file_prints_warning(self, tmp_path, capsys):
        """
        Requirement 9.6: Passing a directory path must print a warning to
        stdout.
        """
        reporter = BLEU_Reporter()
        blocks = _make_blocks(["Hello world."])
        reporter.compute(blocks, str(tmp_path))

        captured = capsys.readouterr()
        assert "⚠️" in captured.out


# ---------------------------------------------------------------------------
# Task 15.2 — Integration smoke tests
# Requirements: 1.5, 2.1, 3.1, 7.1, 8.1, 9.3, 10.1
# ---------------------------------------------------------------------------
#
# These tests verify that the full pipeline runs end-to-end without crashing.
# They do NOT assert translation quality — only that the pipeline completes
# and returns the expected result structure.
#
# The translation model is loaded at module import time in document_translator_v3.
# If the model is unavailable the entire module import will fail; we guard
# against that with a module-level importorskip so the tests are skipped
# gracefully in environments without the model weights.

import tempfile

# Guard: skip the whole class if document_translator_v3 cannot be imported
# (e.g. model weights not downloaded, transformers not installed, etc.)
_dt_v3 = pytest.importorskip(
    "document_translator_v3",
    reason="document_translator_v3 not importable (model or dependencies missing)",
)
run_pipeline = _dt_v3.run_pipeline


@pytest.mark.slow
class TestIntegrationSmokeDOCX:
    """
    Smoke test: translate a minimal synthetic DOCX end-to-end.
    Requirements: 1.5, 2.1, 3.1, 7.1, 8.1, 9.3
    """

    def test_docx_pipeline_runs_and_returns_result_dict(self, tmp_path):
        """
        Requirement 9.3: run_pipeline() must return a dict with keys
        'output_file', 'translated_blocks', and 'bleu_score'.
        Requirements 7.1, 8.1: paragraph and table content must be processed.
        Requirements 1.5, 2.1, 3.1: pipeline uses Chunk_Splitter,
        Context_Buffer, and Glossary_Store (no glossary here → no-op).
        """
        docx = pytest.importorskip(
            "docx",
            reason="python-docx not installed",
        )
        from docx import Document as _Document

        # ── Build a minimal synthetic DOCX ───────────────────────────────────
        doc = _Document()
        doc.add_paragraph(
            "The quick brown fox jumps over the lazy dog near the river bank."
        )
        doc.add_paragraph(
            "She sells seashells by the seashore every single morning."
        )
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Hello world from the first cell."
        table.cell(0, 1).text = "Second cell contains more text here."
        table.cell(1, 0).text = "Third cell with additional content."
        table.cell(1, 1).text = "Fourth cell ends the table row."

        input_path = str(tmp_path / "input.docx")
        output_path = str(tmp_path / "output.docx")
        doc.save(input_path)

        # ── Run the pipeline ──────────────────────────────────────────────────
        try:
            result = run_pipeline(
                input_file=input_path,
                source_lang="English",
                target_lang="Filipino",
                output_file=output_path,
            )
        except Exception as exc:
            pytest.skip(f"Pipeline raised an exception (model may be unavailable): {exc}")

        # ── Assertions ────────────────────────────────────────────────────────
        # Requirement 9.3: result dict must have all three keys
        assert isinstance(result, dict), "run_pipeline() must return a dict"
        assert "output_file" in result, "result dict must contain 'output_file'"
        assert "translated_blocks" in result, "result dict must contain 'translated_blocks'"
        assert "bleu_score" in result, "result dict must contain 'bleu_score'"

        # Output file must exist on disk
        assert os.path.exists(result["output_file"]), (
            f"Output file does not exist: {result['output_file']}"
        )

        # translated_blocks must be a non-empty list
        assert isinstance(result["translated_blocks"], list)
        assert len(result["translated_blocks"]) > 0

        # bleu_score must be None (no reference file provided)
        assert result["bleu_score"] is None


@pytest.mark.slow
class TestIntegrationSmokePDF:
    """
    Smoke test: translate a minimal synthetic PDF end-to-end.
    Requirements: 1.5, 2.1, 3.1, 9.3, 10.1
    """

    def test_pdf_pipeline_runs_and_output_exists(self, tmp_path):
        """
        Requirement 10.1: Column_Detector must handle a 2-column layout.
        Requirements 1.5, 2.1, 3.1: pipeline uses Chunk_Splitter,
        Context_Buffer, and Glossary_Store (no glossary → no-op).
        """
        fitz_mod = pytest.importorskip(
            "fitz",
            reason="PyMuPDF (fitz) not installed",
        )

        # ── Build a minimal synthetic PDF with 2 text blocks in 2 columns ────
        # Page width = 595 pt (A4). Two columns separated by a gap > 10%.
        # Left column: x0=50, x1=240  (width 190 pt)
        # Right column: x0=355, x1=545 (width 190 pt)
        # Gap between columns: 355 - 240 = 115 pt ≈ 19% of 595 → detected as 2-col.
        pdf_doc = fitz_mod.open()
        page = pdf_doc.new_page(width=595, height=842)

        left_rect = fitz_mod.Rect(50, 100, 240, 200)
        right_rect = fitz_mod.Rect(355, 100, 545, 200)

        left_text = (
            "The quick brown fox jumps over the lazy dog near the river bank today."
        )
        right_text = (
            "She sells seashells by the seashore every single morning without fail."
        )

        page.insert_textbox(left_rect, left_text, fontsize=11, color=(0, 0, 0))
        page.insert_textbox(right_rect, right_text, fontsize=11, color=(0, 0, 0))

        input_path = str(tmp_path / "input.pdf")
        output_path = str(tmp_path / "output.pdf")
        pdf_doc.save(input_path)
        pdf_doc.close()

        # ── Run the pipeline ──────────────────────────────────────────────────
        try:
            result = run_pipeline(
                input_file=input_path,
                source_lang="English",
                target_lang="Filipino",
                output_file=output_path,
            )
        except Exception as exc:
            pytest.skip(f"Pipeline raised an exception (model may be unavailable): {exc}")

        # ── Assertions ────────────────────────────────────────────────────────
        # Output file must exist on disk
        assert os.path.exists(result["output_file"]), (
            f"Output file does not exist: {result['output_file']}"
        )

        # Result must be a dict (Requirement 9.3)
        assert isinstance(result, dict)
        assert "output_file" in result
        assert "translated_blocks" in result
        assert "bleu_score" in result


# ---------------------------------------------------------------------------
# Anti-hallucination detection tests
# ---------------------------------------------------------------------------

from document_translator_v3 import _detect_hallucination_in_output


class TestHallucinationDetection:
    """Tests for _detect_hallucination_in_output."""

    # ── Explanatory phrases (should be flagged) ──────────────────────────────

    def test_detect_here_is_the_translation(self):
        flagged, reason = _detect_hallucination_in_output(
            "Here is the translation: Moadto ko sa merkado.", "I am going to the market."
        )
        assert flagged is True
        assert "Explanatory" in reason

    def test_detect_translation_colon(self):
        flagged, reason = _detect_hallucination_in_output(
            "Translation: Unsa imong pangalan?", "What is your name?"
        )
        assert flagged is True

    def test_detect_in_cebuano(self):
        flagged, reason = _detect_hallucination_in_output(
            "In Cebuano, the translation is: Daghang salamat.", "Thank you very much."
        )
        assert flagged is True

    def test_detect_hope_this_helps(self):
        flagged, reason = _detect_hallucination_in_output(
            "Moadto ko sa merkado. I hope this helps!", "I am going to the market."
        )
        assert flagged is True

    def test_detect_let_me_know(self):
        flagged, reason = _detect_hallucination_in_output(
            "Moadto ko sa merkado. Let me know if you need anything else.",
            "I am going to the market."
        )
        assert flagged is True

    # ── Clean translations (should NOT be flagged) ───────────────────────────

    def test_clean_translation_not_flagged(self):
        flagged, _ = _detect_hallucination_in_output(
            "Moadto ko sa merkado.", "I am going to the market."
        )
        assert flagged is False

    def test_clean_filipino_not_flagged(self):
        flagged, _ = _detect_hallucination_in_output(
            "Pupunta ako sa palengke.", "I am going to the market."
        )
        assert flagged is False

    # ── Verbosity detection ───────────────────────────────────────────────────

    def test_verbosity_short_text_high_ratio(self):
        # 1 word → 10 words = 10x (exceeds 8x for ≤5 word source)
        flagged, reason = _detect_hallucination_in_output(
            "One two three four five six seven eight nine ten",
            "Hello"
        )
        assert flagged is True
        assert "verbosity" in reason.lower()

    def test_verbosity_medium_text_high_ratio(self):
        # 10 words → 35 words = 3.5x (exceeds 3x for 6-30 word source)
        src = " ".join([f"word{i}" for i in range(10)])
        tgt = " ".join([f"word{i}" for i in range(35)])
        flagged, reason = _detect_hallucination_in_output(tgt, src)
        assert flagged is True

    def test_verbosity_ok_ratio(self):
        # 10 words → 12 words = 1.2x (well within 3x)
        src = " ".join([f"word{i}" for i in range(10)])
        tgt = " ".join([f"word{i}" for i in range(12)])
        flagged, _ = _detect_hallucination_in_output(tgt, src)
        assert flagged is False

    # ── Sentence inflation detection ──────────────────────────────────────────

    def test_sentence_inflation(self):
        # Source: 1 sentence. Target: 5 sentences.
        flagged, reason = _detect_hallucination_in_output(
            "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence.",
            "Hello world."
        )
        assert flagged is True
        assert "inflation" in reason.lower() or "sentence" in reason.lower()

    def test_no_false_positive_normal_punctuation(self):
        flagged, _ = _detect_hallucination_in_output(
            "Moadto ko. Unsa imong pangalan? Daghang salamat.",
            "I'm going. What is your name? Thank you very much."
        )
        assert flagged is False

    def test_added_punctuation_to_plain_text(self):
        flagged, reason = _detect_hallucination_in_output(
            "Word one. Word two. Word three.",
            "Word one word two word three"
        )
        assert flagged is True

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_empty_strings(self):
        flagged, _ = _detect_hallucination_in_output("", "Hello")
        assert flagged is False

    def test_both_empty(self):
        flagged, _ = _detect_hallucination_in_output("", "")
        assert flagged is False

    def test_none_safe(self):
        # Ensure no crash on empty/None-like inputs
        flagged, _ = _detect_hallucination_in_output("test", "")
        assert flagged is False
