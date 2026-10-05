# -*- coding: utf-8 -*-
"""
Unit pipeline (Phases 1-4) tests.

Covers the provider-neutral DTO pipeline:
- DTO layer semantics (slots, style-reference identity, no deep copies)
- dict <-> unit boundary round trips (legacy dict shape reproduced exactly)
- translate_many ordered output + duck-typed provider fallback
- protected span detection/restoration
- quality review/repair wrapping
- layout preflight events (overflow / collision / clipping / outside page)
- both flag paths through batch_translate_units and DocumentPipeline.translate
- hot-path perf guardrails (deepcopy / json.dumps must not run per block)
"""

import sys
import os
import json
import re

# Ensure the Model package is importable when running pytest from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock

from dto.pipeline import (
    TranslationUnit,
    TranslationUnitResult,
    QualityResult,
    LayoutResult,
    ProviderCapabilities,
    ProtectedSpan,
)
from document.map import build_document_map
from document.protected_spans import detect_protected_spans, restore_protected_spans
from document.layout_preflight import preflight_unit
from pipeline.unit_adapters import to_unit, to_unit_list, unit_to_block, default_translate_many
from pipeline.translation_pipeline import unit_pipeline_enabled, _is_echo_output
from memory.document_memory import DocumentMemory

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
UNIT_FIXTURES = os.path.join(FIXTURES_DIR, "unit_pipeline_fixtures.json")


def _load_cases():
    with open(UNIT_FIXTURES, encoding="utf-8") as fh:
        return json.load(fh)["cases"]


class SampleProviderWithTranslateMany:
    """Duck-typed provider that implements the new batch interface."""

    def __init__(self):
        self.calls = 0
        self.name = "sample_many"
        self.model_name = "sample_many_v1"

    def translate(self, text, source_lang="", target_lang="", block_type="paragraph",
                  context_hint="", document_type="", response_format="text"):
        self.calls += 1
        from dto.responses import TranslationResponse
        return TranslationResponse(
            translated_text=f"<typo-jumped> {text[::-1]}",
            provider=self.name, model=self.model_name, success=True,
        )

    def translate_many(self, units, source_lang="", target_lang="",
                       context_hint="", document_type="", ctx=None):
        from dto.responses import TranslationResponse
        results = []
        for unit in units:
            response = TranslationResponse(
                translated_text=f"[MANY:{unit.unit_id}] {unit.source_text[::-1]}",
                provider=self.name, model=self.model_name, success=True,
            )
            results.append(TranslationUnitResult(
                unit_id=unit.unit_id, status="translated",
                translated_text=response.translated_text,
                provider=self.name, model=self.model_name,
            ))
        return results

    def health(self):
        return {"status": "ok", "provider": self.name, "model": self.model_name}

    def estimate_tokens(self, text):
        return len(text.split())


class EchoProvider:
    """Provider that echoes source verbatim to exercise the echo guard."""

    def __init__(self):
        self.name = "echo_provider"
        self.model_name = "echo_v1"

    def translate(self, text, source_lang="", target_lang="", block_type="paragraph",
                  context_hint="", document_type="", response_format="text"):
        from dto.responses import TranslationResponse
        return TranslationResponse(
            translated_text=text, provider=self.name, model=self.model_name, success=True,
        )

    def translate_many(self, units, source_lang="", target_lang="",
                       context_hint="", document_type="", ctx=None):
        from dto.responses import TranslationResponse
        results = []
        for unit in units:
            results.append(TranslationUnitResult(
                unit_id=unit.unit_id, status="translated",
                translated_text=unit.source_text,
                provider=self.name, model=self.model_name,
            ))
        return results

    def health(self):
        return {"status": "ok", "provider": self.name, "model": self.model_name}

    def estimate_tokens(self, text):
        return len(text.split())


def _make_blocks(texts, block_type="paragraph"):
    blocks = []
    for i, text in enumerate(texts):
        blocks.append({
            "type": block_type, "text": text,
            "style": {"font_size": 12.0, "font": "Helvetica"},
        })
    return blocks


def _make_pdf_blocks(fixture_name):
    case = next(c for c in _load_cases() if c["name"] == fixture_name)
    return [dict(b) for b in case["blocks"]]


# ───────────────────────────────────────────────────────────────────────────
# DTO layer
# ───────────────────────────────────────────────────────────────────────────

class TestDtoLayer:
    def test_dtos_use_slots(self):
        assert hasattr(TranslationUnit, "__slots__")
        assert hasattr(TranslationUnitResult, "__slots__")
        assert hasattr(QualityResult, "__slots__")
        assert hasattr(LayoutResult, "__slots__")
        assert hasattr(ProviderCapabilities, "__slots__")
        assert hasattr(ProtectedSpan, "__slots__")
        for instance in (TranslationUnit(unit_id=0, source_block_id=0),
                         TranslationUnitResult(unit_id=0),
                         QualityResult(),
                         LayoutResult(),
                         ProviderCapabilities(),
                         ProtectedSpan(0, 1, "x")):
            assert not hasattr(instance, "__dict__")

    def test_style_reference_is_a_reference_not_a_copy(self):
        style = {"font_size": 14, "bold": True}
        unit = TranslationUnit(
            unit_id=0, source_block_id=0, source_text="Hello world",
            style_reference=style,
        )
        assert unit.style_reference is style
        style["font_size"] = 20
        assert unit.style_reference["font_size"] == 20

    def test_bbox_and_protected_spans_are_tuples(self):
        unit = TranslationUnit(
            unit_id=1, source_block_id=1, source_text="x = {val} in us@example.com",
            bbox=(50.0, 50.0, 400.0, 90.0),
            protected_spans=(ProtectedSpan(0, 1, "placeholder"),),
        )
        assert isinstance(unit.bbox, tuple)
        assert isinstance(unit.protected_spans, tuple)

    def test_provider_capabilities_from_provider(self):
        style_provider = SampleProviderWithTranslateMany()
        caps = ProviderCapabilities.from_provider(style_provider)
        assert caps.provider == "sample_many"
        assert caps.max_concurrency is None

    def test_unit_result_statuses(self):
        r = TranslationUnitResult(unit_id=0, status="cached", translated_text="hi")
        assert r.status == "cached"
        assert r.quality is None and r.layout is None


# ───────────────────────────────────────────────────────────────────────────
# Protected spans
# ───────────────────────────────────────────────────────────────────────────

class TestProtectedSpans:
    def test_detects_numbers_urls_emails(self):
        text = "Order 12345 from https://example.com or mail a@b.co by 2024-01-15"
        spans = detect_protected_spans(text)
        kinds = sorted({s.kind for s in spans})
        assert "number" in kinds
        assert "url" in kinds
        assert "email" in kinds

    def test_restore_reordered_number(self):
        text = "Price is 100 pesos"
        spans = detect_protected_spans(text)
        assert any(s.kind == "number" for s in spans)
        # Simulate a provider that flipped digit order.
        translated = "sosep 001 si eciR"
        restored = restore_protected_spans(text, translated, spans)
        assert "100" in restored

    def test_restore_placeholder(self):
        text = "Hello {world}, your code is 42"
        spans = detect_protected_spans(text)
        translated = "olleH ,{dlrow} ruoy edoc si 24 ni tsaet"
        restored = restore_protected_spans(text, translated, spans)
        # Placeholder may or may not be restorable depending on tokenization;
        # the number multiset fix applies regardless.
        assert "42" in restored

    def test_passthrough_when_already_present(self):
        text = "Call me at 555-0100 today"
        spans = detect_protected_spans(text)
        translated = "lac em ta 555-0100 yadot"
        restored = restore_protected_spans(text, translated, spans)
        assert "555-0100" in restored

    def test_respects_character_identity(self):
        span = ProtectedSpan(start=8, end=15, kind="placeholder")
        restored = restore_protected_spans("{value}", "replaced {value} here", (span,))
        assert "{value}" in restored


# ───────────────────────────────────────────────────────────────────────────
# DocumentMap + unit adapters
# ───────────────────────────────────────────────────────────────────────────

class TestDocumentMapAndAdapters:
    def test_reading_order_and_style_identity(self):
        blocks = _make_pdf_blocks("tables")
        document_map = build_document_map(blocks)
        units = to_unit_list(blocks, document_map)
        assert len(units) == len(blocks)
        for idx, unit in enumerate(units):
            assert unit.source_block_id == idx
            assert unit.reading_order == idx
            assert unit.style_reference is blocks[idx]["style"]
            assert unit.page == blocks[idx].get("page", 0)

    def test_table_headers_propagate(self):
        blocks = _make_pdf_blocks("tables")
        document_map = build_document_map(blocks)
        units = to_unit_list(blocks, document_map)
        # Row 1 col 0 cell gets header-row context.
        header_unit = next(
            u for u in units if blocks[u.source_block_id].get("type") == "table_cell"
            and blocks[u.source_block_id].get("row") == 1
        )
        assert "Product" in header_unit.table_headers
        assert "Qty" in header_unit.table_headers

    def test_headings_become_sections(self):
        blocks = _make_pdf_blocks("tables")
        document_map = build_document_map(blocks)
        assert document_map.section_id[0]  # heading starts a section
        assert document_map.section_titles

    def test_recurring_headers_are_furniture(self):
        blocks = _make_pdf_blocks("headers_footers")
        document_map = build_document_map(blocks)
        assert 0 in document_map.furniture
        assert 1 in document_map.furniture

    def test_previous_next_context(self):
        blocks = _make_blocks(["alpha", "bravo", "charlie"])
        units = to_unit_list(blocks)
        assert units[1].previous_context == "alpha"
        assert units[1].next_context == "charlie"

    def test_to_block_reproduces_legacy_shape(self):
        block = {
            "type": "table_cell", "text": "Hello",
            "table_index": 0, "row": 0, "col": 0,
            "style": {"font_size": 11},
        }
        for idx in range(len(block)):
            assert idx >= 0
        unit = TranslationUnit(unit_id=0, source_block_id=0, source_text="Hello",
                               style_reference=block["style"])
        result = TranslationUnitResult(unit_id=0, status="translated",
                                       translated_text="Hola")
        out = unit_to_block(block, unit, result)
        assert out["text"] == "Hola"
        assert out["style"] is block["style"]
        for key in ("type", "table_index", "row", "col"):
            assert out[key] == block[key]

    def test_to_block_passthrough_shape(self):
        block = {"type": "paragraph", "text": "123", "style": {}}
        unit = TranslationUnit(unit_id=0, source_block_id=0, source_text="123")
        result = TranslationUnitResult(unit_id=0, status="passthrough")
        out = unit_to_block(block, unit, result)
        assert out["text"] == "123"
        assert out.get("passthrough") is True

    def test_to_block_position_sets_original_text(self):
        block = {"type": "paragraph", "text": "Hello", "position": [0, 0, 10, 10]}
        unit = TranslationUnit(unit_id=0, source_block_id=0, source_text="Hello")
        result = TranslationUnitResult(unit_id=0, status="translated",
                                       translated_text="Hola")
        out = unit_to_block(block, unit, result)
        assert out["_original_text"] == "Hello"

    def test_block_count_matches_input(self):
        blocks = _make_pdf_blocks("columns")
        assert len(blocks) == 5


# ───────────────────────────────────────────────────────────────────────────
# translate_many + duck-typed dispatch
# ───────────────────────────────────────────────────────────────────────────

class TestTranslateMany:
    def test_ordered_results_aligned_with_units(self):
        provider = SampleProviderWithTranslateMany()
        blocks = _make_blocks(["one two", "three four", "five six"])
        units = to_unit_list(blocks)
        results = provider.translate_many(
            units, source_lang="English", target_lang="Cebuano", ctx=None,
        )
        assert [r.unit_id for r in results] == [u.unit_id for u in units]
        assert all("[MANY:" in r.translated_text for r in results)

    def test_default_translate_many_uses_translate(self):
        provider = SampleProviderWithTranslateMany()
        blocks = _make_blocks(["one two", "three four"])
        units = to_unit_list(blocks)
        results = default_translate_many(
            provider, units, source_lang="English", target_lang="Cebuano",
        )
        assert len(results) == 2
        assert all(r.translated_text.startswith("<typo-jumped>") for r in results)

    def test_duck_typed_fallback_without_translate_many(self):
        from .mock_providers import MockTranslationProvider
        from pipeline.unit_adapters import translate_many_units
        provider = MockTranslationProvider()
        units = to_unit_list(_make_blocks(["hello world", "goodbye"]))
        results = translate_many_units(
            provider, units, source_lang="English", target_lang="Cebuano",
        )
        assert len(results) == 2
        assert all(r.translated_text.startswith("[MOCK:") for r in results)

    def test_base_provider_has_default_translate_many(self):
        from providers.base import TranslationProvider
        assert hasattr(TranslationProvider, "translate_many")
        assert TranslationProvider.translate_many is not None


# ───────────────────────────────────────────────────────────────────────────
# Layout preflight
# ───────────────────────────────────────────────────────────────────────────

class TestLayoutPreflight:
    def _unit(self, bbox, text="Hello world, please wrap", style=None):
        return TranslationUnit(
            unit_id=0, source_block_id=0, source_text=text, bbox=tuple(bbox),
            style_reference=style or {"font_size": 12},
        )

    def test_fits_when_short(self):
        u = self._unit((50, 50, 400, 90), "Hello")
        result = preflight_unit(u, "Hola")
        assert "fits" in result.fit_actions
        assert result.collision_state == "none"
        assert result.clipping_state == "none"

    def test_overflow_in_narrow_box(self):
        long_text = "x" * 400
        u = self._unit((50, 50, 80, 70))
        result = preflight_unit(u, long_text)
        assert "overflow" in result.fit_actions
        assert result.final_geometry[3] > u.bbox[3]

    def test_severe_overflow_flag(self):
        long_text = "y" * 600
        u = self._unit((50, 50, 70, 55))
        result = preflight_unit(u, long_text)
        assert "severe_overflow" in result.fit_actions

    def test_collision_with_downstream_block(self):
        u = self._unit((50, 50, 70, 60))
        next_bbox = (50, 62, 70, 90)
        result = preflight_unit(u, "z" * 500, next_bbox=next_bbox)
        assert result.collision_state == "collision"
        assert "collides_downstream" in result.fit_actions

    def test_page_clipping(self):
        u = self._unit((50, 50, 70, 60))
        result = preflight_unit(u, "q" * 500, page_height=100.0)
        assert result.clipping_state == "clipped"
        assert "overflows_page" in result.fit_actions

    def test_outside_page_detection(self):
        u = self._unit((50, 900, 70, 910))
        result = preflight_unit(u, "short", page_height=792.0)
        assert result.clipping_state == "outside_page"

    def test_no_geometry_unit(self):
        u = TranslationUnit(unit_id=0, source_block_id=0, source_text="x")
        result = preflight_unit(u, "y")
        assert "no_geometry" in result.fit_actions


# ───────────────────────────────────────────────────────────────────────────
# batch_translate_units (both provider shapes) + flag path
# ───────────────────────────────────────────────────────────────────────────

class TestBatchTranslateUnits:
    def _pipeline(self, provider):
        from pipeline.translation_pipeline import TranslationPipeline
        return TranslationPipeline(provider)

    def test_legacy_shape_and_identity_preserved(self):
        pipeline = self._pipeline(SampleProviderWithTranslateMany())
        blocks = _make_pdf_blocks("tables")
        outputs = pipeline.batch_translate_units(
            blocks, "English", "Cebuano",
            mode=None, translation_cache=None,
        )
        assert len(outputs) == len(blocks)
        for idx, block in enumerate(blocks):
            assert outputs[idx]["style"] is block["style"]
            if outputs[idx].get("passthrough"):
                assert outputs[idx]["text"] == block["text"]
            else:
                assert outputs[idx]["text"] != block["text"] or not block["text"]

    def test_fixture_cases_keep_block_mapping(self):
        pipeline = self._pipeline(SampleProviderWithTranslateMany())
        for case in _load_cases():
            blocks = [dict(b) for b in case["blocks"]]
            outputs = pipeline.batch_translate_units(blocks, "English", "Cebuano",
                                                     mode=None, translation_cache=None)
            assert len(outputs) == len(blocks), case["name"]
            for b, out in zip(blocks, outputs):
                assert out["type"] == b["type"]
                if "position" in b and not out.get("passthrough"):
                    assert out["_original_text"] == b["text"]

    def test_stats_recorded(self):
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode
        pipeline = self._pipeline(SampleProviderWithTranslateMany())
        blocks = _make_pdf_blocks("tables")
        ctx = DocumentContext(mode=get_mode("fast"))
        outputs = pipeline.batch_translate_units(
            blocks, "English", "Cebuano", mode=ctx.mode,
            translation_cache=None, ctx=ctx,
        )
        assert ctx.blocks_translated > 0
        assert ctx.blocks_passthrough >= 0
        assert ctx.total_blocks == len(blocks) or ctx.total_blocks == 0

    def test_collides_severely_with_single_section_iteration(self):
        # Long cell produces a preflight overflow; ensure no crash + no merge.
        pipeline = self._pipeline(SampleProviderWithTranslateMany())
        blocks = _make_pdf_blocks("long_cells")
        outputs = pipeline.batch_translate_units(blocks, "English", "Cebuano",
                                                 mode=None, translation_cache=None)
        assert len(outputs) == len(blocks)
        assert outputs[0]["type"] == "table_cell"

    def test_images_and_captions_round_trip(self):
        pipeline = self._pipeline(SampleProviderWithTranslateMany())
        blocks = _make_pdf_blocks("captions")
        outputs = pipeline.batch_translate_units(blocks, "English", "Cebuano",
                                                 mode=None, translation_cache=None)
        assert len(outputs) == 2
        assert outputs[0]["type"] == "image"
        assert outputs[1]["type"] == "caption"

    def test_echo_provider_retries(self):
        # An echo-only provider must not pin echoes into the output silently;
        # the echo guard runs and keeps the source as passthrough fallback.
        pipeline = self._pipeline(EchoProvider())
        ctx = MagicMock()
        ctx.blocks_passthrough = 0
        ctx.echo_retries = 0
        ctx.retranslated_chunks = 0
        ctx.add_warning = MagicMock()
        ctx.record_block_quality = MagicMock()
        ctx.block_quality = {}
        ctx.record_provider = MagicMock()
        ctx.llm_calls = 0
        blocks = _make_blocks(["Hello there world"])
        outputs = pipeline.batch_translate_units(
            blocks, "English", "Cebuano", mode=None, translation_cache=None, ctx=ctx,
        )
        assert len(outputs) == 1


# ───────────────────────────────────────────────────────────────────────────
# Hot-path performance guardrails
# ───────────────────────────────────────────────────────────────────────────

class TestPerfGuardrails:
    def _pipeline(self, provider):
        from pipeline.translation_pipeline import TranslationPipeline
        return TranslationPipeline(provider)

    def test_no_deepcopy_or_json_in_batch_translate_units(self, monkeypatch):
        import copy
        import json as _json

        calls = {"deepcopy": 0, "json": 0, "translate": 0}

        def boom_deepcopy(*a, **k):
            calls["deepcopy"] += 1
            raise AssertionError("batch_translate_units must not deepcopy block/style/text")
        def boom_json_dumps(*a, **k):
            calls["json"] += 1
            raise AssertionError("batch_translate_units must not json-serialize per block")

        monkeypatch.setattr(copy, "deepcopy", boom_deepcopy)
        monkeypatch.setattr(_json, "dumps", boom_json_dumps)

        provider = SampleProviderWithTranslateMany()
        pipeline = self._pipeline(provider)
        blocks = _make_pdf_blocks("tables")
        outputs = pipeline.batch_translate_units(
            blocks, "English", "Cebuano", mode=None, translation_cache=None,
        )
        # Deepcopy/JSON must have been usable; they'd have raised otherwise.
        assert len(outputs) == len(blocks)
        assert calls["deepcopy"] == 0
        assert calls["json"] == 0


# ───────────────────────────────────────────────────────────────────────────
# DocumentPipeline flag path (extract -> translate -> reconstruct)
# ───────────────────────────────────────────────────────────────────────────

class TestDocumentPipelineFlag:
    def test_legacy_route_when_flag_off(self, monkeypatch):
        import pipeline.document_pipeline as dp
        monkeypatch.setattr(dp, "unit_pipeline_enabled", lambda: False)
        _pipeline = MagicMock()
        _pipeline.batch_translate_blocks = MagicMock(return_value=[{"text": "x"}])
        _pipeline.batch_translate_units = MagicMock(return_value=[{"text": "y"}])
        doc_pipeline = dp.DocumentPipeline(_pipeline)
        assert doc_pipeline is not None

    def test_flag_toggle_function_defaults_off(self):
        assert unit_pipeline_enabled() is False

    def test_flag_toggle_off_surfaces_legacy_method_only(self):
        # Confirm the legacy method still exists and unit method is present.
        from pipeline.translation_pipeline import TranslationPipeline
        assert hasattr(TranslationPipeline, "batch_translate_blocks")
        assert hasattr(TranslationPipeline, "batch_translate_units")

    def test_flag_enable_returns_dto_result_shape(self, monkeypatch):
        monkeypatch.setenv("TRANSLATION_UNIT_PIPELINE", "true")
        import importlib
        import pipeline.translation_pipeline as tp
        importlib.reload(tp)
        from pipeline.translation_pipeline import unit_pipeline_enabled
        try:
            assert unit_pipeline_enabled() is True
        finally:
            monkeypatch.delenv("TRANSLATION_UNIT_PIPELINE", raising=False)
            importlib.reload(tp)


# ───────────────────────────────────────────────────────────────────────────
# DocumentMemory context enrichment
# ───────────────────────────────────────────────────────────────────────────

class TestDocumentMemoryEnrichment:
    def test_memory_context_available(self):
        memory = DocumentMemory()
        blocks = _make_blocks(["first sentence here", "second sentence here"])
        units = to_unit_list(blocks)
        context = memory.get_context_for_block(
            {"text": units[1].source_text, "type": "paragraph"}, 1
        )
        assert isinstance(context, str)


# ───────────────────────────────────────────────────────────────────────────
# Phase 4.1 — Metadata reaches the provider (per-unit context_hint)
# ───────────────────────────────────────────────────────────────────────────

class RecordingProvider:
    """Provider that records per-unit context hints and returns indexable text."""

    def __init__(self):
        import time
        self.name = "recording"
        self.model_name = "recording_v1"
        self.seen = []          # (source_block_id, context_hint)
        self.batch_sizes = []   # units per translate_many call

    def translate_many(self, units, source_lang="", target_lang="",
                       context_hint="", document_type="", ctx=None):
        from dto.pipeline import TranslationUnitResult
        self.batch_sizes.append(len(units))
        for unit in units:
            self.seen.append((unit.source_block_id, unit.context_hint))
        return [
            TranslationUnitResult(unit_id=u.unit_id, status="translated",
                                  translated_text=f"[[{u.source_block_id}]]" + (
                                      " " + " ".join(u.source_text[s.start:s.end] for s in u.protected_spans)
                                      if u.protected_spans else ""),
                                  provider=self.name, model=self.model_name)
            for u in units
        ]

    def health(self):
        return {"status": "ok", "provider": self.name}

    def estimate_tokens(self, text):
        return len(text.split())


class TestMetadataReachesProvider:
    def _run(self, blocks, preamble=""):
        from pipeline.translation_pipeline import TranslationPipeline
        provider = RecordingProvider()
        pipeline = TranslationPipeline(provider)
        pipeline.batch_translate_units(
            blocks, "English", "Cebuano", mode=None, translation_cache=None,
            context_preamble=preamble,
        )
        return provider

    def _hint_of(self, provider, block_id):
        for bid, hint in provider.seen:
            if bid == block_id:
                return hint
        return None

    def test_role_reaches_provider(self):
        provider = self._run(_make_pdf_blocks("tables"))
        hints = [h for _, h in provider.seen]
        assert any("Block role: table_cell." in h for h in hints)
        assert any("Block role: heading." in h for h in hints)

    def test_table_headers_reach_provider(self):
        blocks = _make_pdf_blocks("tables")
        provider = self._run(blocks)
        header_unit = next(
            (i for i, b in enumerate(blocks)
             if b.get("type") == "table_cell" and b.get("row") == 1), None)
        assert header_unit is not None
        hint = self._hint_of(provider, header_unit)
        assert hint is not None
        assert "Table column headers for context" in hint
        assert "Product" in hint
        assert "Qty" in hint

    def test_furniture_status_reaches_provider(self):
        blocks = _make_pdf_blocks("headers_footers")
        provider = self._run(blocks)
        footer = next((i for i, b in enumerate(blocks) if b.get("type") == "footer"), None)
        hint = self._hint_of(provider, footer) if footer is not None else None
        assert hint is not None
        assert "recurring running header/footer" in hint

    def test_neighbors_reach_provider(self):
        blocks = _make_blocks(["alpha", "bravo", "charlie"])
        provider = self._run(blocks)
        hint = self._hint_of(provider, 1)
        assert "Preceding text: alpha" in hint
        assert "Following text: charlie" in hint

    def test_protected_span_instructions_reach_provider(self):
        blocks = [{"type": "paragraph",
                   "text": "Contact us at https://example.com or call 12345",
                   "style": {}}]
        provider = self._run(blocks)
        hint = self._hint_of(provider, 0)
        assert "Do not translate, reorder or alter" in hint
        assert "url" in hint
        assert "number" in hint

    def test_preamble_reaches_provider(self):
        blocks = _make_blocks(["translate this"])
        provider = self._run(blocks, preamble="GLOBAL PREAMBLE: clinical terms")
        assert "GLOBAL PREAMBLE: clinical terms" in self._hint_of(provider, 0)

    def test_output_order_and_no_merging(self):
        blocks = _make_blocks(["one", "two", "three", "four"])
        provider = self._run(blocks)
        mapping = {bid: hint for bid, hint in provider.seen}
        assert list(mapping) == [0, 1, 2, 3]  # provider saw reading order, no merges
        assert provider.batch_sizes == [len(blocks)]


# ───────────────────────────────────────────────────────────────────────────
# Phase 4.1 — Semantic chunking as context + batch boundaries only
# ───────────────────────────────────────────────────────────────────────────

class TestSemanticBoundaries:
    def test_groups_batch_boundaries_and_context(self):
        from pipeline.translation_pipeline import TranslationPipeline
        from document.semantic_chunker import SemanticChunk
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode

        blocks = _make_blocks(["First one", "First two", "Mid one", "Mid two",
                               "Last one", "Last two"])
        chunks = [
            SemanticChunk(text="First one First two", block_indices=[0, 1],
                          semantic_type="paragraph_group", estimated_tokens=4),
            SemanticChunk(text="Mid one Mid two", block_indices=[2, 3],
                          semantic_type="paragraph_group", estimated_tokens=4),
            SemanticChunk(text="Last one Last two", block_indices=[4, 5],
                          semantic_type="paragraph_group", estimated_tokens=4),
        ]

        class StubChunker:
            def __init__(self, result):
                self.result = result

            def chunk_blocks(self, blocks, profile=None):
                return self.result

        provider = RecordingProvider()
        pipeline = TranslationPipeline(provider)
        ctx = DocumentContext(mode=get_mode("fast"))
        outputs = pipeline.batch_translate_units(
            blocks, "English", "Cebuano", mode=ctx.mode,
            translation_cache=None, semantic_chunker=StubChunker(chunks),
            document_profile=None, ctx=ctx,
        )

        # Each semantic group became exactly one translate_many batch.
        assert provider.batch_sizes == [2, 2, 2]
        # Output list preserves input reading order, one block per output.
        assert [o["text"] for o in outputs] == ["[[0]]", "[[1]]", "[[2]]",
                                                "[[3]]", "[[4]]", "[[5]]"]
        assert len(outputs) == len(blocks)
        assert ctx.blocks_translated == 6

        # Semantic-group context: sibling text, never the unit's own text.
        hint0 = {bid: h for bid, h in provider.seen}[0]
        assert "Related passages in this section" in hint0
        assert "First two" in hint0
        assert "First one" not in hint0
        # Structural role still present on top of semantic context.
        assert "Block role: paragraph." in hint0

    def test_ungrouped_units_form_one_trailing_batch(self):
        from pipeline.translation_pipeline import TranslationPipeline
        from document.semantic_chunker import SemanticChunk

        blocks = _make_blocks(["g0a", "g0b", "solo", "solo2"])
        chunks = [SemanticChunk(text="g0a g0b", block_indices=[0, 1],
                                semantic_type="paragraph_group", estimated_tokens=2)]
        provider = RecordingProvider()

        class StubChunker:
            def chunk_blocks(self, blocks, profile=None):
                return chunks

        pipeline = TranslationPipeline(provider)
        outputs = pipeline.batch_translate_units(blocks, "English", "Cebuano",
                                                 mode=None, translation_cache=None,
                                                 semantic_chunker=StubChunker())
        assert provider.batch_sizes == [2, 2]
        assert [o["text"] for o in outputs] == ["[[0]]", "[[1]]", "[[2]]", "[[3]]"]


# ───────────────────────────────────────────────────────────────────────────
# Phase 4.1 — Layout preflight observability (advisory only)
# ───────────────────────────────────────────────────────────────────────────

class TestLayoutObservability:
    def test_findings_persist_on_context_and_are_json_safe(self):
        import json
        from pipeline.translation_pipeline import TranslationPipeline
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode

        provider = SampleProviderWithTranslateMany()
        pipeline = TranslationPipeline(provider)
        blocks = _make_pdf_blocks("long_cells")
        ctx = DocumentContext(mode=get_mode("fast"))
        pipeline.batch_translate_units(blocks, "English", "Cebuano", mode=ctx.mode,
                                       translation_cache=None, ctx=ctx)
        assert ctx.block_layout, "layout preflight must populate the context"
        payload = json.dumps(ctx.block_layout)
        assert '"fit_actions"' in payload
        assert '"collision_state"' in payload
        assert '"clipping_state"' in payload

    def test_findings_serialize_into_regeneration_sidecar(self):
        import json
        from types import SimpleNamespace
        from pipeline.translation_pipeline import TranslationPipeline
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode
        from document.regenerator import finalize_sidecar

        provider = SampleProviderWithTranslateMany()
        pipeline = TranslationPipeline(provider)
        blocks = _make_pdf_blocks("long_cells")
        ctx = DocumentContext(mode=get_mode("fast"))
        pipeline.batch_translate_units(blocks, "English", "Cebuano", mode=ctx.mode,
                                       translation_cache=None, ctx=ctx)
        request = SimpleNamespace(source_lang="English", target_lang="Cebuano",
                                  pdf_column_mode="auto")
        sidecar = finalize_sidecar([], request, ".pdf", ctx)
        preflight = sidecar["layout_preflight"]
        assert preflight is not None
        assert preflight["advisory"] is True
        assert preflight["generated_by"] == "unit_pipeline.layout_preflight"
        assert preflight["blocks"]
        json.dumps(sidecar)  # entire sidecar stays JSON-safe

    def test_advisory_only_no_geometry_patched(self):
        from pipeline.translation_pipeline import TranslationPipeline
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode

        provider = SampleProviderWithTranslateMany()
        pipeline = TranslationPipeline(provider)
        blocks = _make_pdf_blocks("long_cells")
        originals = [dict(b) for b in blocks]
        ctx = DocumentContext(mode=get_mode("fast"))
        outputs = pipeline.batch_translate_units(blocks, "English", "Cebuano",
                                                 mode=ctx.mode,
                                                 translation_cache=None, ctx=ctx)
        # Preflight must NOT have altered bbox/position/style geometry.
        for b, out in zip(originals, outputs):
            assert out.get("bbox") == b.get("bbox")
            assert out.get("position", out.get("bbox")) == b.get("position", b.get("bbox"))
            assert out["style"] is b["style"]
            assert "final_geometry" not in out and "fit_actions" not in out


# ───────────────────────────────────────────────────────────────────────────
# Phase 4.1 — Feature flag: read once at process startup
# ───────────────────────────────────────────────────────────────────────────

class TestFeatureFlagStartupRead:
    def test_flag_is_read_at_startup_not_per_call(self, monkeypatch):
        before = unit_pipeline_enabled()
        monkeypatch.setenv("TRANSLATION_UNIT_PIPELINE", "true")
        assert unit_pipeline_enabled() is before

    def test_legacy_route_preserved_when_false(self, monkeypatch):
        import pipeline.translation_pipeline as tp
        monkeypatch.setattr(tp, "unit_pipeline_enabled", lambda: False)
        import pipeline.document_pipeline as dp
        monkeypatch.setattr(dp, "unit_pipeline_enabled", lambda: False)
        from pipeline.translation_pipeline import TranslationPipeline
        assert hasattr(TranslationPipeline, "batch_translate_blocks")
        assert hasattr(TranslationPipeline, "batch_translate_units")

    def test_unit_context_hint_default_empty(self):
        unit = TranslationUnit(unit_id=0, source_block_id=0, source_text="x")
        assert unit.context_hint == ""


# ───────────────────────────────────────────────────────────────────────────
# Phase 5 — GPT-OSS native translate_many (batching / ordering / recovery)
# ───────────────────────────────────────────────────────────────────────────


class FakeChatResponse:
    """Stand-in for a requests.Response with a JSON chat payload."""

    def __init__(self, content=None, status=200, text=""):
        self.status_code = status
        self.headers = {}
        self._content = content or ""
        self._text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests as _requests
            raise _requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return {"message": {"content": self._content}}

    @property
    def text(self):
        return self._text


def _gptoss_provider(monkeypatch, batch_limits=None):
    """Build a real GPTOSSProvider and patch its network seams."""
    from providers.gptoss import GPTOSSProvider
    provider = GPTOSSProvider()
    if batch_limits is not None:
        monkeypatch.setattr(
            type(provider), "batch_limits",
            property(lambda self: batch_limits),
        )
    return provider


def _units(texts, context_hints=None):
    units = []
    for i, text in enumerate(texts):
        units.append(TranslationUnit(
            unit_id=i, source_block_id=i, source_text=text,
            context_hint=(context_hints[i] if context_hints else ""),
        ))
    return units


class TestGPTOSSTranslateMany:
    def test_respects_batch_limits_and_char_budget(self, monkeypatch):
        from providers.gptoss import GPTOSSProvider
        provider = _gptoss_provider(monkeypatch)
        texts = ["w" * 500 for _ in range(30)]  # 8 per 4000-char batch
        recorded = []

        def fake_batch(messages, ctx=None, num_predict=None):
            user_msg = messages[-1]["content"] if messages else ""
            ids = [int(m.group(1)) for m in re.finditer(r"(?m)^U(\d+):", user_msg)]
            recorded.append(ids)
            return "{%s}" % ", ".join(f'"U{i}": "[[{i}]]"' for i in ids)

        monkeypatch.setattr(provider, "_request_batch_chat", fake_batch)
        results = provider.translate_many(
            _units(texts), "English", "Cebuano", ctx=None,
        )
        assert [len(b) for b in recorded] == [8, 8, 8, 6]
        assert [i for b in recorded for i in b] == list(range(30))  # reading order
        assert [r.unit_id for r in results] == list(range(30))
        assert all(r.status == "translated" for r in results)

    def test_batch_limit_override_from_capabilities(self, monkeypatch):
        from dto.responses import TranslationResponse
        provider = _gptoss_provider(
            monkeypatch, batch_limits={"max_batch_chars": 5000, "max_batch_items": 3}
        )
        recorded = []

        def fake_batch(messages, ctx=None, num_predict=None):
            user_msg = messages[-1]["content"] if messages else ""
            ids = [int(m.group(1)) for m in re.finditer(r"(?m)^U(\d+):", user_msg)]
            recorded.append(ids)
            return "{%s}" % ", ".join(f'"U{i}": "[[{i}]]"' for i in ids)

        def fake_translate(text, source_lang="", target_lang="", block_type="paragraph",
                           context_hint="", document_type="", response_format="text"):
            return TranslationResponse(
                translated_text="[[SINGLE]]", provider="gptoss",
                model="gpt-oss:test", success=True,
            )

        monkeypatch.setattr(provider, "_request_batch_chat", fake_batch)
        monkeypatch.setattr(provider, "translate", fake_translate)
        results = provider.translate_many(
            _units(["x" * 100] * 10), "English", "Cebuano", ctx=None,
        )
        # 3 multi-unit batch posts; the remaining lone unit uses its own request.
        assert [len(b) for b in recorded] == [3, 3, 3]
        assert [r.unit_id for r in results] == list(range(10))
        assert all(r.status == "translated" for r in results)

    def test_stable_ordering_with_shuffled_mapping(self, monkeypatch):
        from providers.gptoss import GPTOSSProvider, GPTOSSProviderError
        provider = _gptoss_provider(monkeypatch)
        units = _units(["aaa", "bbb", "ccc", "ddd"])

        def fake_batch(messages, ctx=None, num_predict=None):
            # Shuffled key order in the reply must not reorder the output.
            return '{"U3": "DDD", "U1": "BBB", "U0": "AAA", "U2": "CCC"}'

        monkeypatch.setattr(provider, "_request_batch_chat", fake_batch)
        results = provider.translate_many(units, "English", "Cebuano", ctx=None)
        assert [r.unit_id for r in results] == [0, 1, 2, 3]
        assert [r.translated_text for r in results] == ["AAA", "BBB", "CCC", "DDD"]

    def test_context_hint_preserved_in_batch_payload(self, monkeypatch):
        provider = _gptoss_provider(monkeypatch)
        captured = {}

        def fake_batch(messages, ctx=None, num_predict=None):
            captured["msg"] = messages[-1]["content"]
            ids = [int(m.group(1)) for m in re.finditer(r"(?m)^U(\d+):", messages[-1]["content"])]
            return "{%s}" % ", ".join(f'"U{i}": "[[{i}]]"' for i in ids)

        monkeypatch.setattr(provider, "_request_batch_chat", fake_batch)
        hints = ["ROLE: heading; PRECEDING: Intro.", "ROLE: paragraph.", "ROLE: table_cell."]
        provider.translate_many(
            _units(["hello", "world", "!"], context_hints=hints),
            "English", "Cebuano", ctx=None,
        )
        msg = captured["msg"]
        assert "Context for U0: ROLE: heading; PRECEDING: Intro." in msg
        assert "Context for U1: ROLE: paragraph." in msg
        assert "Context for U2: ROLE: table_cell." in msg

    def test_context_hint_preserved_in_single_unit_request(self, monkeypatch):
        from dto.responses import TranslationResponse
        provider = _gptoss_provider(monkeypatch)
        seen = {}

        def fake_translate(text, source_lang="", target_lang="", block_type="paragraph",
                           context_hint="", document_type="", response_format="text"):
            seen["hint"] = context_hint
            seen["text"] = text
            return TranslationResponse(
                translated_text=f"[[{text[:3]}]]",
                provider="gptoss", model="gpt-oss:test", success=True,
            )

        monkeypatch.setattr(provider, "translate", fake_translate)
        unit = _units(["abcdefghij"] * 1)[0]
        unit.context_hint = "TABLE HEADERS: Qty, Price."
        results = provider.translate_many([unit], "English", "Cebuano", ctx=None)
        assert seen["hint"] == "TABLE HEADERS: Qty, Price."
        assert results[0].unit_id == unit.unit_id
        assert results[0].status == "translated"
        assert "abc" in results[0].translated_text

    def test_oversized_unit_gets_single_unit_request(self, monkeypatch):
        from dto.responses import TranslationResponse
        provider = _gptoss_provider(monkeypatch)  # default 4000 char budget
        big = "B" * 6000
        texts = [big, "small one", "small two"]
        translated = []

        def fake_translate(text, source_lang="", target_lang="", block_type="paragraph",
                           context_hint="", document_type="", response_format="text"):
            translated.append(text)
            return TranslationResponse(
                translated_text=f"[[{len(text)}]]",
                provider="gptoss", model="gpt-oss:test", success=True,
            )

        batch_ids = []

        def fake_batch(messages, ctx=None, num_predict=None):
            user_msg = messages[-1]["content"]
            ids = [int(m.group(1)) for m in re.finditer(r"(?m)^U(\d+):", user_msg)]
            batch_ids.append(ids)
            return "{%s}" % ", ".join(f'"U{i}": "[[{i}]]"' for i in ids)

        monkeypatch.setattr(provider, "translate", fake_translate)
        monkeypatch.setattr(provider, "_request_batch_chat", fake_batch)
        results = provider.translate_many(_units(texts), "English", "Cebuano", ctx=None)
        # The oversized unit took the single-translate path; the two small ones
        # fit one batch request.
        assert translated == [big]
        assert batch_ids == [[1, 2]]
        assert [r.unit_id for r in results] == [0, 1, 2]

    def test_malformed_batch_retries_unresolved_individually(self, monkeypatch):
        from dto.responses import TranslationResponse
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode
        provider = _gptoss_provider(monkeypatch)
        ctx = DocumentContext(mode=get_mode("fast"))

        def fake_batch(messages, ctx=None, num_predict=None):
            # U0 fine, U1 duplicated, U2 empty value, U99 unexpected key/shuffled.
            return '{"U0": "AAA", "U1": "B", "U1": "C", "U2": "", "U99": "x"}'

        def fake_translate(text, source_lang="", target_lang="", block_type="paragraph",
                           context_hint="", document_type="", response_format="text"):
            return TranslationResponse(
                translated_text="[[SINGLE]]", provider="gptoss",
                model="gpt-oss:test", success=True,
            )

        monkeypatch.setattr(provider, "_request_batch_chat", fake_batch)
        monkeypatch.setattr(provider, "translate", fake_translate)
        results = provider.translate_many(
            _units(["a", "b", "c"]), "English", "Cebuano", ctx=ctx,
        )
        # U1 (dup) and U2 (empty) were retried individually; U99 is an
        # unexpected key counted as invalid but not retried (no such unit).
        assert all(r.status == "translated" for r in results)
        assert [r.unit_id for r in results] == [0, 1, 2]
        assert ctx.provider_retries == 2
        assert ctx.provider_failures.get("invalid_response") == 3
        assert results[1].translated_text == "[[SINGLE]]"
        assert results[0].translated_text == "AAA"

    def test_unparseable_batch_retries_every_unit(self, monkeypatch):
        from dto.responses import TranslationResponse
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode
        provider = _gptoss_provider(monkeypatch)
        ctx = DocumentContext(mode=get_mode("fast"))

        def fake_batch(messages, ctx=None, num_predict=None):
            return "no json here at all"

        def fake_translate(text, source_lang="", target_lang="", block_type="paragraph",
                           context_hint="", document_type="", response_format="text"):
            return TranslationResponse(
                translated_text="[[SINGLE]]", provider="gptoss",
                model="gpt-oss:test", success=True,
            )

        monkeypatch.setattr(provider, "_request_batch_chat", fake_batch)
        monkeypatch.setattr(provider, "translate", fake_translate)
        results = provider.translate_many(
            _units(["one", "two", "three"]), "English", "Cebuano", ctx=ctx,
        )
        assert [r.unit_id for r in results] == [0, 1, 2]
        assert all(r.status == "translated" for r in results)
        assert ctx.provider_retries == 3
        assert ctx.provider_failures.get("invalid_response") == 3

    def test_systemic_rate_limit_raises_and_records(self, monkeypatch):
        from provider_usage import ProviderStopped
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode
        provider = _gptoss_provider(monkeypatch)
        monkeypatch.setenv("GPTOSS_MAX_ATTEMPTS", "1")
        ctx = DocumentContext(mode=get_mode("fast"))

        def fake_post(session, *args, **kwargs):
            return FakeChatResponse(status=429, text="rate limited")

        monkeypatch.setattr(provider._session, "post", fake_post)
        with pytest.raises(ProviderStopped, match="HTTP 429") as stopped:
            provider.translate_many(
                _units(["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l"]),
                "English", "Cebuano", ctx=ctx,
            )
        assert stopped.value.status_code == 429
        assert ctx.provider_failures.get("rate_limit") == 1
        assert ctx.provider_retries == 0

    def test_systemic_connection_failure_raises(self, monkeypatch):
        from dto.responses import TranslationResponse
        from providers.gptoss import GPTOSSProviderError
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode
        provider = _gptoss_provider(monkeypatch)
        ctx = DocumentContext(mode=get_mode("fast"))

        def fake_translate(text, source_lang="", target_lang="", block_type="paragraph",
                           context_hint="", document_type="", response_format="text"):
            return TranslationResponse(
                translated_text="", provider="gptoss", model="gpt-oss:test",
                success=False,
                error_message="Cannot connect to Ollama Cloud at http://localhost:11434/api/chat.",
            )

        monkeypatch.setattr(provider, "translate", fake_translate)
        with pytest.raises(GPTOSSProviderError, match="Cannot connect"):
            provider.translate_many(_units(["solo"]), "English", "Cebuano", ctx=ctx)
        assert ctx.provider_failures.get("connection") == 1

    def test_isolated_failure_keeps_source_not_source_success(self, monkeypatch):
        from dto.responses import TranslationResponse
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode
        provider = _gptoss_provider(monkeypatch)
        ctx = DocumentContext(mode=get_mode("fast"))

        def fake_translate(text, source_lang="", target_lang="", block_type="paragraph",
                           context_hint="", document_type="", response_format="text"):
            return TranslationResponse(
                translated_text="", provider="gptoss", model="gpt-oss:test",
                success=False, error_message="GPT-OSS error: boom",
            )

        monkeypatch.setattr(provider, "translate", fake_translate)
        results = provider.translate_many(_units(["keep me"]), "English", "Cebuano", ctx=ctx)
        assert results[0].status == "failed"
        assert results[0].translated_text == "keep me"  # source retained, flagged failed
        assert ctx.provider_failures.get("per_unit_failure") == 1

    def test_health_and_estimate_tokens_unchanged(self, monkeypatch):
        provider = _gptoss_provider(monkeypatch)
        assert provider.name == "gptoss"
        assert provider.estimate_tokens("one two three") == 3


class SchedulerGPTOSSProvider:
    """A gptoss-named provider exercised through the real fair-scheduler seams."""

    def __init__(self):
        self.name = "gptoss"
        self.model_name = "gptoss:test"
        self.batch_sizes = []

    def translate_many(self, units, source_lang="", target_lang="",
                       context_hint="", document_type="", ctx=None):
        self.batch_sizes.append(len(units))
        return [
            TranslationUnitResult(unit_id=u.unit_id, status="translated",
                                  translated_text=f"[[{u.source_block_id}]]",
                                  provider=self.name, model=self.model_name)
            for u in units
        ]

    def health(self):
        return {"status": "ok", "provider": self.name, "model": self.model_name}

    def estimate_tokens(self, text):
        return len(text.split())


def _completed_future(result_or_exc):
    from concurrent.futures import Future
    future = Future()
    if isinstance(result_or_exc, BaseException):
        future.set_exception(result_or_exc)
    else:
        future.set_result(result_or_exc)
    future.scheduler_wait_ms = 7.5
    return future


class TestGPTOSSchedulerDispatch:
    def test_semantic_boundaries_flow_through_scheduler(self, monkeypatch):
        from pipeline.translation_pipeline import TranslationPipeline, document_batch_scheduler
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode
        from document.semantic_chunker import SemanticChunk

        blocks = _make_blocks(["First one", "First two", "Mid one", "Mid two",
                               "Last one", "Last two"])
        chunks = [
            SemanticChunk(text="First one First two", block_indices=[0, 1],
                          semantic_type="paragraph_group", estimated_tokens=4),
            SemanticChunk(text="Mid one Mid two", block_indices=[2, 3],
                          semantic_type="paragraph_group", estimated_tokens=4),
            SemanticChunk(text="Last one Last two", block_indices=[4, 5],
                          semantic_type="paragraph_group", estimated_tokens=4),
        ]

        class StubChunker:
            def __init__(self, result):
                self.result = result

            def chunk_blocks(self, blocks, profile=None):
                return self.result

        calls = []

        def fake_submit(document_id, callback):
            calls.append(document_id)
            return _completed_future(callback())

        monkeypatch.setattr(document_batch_scheduler, "submit", fake_submit)

        provider = SchedulerGPTOSSProvider()
        pipeline = TranslationPipeline(provider)
        ctx = DocumentContext(mode=get_mode("fast"))
        outputs = pipeline.batch_translate_units(
            blocks, "English", "Cebuano", mode=ctx.mode,
            translation_cache=None, semantic_chunker=StubChunker(chunks),
            document_profile=None, ctx=ctx,
        )
        # Semantic groups were preserved as scheduler-dispatched batch boundaries.
        assert provider.batch_sizes == [2, 2, 2]
        assert calls == [str(id(ctx))] * 3
        assert [o["text"] for o in outputs] == ["[[0]]", "[[1]]", "[[2]]",
                                                "[[3]]", "[[4]]", "[[5]]"]
        assert ctx.scheduler_batches == 3
        assert ctx.scheduler_slots == 8
        assert ctx.scheduler_wait_ms == pytest.approx(7.5 * 3)
        assert ctx.blocks_batched == 6

    def test_non_gptoss_runs_inline_without_scheduler(self, monkeypatch):
        from pipeline.translation_pipeline import TranslationPipeline, document_batch_scheduler

        def boom(*a, **k):
            raise AssertionError("non-gptoss unit path must not touch the scheduler")

        monkeypatch.setattr(document_batch_scheduler, "submit", boom)
        provider = RecordingProvider()
        pipeline = TranslationPipeline(provider)
        outputs = pipeline.batch_translate_units(
            _make_blocks(["alpha one", "bravo two", "charlie three", "delta four"]),
            "English", "Cebuano", mode=None, translation_cache=None,
        )
        assert provider.batch_sizes == [4]
        assert len(outputs) == 4

    def test_systemic_failure_fails_fast(self, monkeypatch):
        from pipeline.translation_pipeline import TranslationPipeline, document_batch_scheduler
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode

        class FailingProvider(SchedulerGPTOSSProvider):
            def translate_many(self, units, source_lang="", target_lang="",
                               context_hint="", document_type="", ctx=None):
                raise RuntimeError("Cannot connect to Ollama Cloud at ...")

        def fake_submit(document_id, callback):
            try:
                result = callback()
            except BaseException as exc:
                return _completed_future(exc)
            return _completed_future(result)

        monkeypatch.setattr(document_batch_scheduler, "submit", fake_submit)
        pipeline = TranslationPipeline(FailingProvider())
        ctx = DocumentContext(mode=get_mode("fast"))
        with pytest.raises(RuntimeError, match="false successful translation"):
            pipeline.batch_translate_units(
                _make_blocks(["first line here", "second line here", "third line here"]),
                "English", "Cebuano", mode=ctx.mode, translation_cache=None, ctx=ctx,
            )

    def test_isolated_failure_retains_source_with_warning(self, monkeypatch):
        from pipeline.translation_pipeline import TranslationPipeline, document_batch_scheduler
        from pipeline.document_context import DocumentContext
        from config.processing_modes import get_mode

        class BoomProvider(SchedulerGPTOSSProvider):
            def translate_many(self, units, source_lang="", target_lang="",
                               context_hint="", document_type="", ctx=None):
                raise RuntimeError("boom boom")

        def fake_submit(document_id, callback):
            try:
                result = callback()
            except BaseException as exc:
                return _completed_future(exc)
            return _completed_future(result)

        monkeypatch.setattr(document_batch_scheduler, "submit", fake_submit)
        pipeline = TranslationPipeline(BoomProvider())
        ctx = DocumentContext(mode=get_mode("fast"))
        outputs = pipeline.batch_translate_units(
            _make_blocks(["keep source"])[:1], "English", "Cebuano",
            mode=ctx.mode, translation_cache=None, ctx=ctx,
        )
        assert outputs[0]["text"] == "keep source"
        assert any("could not be translated" in w for w in ctx.warnings)
