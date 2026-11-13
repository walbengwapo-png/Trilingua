"""Two synthetic probes only; successful validation must never release the incident."""
from unittest.mock import Mock
from uuid import uuid4
import pytest
import server
import provider_circuit


def reply(content=None, status=200):
    response = Mock(status_code=status, headers={})
    response.json.return_value = {'message': {'content': content}} if status == 200 else {'error': 'Unauthorized'}
    return response


@pytest.fixture
def probes(monkeypatch):
    monkeypatch.setenv('OLLAMA_CLOUD_MODEL', 'gpt-oss:20b')
    monkeypatch.setenv('OLLAMA_ANALYSIS_MODEL', 'gemma4:31b')
    monkeypatch.setenv('OLLAMA_CLOUD_URL', 'http://provider.invalid/api/chat')
    incident = str(uuid4())
    ticket = {'allowed': True, 'scope': 'ollama', 'incident_id': incident, 'version': 1, 'probe_lease': str(uuid4())}
    proof = {'incident_id': incident, 'version': 2, 'probe_evidence_id': str(uuid4())}
    rpc = Mock(side_effect=[ticket, proof])
    monkeypatch.setattr(provider_circuit, 'rpc', rpc)
    post = Mock(side_effect=[reply('Magandang umaga.'), reply('{"ok":true}')])
    monkeypatch.setattr('requests.post', post)
    return {'incident': incident, 'version': 1, 'actor': 'test-operator'}, rpc, post


def test_both_successful_probes_record_evidence_without_releasing(probes):
    payload, rpc, post = probes
    result = server.recover_provider(payload)
    assert result['status'] == 'validated_awaiting_approval'
    assert post.call_count == 2
    assert [call.kwargs['json']['model'] for call in post.call_args_list] == ['gpt-oss:20b', 'gemma4:31b']
    assert post.call_args_list[1].kwargs['json']['format'] == 'json'
    assert [call.args[0] for call in rpc.call_args_list] == ['lease_provider_recovery_v1', 'record_provider_probe_v1']


def test_hard_failure_stops_after_one_request(probes):
    payload, rpc, post = probes
    post.side_effect = [reply(status=401)]
    with pytest.raises(server.UsageHTTPException) as error:
        server.recover_provider(payload)
    assert error.value.error_details['original_status'] == 401
    assert post.call_count == 1
    assert rpc.call_args.args[0] == 'finish_provider_circuit_v1'
    assert rpc.call_args.args[1]['failure']['category'] == 'credentials'


def test_nonempty_but_invalid_analysis_cannot_validate(probes):
    payload, rpc, post = probes
    post.side_effect = [reply('Magandang umaga.'), reply('Not structured output')]
    with pytest.raises(server.UsageHTTPException) as error:
        server.recover_provider(payload)
    assert error.value.error_details['category'] == 'probe_output_invalid'
    assert error.value.error_details['original_status'] == 200
    assert post.call_count == 2
    assert rpc.call_args.args[0] == 'finish_provider_circuit_v1'


def test_different_configured_models_send_no_probe(probes, monkeypatch):
    payload, rpc, post = probes
    monkeypatch.setenv('OLLAMA_ANALYSIS_MODEL', 'unapproved-model')
    with pytest.raises(server.HTTPException) as error:
        server.recover_provider(payload)
    assert error.value.status_code == 409
    post.assert_not_called()
    rpc.assert_not_called()
