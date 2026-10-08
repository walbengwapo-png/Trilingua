# -*- coding: utf-8 -*-
"""
Isolation tests for the admin regeneration sidecar.

Verifies the Phases 1-3 Python scope WITHOUT touching the Laravel layers:

1. A /translate/document run populates a JSON sidecar on the response
   (document context, format, languages, per-block entries).
2. `reconstruct_from_sidecar` re-renders an edited document using ONLY
   reconstruction code — it must NOT invoke the analyzer, prepass,
   quality reviewer, or translation provider again.
3. Block capture carries review fields (source/ai/current text, quality).

The whole point of the sidecar design is that admin edits re-render the
document with no re-translation. These tests assert exactly that isolation.

Run:
    python -m pytest trilingua-code/Model/tests/test_regeneration.py -v
"""

import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from dto.requests import DocumentTranslationRequest
from document.regenerator import (
    finalize_sidecar,
    rich_block_entry,
    inplace_block_entry,
    reconstruct_from_sidecar,
    apply_overrides,
)


_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


# ===========================================================================
# Sidecar shape
# ===========================================================================

def test_response_carries_sidecar_and_blocks(document_pipeline):
    """A translated document response now exposes sidecar + blocks."""
    fixture = os.path.join(_FIXTURES, "golden_short.txt")
    request = DocumentTranslationRequest(
        file_path=fixture, source_lang="English", target_lang="Cebuano",
    )
    response = document_pipeline.translate(request)

    assert response.success, response.error_message
    assert response.sidecar is not None, "sidecar must be populated"
    assert "version" in response.sidecar
    assert response.sidecar["format"].lower() == ".txt"
    assert response.sidecar["source_lang"] == "English"
    assert response.sidecar["target_lang"] == "Cebuano"
    assert "blocks" in response.sidecar
    assert len(response.blocks) == len(response.sidecar["blocks"])


def test_rich_block_entry_shape(document_pipeline):
    """Structural metadata + review fields land on text path blocks."""
    fixture = os.path.join(_FIXTURES, "golden_short.txt")
    request = DocumentTranslationRequest(
        file_path=fixture, source_lang="English", target_lang="Cebuano",
    )
    response = document_pipeline.translate(request)
    assert response.blocks, "expected at least one block"

    b = response.blocks[0]
    for key in ("block_index", "block_type", "source_text",
                "ai_translated_text", "current_text"):
        assert key in b, f"missing review field {key}"


# ===========================================================================
# reconstruct_from_sidecar — isolation guarantee
# ===========================================================================

@pytest.fixture
def short_sidecar(document_pipeline):
    """Translate a fixture and return its sidecar dict."""
    fixture = os.path.join(_FIXTURES, "golden_short.txt")
    request = DocumentTranslationRequest(
        file_path=fixture, source_lang="English", target_lang="Cebuano",
    )
    response = document_pipeline.translate(request)
    assert response.success, response.error_message
    return response.sidecar


def test_reconstruct_uses_only_reconstruction(document_pipeline):
    """Reconstruction-only: no analyzer / prepass / provider re-runs."""
    from unittest import mock

    fixture = os.path.join(_FIXTURES, "golden_short.txt")
    request = DocumentTranslationRequest(
        file_path=fixture, source_lang="English", target_lang="Cebuano",
    )
    response = document_pipeline.translate(request)
    assert response.success, response.error_message

    # Spy on translation pipeline + analyzer to prove they are NOT called.
    spy_translate = mock.patch.object(
        document_pipeline.translation_pipeline, "translate", autospec=True)
    spy_batch = mock.patch.object(
        document_pipeline.translation_pipeline, "batch_translate_blocks", autospec=True)
    spy_prepass = mock.patch.object(
        document_pipeline, "_execute_prepass_concurrent", autospec=True)

    with spy_translate as t, spy_batch as b, spy_prepass as p:
        out_fd, out_path = tempfile.mkstemp(suffix=".txt")
        os.close(out_fd)

        reconstruct_from_sidecar(
            response.sidecar,
            overrides={"0": "EDITED FIRST BLOCK"},
            original_file=None,      # text formats don't need the original
            output_file=out_path,
            source_lang="English",
            target_lang="Cebuano",
        )

        assert os.path.exists(out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            text = f.read()
        assert "EDITED FIRST BLOCK" in text

        t.assert_not_called()
        b.assert_not_called()
        p.assert_not_called()
        os.remove(out_path)


def test_apply_overrides_is_pure(document_pipeline, tmp_path):
    """apply_overrides returns new dicts and overlays 'text', keeps source."""
    blocks = [
        {"block_index": 0, "text": "alpha", "current_text": "alpha", "source_text": "a"},
        {"block_index": 1, "text": "beta",  "current_text": "beta",  "source_text": "b"},
    ]
    out = apply_overrides(blocks, {1: "BETA-EDITED"})

    assert out[0] is not blocks[0], "must not mutate original list items"
    assert out[1]["text"] == "BETA-EDITED"
    assert out[1]["current_text"] == "BETA-EDITED"
    assert out[1]["source_text"] == "b"
    assert blocks[1]["text"] == "beta", "original untouched"


# ===========================================================================
# Sidecar builders (unit-level, no pipeline needed)
# ===========================================================================

def test_rich_block_entry_carries_structure():
    tb = {
        "type": "paragraph",
        "text": "Translated",
        "position": [1, 2, 3, 4],
        "page": 0,
        "lines": [{"spans": [{"text": "source line"}]}],
        "quality_score": 88.0,
        "quality_issues": [{"severity": "high"}],
    }
    entry = rich_block_entry(3, tb, "Original")
    assert entry["block_index"] == 3
    assert entry["source_text"] == "Original"
    assert entry["ai_translated_text"] == "Translated"
    assert entry["current_text"] == "Translated"
    assert entry["quality_score"] == 88.0
    assert entry["position"] == [1, 2, 3, 4]
    assert "lines" in entry


def test_inplace_block_entry_no_structure():
    entry = inplace_block_entry(0, "paragraph", "src", "tgt")
    assert entry["block_index"] == 0
    assert entry["source_text"] == "src"
    assert entry["ai_translated_text"] == "tgt"
    assert "text" not in entry, "in-place entries carry no structural text"