from document.pdf_regions import completed_status


def test_untranslated_prose_is_not_a_successful_passthrough():
    assert completed_status({'source_text': 'Wash your hands before eating.',
                             'text': 'Wash your hands before eating.'}) == 'held'
    assert completed_status({'source_text': 'Home Language Survey',
                             'text': 'Home Language Survey', 'block_type': 'heading'}) == 'held'
    assert completed_status({'source_text': 'Missing text'}) == 'held'
    assert completed_status({'source_text': 'https://example.org', 'text': 'https://example.org'}) == 'passthrough'
    assert completed_status({'source_text': 'Agency logo', 'text': 'Agency logo', 'passthrough': True}) == 'passthrough'


def test_echoed_region_produces_partial_output_and_a_visible_reason(document_pipeline, tmp_path):
    output = tmp_path/'output.pdf'
    output.write_bytes(b'pdf fixture')
    entries = [{'region_id': 'translated', 'source_text': 'Good morning', 'text': 'Maayong buntag'},
               {'region_id': 'echoed', 'source_text': 'Please wash your hands.', 'text': 'Please wash your hands.'}]
    sidecar = {'blocks': entries}
    extraction = {'original_sha256': '0'*64, 'pages': [], 'warnings': [], 'regions': [
        {'region_id': 'translated', 'page': 0, 'status': 'pending'},
        {'region_id': 'echoed', 'page': 0, 'status': 'pending'}]}
    from unittest.mock import patch
    with patch('document.render_plan.make_plan', return_value={}):
        path = document_pipeline._pdf_sidecar(sidecar, extraction, {}, str(output))
    assert path.endswith('_partial.pdf')
    assert sidecar['content_summary']['status'] == 'partial'
    assert sidecar['content_summary']['held'] == 1
    assert extraction['regions'][1]['reason'] == 'source_text_unchanged'
    assert entries[1]['current_text'] == 'Please wash your hands.'
