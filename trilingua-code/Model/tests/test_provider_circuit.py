"""R2 protocol tests; SQL locking/CAS still requires native disposable-Postgres verification."""
from unittest.mock import Mock
from types import SimpleNamespace
import pytest
import provider_circuit as circuit
from provider_errors import OperationFailure, ProviderFailure, ProviderStopped


def test_database_outage_refuses_new_work(monkeypatch):
    monkeypatch.setattr(circuit, '_store_factory', Mock(side_effect=ConnectionError('offline')))
    with pytest.raises(OperationFailure) as error:
        circuit.acquire()
    assert error.value.category == 'circuit_storage_unavailable'


def test_persisted_stop_survives_new_collectors(monkeypatch):
    from provider_usage import ollama_post, usage_scope
    monkeypatch.setattr(circuit, 'rpc', Mock(return_value={'allowed': False, 'incident_id': 'persisted', 'version': 4}))
    post = Mock()
    for _ in range(2):
        with pytest.raises(ProviderStopped) as error, usage_scope():
            ollama_post(post, 'http://mock', json={})
        assert error.value.details['incident_id'] == 'persisted'
    post.assert_not_called()


def ticket():
    return {'allowed': True, 'scope': 'ollama', 'incident_id': 'incident', 'version': 7, 'probe_lease': 'lease', 'actor': 'operator'}


def test_finish_passes_exact_incident_version_and_lease(monkeypatch):
    rpc = Mock(return_value=False)
    monkeypatch.setattr(circuit, 'rpc', rpc)
    assert circuit.finish(ticket()) is False
    args = rpc.call_args.args[1]
    assert (args['incident'], args['expected_version'], args['lease']) == ('incident', 7, 'lease')


def test_lease_cancellation_does_not_report_provider_failure(monkeypatch):
    rpc = Mock(return_value=True)
    monkeypatch.setattr(circuit, 'rpc', rpc)
    circuit.finish(ticket(), OperationFailure('lease_lost', 409))
    assert rpc.call_args.args[0] == 'cancel_provider_probe_v1'
    assert 'failure' not in rpc.call_args.args[1]


def test_manual_probe_records_evidence_without_releasing_the_incident(monkeypatch):
    proof = {'incident_id': 'incident', 'version': 8, 'probe_evidence_id': 'proof'}
    rpc = Mock(side_effect=[ticket(), proof])
    monkeypatch.setattr(circuit, 'rpc', rpc)
    with circuit.recovery_lease('incident', 7, 'operator') as leased:
        assert circuit.acquire()['incident_id'] == 'incident'
        circuit.finish(leased)
        assert rpc.call_count == 1
        leased['models'] = [{'model': 'translation', 'purpose': 'translation', 'valid': True},
                            {'model': 'analysis', 'purpose': 'analysis', 'valid': True}]
    assert rpc.call_count == 2
    assert rpc.call_args.args[0] == 'record_provider_probe_v1'
    assert rpc.call_args.args[1]['expected_version'] == 7
    assert leased['validation'] == proof


def test_failed_manual_probe_does_not_release(monkeypatch):
    rpc = Mock(side_effect=[ticket(), True])
    monkeypatch.setattr(circuit, 'rpc', rpc)
    with pytest.raises(ProviderStopped):
        with circuit.recovery_lease('incident', 7, 'operator'):
            raise ProviderStopped('credentials', 401)
    assert rpc.call_args.args[1]['failure']['category'] == 'credentials'


def test_half_open_failure_does_not_retry_or_sleep_while_leased(monkeypatch):
    from provider_usage import ollama_post
    monkeypatch.setattr(circuit, 'acquire', lambda: ticket())
    finish = Mock()
    monkeypatch.setattr(circuit, 'finish', finish)
    sleep = Mock()
    monkeypatch.setattr('provider_usage.time.sleep', sleep)
    reply = Mock(status_code=503, headers={})
    reply.json.return_value = {'error': 'unavailable'}
    post = Mock(return_value=reply)
    with pytest.raises(ProviderFailure):
        ollama_post(post, 'http://mock', json={})
    assert post.call_count == 1
    assert finish.call_count == 1
    sleep.assert_not_called()
