import csv
from unittest.mock import patch

from dto.requests import DocumentTranslationRequest, TranslationRequest
from dto.responses import TranslationResponse


def test_numeric_names_blanks_and_category_collisions_are_safe(document_pipeline, tmp_path):
    source = tmp_path/'data.csv'
    rows = [['island', 'species', 'time', 'day', 'amount', 'balance', 'notes'],
            ['Dream', 'Chinstrap', 'Lunch', 'Sun', '12.50', '1.25e3', 'Please wash hands'],
            ['Dream', 'Adelie', 'Dinner', 'Thu', '', '-2.0E-4', 'Please wash hands']]
    with source.open('w', encoding='utf-8', newline='') as f:
        csv.writer(f).writerows(rows)
    calls = []
    def translate(text, source_lang, target_lang, **kwargs):
        calls.append((text, kwargs))
        return 'Panihapon' if text in {'Lunch', 'Dinner'} else 'T:' + text
    with patch.object(document_pipeline, '_translate_single', side_effect=translate):
        result = document_pipeline.translate(DocumentTranslationRequest(str(source), 'English', 'Cebuano', mode='fast'))
    assert result.success, result.error_message
    with open(result.output_path, encoding='utf-8', newline='') as f:
        out = list(csv.reader(f))
    assert out[1][:3] == ['Dream', 'Chinstrap', 'Lunch']
    assert out[2][:3] == ['Dream', 'Adelie', 'Dinner']
    assert [r[4] for r in out[1:]] == ['12.50', '']
    assert [r[5] for r in out[1:]] == ['1.25e3', '-2.0E-4']
    assert sum(text == 'Please wash hands' for text, _ in calls) == 1
    assert all(text not in {'Dream', 'Chinstrap', 'Adelie', '12.50'} for text, _ in calls)
    hint = next(kw['context_hint'] for text, kw in calls if text == 'Lunch')
    assert "column 'time'" in hint and 'Dinner' in hint
    assert result.sidecar['content_summary']['status'] == 'partial'
    assert result.sidecar['extraction']['warnings']


def test_contextual_cells_bypass_plain_text_cache(translation_pipeline):
    with patch.object(translation_pipeline, '_get_cache') as get_cache, \
         patch.object(translation_pipeline, '_translate_with_echo_guard', return_value=TranslationResponse(
             translated_text='Domingo', provider='mock', model='mock')):
        result = translation_pipeline.translate(TranslationRequest('Sun', 'English', 'Cebuano',
            context_hint='Weekday category', document_metadata={'skip_cache': True}))
    assert result.translated_text == 'Domingo'
    get_cache.assert_not_called()
