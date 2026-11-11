"""Saved analysis and final-output review regressions; no external providers."""
from unittest.mock import Mock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.processing_modes import BALANCED, FAST
from document.document_analyzer import DocumentProfile
from document.regenerator import finalize_sidecar
from dto.requests import DocumentTranslationRequest
from pipeline.document_context import DocumentContext
from validators.ai_quality_reviewer import QualityReview


def test_sidecar_retains_bounded_analysis_and_review_coverage():
    ctx = DocumentContext(mode=BALANCED)
    ctx.document_profile = DocumentProfile('legal_contract', 'formal', 'English', .9,
        total_blocks=3, total_words=40, terminology=['term'] * 100)
    ctx.prepass_domain = 'legal'
    ctx.prepass_summary = 'Contract summary'
    entries = [
        {'source_text': 'First block', 'quality_score': 85},
        {'source_text': 'Second block', 'quality_score': None},
        {'source_text': 'Logo', 'passthrough': True},
    ]
    sidecar = finalize_sidecar(entries, DocumentTranslationRequest('x.docx', 'English', 'Cebuano'), '.docx', ctx)
    assert sidecar['analysis']['domain'] == 'legal'
    assert sidecar['analysis']['summary'] == 'Contract summary'
    assert sidecar['analysis']['extracted_blocks'] == 3
    assert len(sidecar['analysis']['terminology']) == 50
    assert sidecar['quality_review'] == {'status': 'partial', 'reason': None, 'eligible_blocks': 2, 'scored_blocks': 1}
    assert sidecar['blocks'] is entries


def test_final_review_scores_cached_and_changed_output_without_reusing_stale_score(document_pipeline):
    ctx = DocumentContext(mode=BALANCED)
    ctx.record_block_quality(0, 99, [], 'Earlier translation')
    ctx.record_block_quality(2, 90, [], 'Already reviewed')
    sources = [{'text': 'First source'}, {'text': 'Cached source'}, {'text': 'Third source'}]
    blocks = [{'text': 'Changed output', 'quality_score': 99}, {'text': 'Cached output'}, {'text': 'Already reviewed'}]
    reviewer = Mock()
    reviewer.batch_review.return_value = {0: QualityReview(80), 1: QualityReview(85)}
    document_pipeline._quality_reviewer = reviewer
    document_pipeline._review_final_blocks(sources, blocks, ctx)
    assert [b['quality_score'] for b in blocks] == [80, 85, 90]
    assert reviewer.batch_review.call_args.args[0] == [(0, 'First source', 'Changed output'), (1, 'Cached source', 'Cached output')]


def test_final_review_failure_preserves_output_without_stale_score(document_pipeline):
    ctx = DocumentContext(mode=BALANCED)
    ctx.record_block_quality(0, 99, [], 'Old text')
    blocks = [{'text': 'Saved new text', 'quality_score': 99}]
    document_pipeline._quality_reviewer = Mock()
    document_pipeline._quality_reviewer.batch_review.side_effect = RuntimeError('offline')
    document_pipeline._review_final_blocks([{'text': 'Source'}], blocks, ctx)
    assert blocks[0]['text'] == 'Saved new text'
    assert blocks[0]['quality_score'] is None


def test_disabled_review_remains_explicit_and_analysis_is_not_fabricated():
    ctx = DocumentContext(mode=FAST)
    sidecar = finalize_sidecar([{'source_text': 'Some text'}], DocumentTranslationRequest('x.txt', 'English', 'Cebuano'), '.txt', ctx)
    assert sidecar['quality_review']['reason'] == 'review_disabled'
    assert sidecar['analysis']['status'] == 'not_run'
    assert 'confidence' not in sidecar['analysis']
