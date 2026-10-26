"""Mocked AI and generated files: no human review or production acceptance evidence."""
import csv
import json
from pathlib import Path
from unittest.mock import Mock
import fitz
import pytest
from tools.ocr_kit import coordinator as c
from tools.ocr_kit.corpus import digest,save


def packet(tmp_path):
    incoming=tmp_path/'incoming';incoming.mkdir()
    source=incoming/'synthetic.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=600,height=800)
        page.insert_text((48,70),'Native body text')
        page.insert_text((280,770),'1')
        page.insert_text((48,300),'Hidden text must not become a repair',render_mode=3)
        body=page.get_text('blocks')[0]
        doc.save(source)
    regions=[{'id':'body','page':0,'order':0,'bbox':[v*300/72 for v in body[:4]],'text':'Native body text'}]
    save(source.with_suffix('.regions.json'),regions)
    source.with_suffix('.txt').write_text('Native body text',encoding='utf-8')
    with (incoming/'info.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=['file','language','capture_class','content_group_id','split','author','rights_note','material'])
        writer.writeheader();writer.writerow({'file':source.name,'language':'English','split':'calibration',
            'content_group_id':'SYNTHETIC-FIXTURE','material':'test_fixture'})
    save(tmp_path/'workflow.json',{'version':1,'language':'English','calibration_source_sha256':digest(source)})
    return source


def ai(action='prepare_proposals',reason='Prepare the visible missing page number as an unreviewed proposal.'):
    provider=Mock(name='synthetic-provider');provider.name='MOCK-NOT-LIVE';provider.model_name='MOCK-MODEL'
    def analyze(system,user):
        evidence=json.loads(user)
        return {'action':action,'reason':reason,
            'candidate_ids':[x['id'] for x in evidence['candidates']] if action=='prepare_proposals' else [],
            'question_ids':list(evidence['available_questions'])}
    provider.analyze.side_effect=analyze
    return provider


def test_bounded_preparation_adds_visible_footer_only_in_separate_drafts(tmp_path):
    source=packet(tmp_path)
    before={p:p.read_bytes() for p in (tmp_path/'incoming').iterdir()}
    provider=ai(reason='<script>untrusted explanation</script>')
    result=c.coordinate(tmp_path,provider)
    assert result['status']=='proposals_prepared' and result['approval_issued'] is False
    assert [x['text'] for x in result['proposals']]==['1']
    proposal=list(Path(result['run']).glob('*.regions.json'))
    assert len(proposal)==1
    assert [r['text'] for r in json.loads(proposal[0].read_text())]==['Native body text','1']
    assert {p:p.read_bytes() for p in before}==before
    html=(Path(result['run'])/'review.html').read_text()
    assert '&lt;script&gt;' in html and '<script>' not in html
    assert 'Proposed reference text' in html and '../../review.html' in html
    assert not list(tmp_path.rglob('signed-report.json'))
    assert result['live_configuration_changed'] is False


@pytest.mark.parametrize('fault',['approve','unknown_candidate','sign_argument','candidate_on_question',
                                  'unknown_question','empty_question','bad_type','long_reason','bad_unicode'])
def test_ai_cannot_expand_its_permissions(tmp_path,fault):
    packet(tmp_path);provider=ai();answer=provider.analyze.side_effect
    def invalid(system,user):
        result=answer(system,user)
        if fault=='approve':result['action']='approve_and_sign'
        if fault=='unknown_candidate':result['candidate_ids']=['../../private/key']
        if fault=='sign_argument':result['sign_key_file']='sensitive-file'
        if fault=='candidate_on_question':result['action']='ask_user'
        if fault=='unknown_question':result['question_ids']=['paste_api_key']
        if fault=='empty_question':result.update(action='ask_user',candidate_ids=[],question_ids=[])
        if fault=='bad_type':return ['approve']
        if fault=='long_reason':result['reason']='x'*1501
        if fault=='bad_unicode':result['reason']='\ud800'
        return result
    provider.analyze.side_effect=invalid
    result=c.coordinate(tmp_path,provider)
    assert result['status']=='advice_unavailable' and not result['approval_issued']
    assert not list(Path(result['run']).glob('*.regions.json'))
    assert result['questions']


def test_provider_outage_keeps_human_requirements_and_original_files(tmp_path):
    packet(tmp_path);provider=ai();provider.analyze.side_effect=ConnectionError('TEST offline')
    result=c.coordinate(tmp_path,provider)
    assert result['status']=='advice_unavailable' and result['questions']
    assert result['proposals']==[] and not result['approval_issued']


def test_changes_during_analysis_invalidate_ai_action(tmp_path):
    source=packet(tmp_path);provider=ai();answer=provider.analyze.side_effect
    def changed(system,user):
        source.with_suffix('.txt').write_text('Simulated concurrent human correction')
        return answer(system,user)
    provider.analyze.side_effect=changed
    result=c.coordinate(tmp_path,provider)
    assert result['status']=='advice_unavailable' and result['proposals']==[]
    assert not list(Path(result['run']).glob('*.regions.json'))


def test_heldout_content_is_excluded_from_ai_context(tmp_path):
    source=packet(tmp_path)
    held=source.with_name('heldout.pdf');held.write_bytes(source.read_bytes())
    held.with_suffix('.txt').write_text('PRIVATE HELDOUT REFERENCE MUST NOT BE SENT')
    save(held.with_suffix('.regions.json'),[{'id':'secret','text':'PRIVATE HELDOUT GEOMETRY'}])
    with (source.parent/'info.csv').open('a',encoding='utf-8') as stream:
        stream.write('heldout.pdf,English,scan,UNSEEN-FIXTURE,heldout,,,test_fixture\n')
    provider=ai(action='ask_user')
    result=c.coordinate(tmp_path,provider)
    sent=provider.analyze.call_args.args[1]
    assert 'PRIVATE HELDOUT' not in sent and 'Hidden text must' not in sent
    assert json.loads(sent)['heldout_content_included'] is False
    assert result['status']=='advice_ready'


def test_outside_input_is_rejected_before_provider_call(tmp_path):
    packet(tmp_path)
    info=tmp_path/'incoming/info.csv'
    info.write_text(info.read_text().replace('synthetic.pdf','../workflow.json'))
    provider=ai()
    with pytest.raises(ValueError,match='inside incoming'):c.coordinate(tmp_path,provider)
    provider.analyze.assert_not_called()


def test_schema_check_rejects_more_actions_and_stale_candidate_ids():
    evidence={'candidates':[],'available_questions':{'metadata':'Known question'}}
    with pytest.raises(ValueError):c.validate_decision({'action':[],'reason':'x','candidate_ids':[],'question_ids':[]},evidence)
    with pytest.raises(ValueError):c.validate_decision({'action':'prepare_proposals','reason':'x',
                                                     'candidate_ids':['stale'],'question_ids':[]},evidence)


def test_provider_factory_respects_existing_route_without_starting_server(monkeypatch):
    from ai.gemini_provider import GeminiAnalysisProvider
    from ai.ollama_provider import OllamaAnalysisProvider
    monkeypatch.setenv('ANALYSIS_PROVIDER','gemini');monkeypatch.setenv('GEMINI_API_KEY','TEST-NOT-A-KEY')
    monkeypatch.setenv('ANALYSIS_FALLBACK_PROVIDER','ollama')
    provider=c.configured_provider()
    assert isinstance(provider._primary,GeminiAnalysisProvider) and provider._primary._max_attempts==1
    assert isinstance(provider._fallback,OllamaAnalysisProvider)
    monkeypatch.setenv('ANALYSIS_FALLBACK_PROVIDER','none')
    assert c.configured_provider()._fallback is None
