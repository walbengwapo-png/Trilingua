"""Database-authoritative Ollama circuit. There is no process-local allow fallback."""
from contextlib import contextmanager
from contextvars import ContextVar

from provider_errors import OperationFailure, ProviderFailure, ProviderStopped

_recovery = ContextVar('provider_recovery_ticket', default=None)


def _store_factory():
    from document_jobs import DocumentJobStore
    return DocumentJobStore()


def rpc(name, values):
    try:
        return _store_factory().request('POST', '/rest/v1/rpc/' + name, json=values).json()
    except Exception as error:
        raise OperationFailure('circuit_storage_unavailable', 503) from error


def acquire():
    recovery = _recovery.get()
    if recovery:
        return recovery
    ticket = rpc('acquire_provider_circuit_v1', {'circuit_scope': 'ollama'})
    if not isinstance(ticket, dict) or not ticket.get('allowed'):
        raise ProviderStopped('provider_blocked', 503, details={
            'incident_id': (ticket or {}).get('incident_id'), 'version': (ticket or {}).get('version'),
            'original_error': (ticket or {}).get('original_error')})
    return ticket


def finish(ticket, failure=None):
    # Operation-local refusals (lost lease, input, budget) cannot create incidents.
    if isinstance(failure, OperationFailure):
        if ticket.get('probe_lease'):
            rpc('cancel_provider_probe_v1', {'circuit_scope': ticket['scope'], 'incident': ticket['incident_id'],
                'expected_version': ticket['version'], 'lease': ticket['probe_lease']})
        return
    if _recovery.get():
        return  # Both configured models must pass before manual recovery releases the incident.
    if failure is None and not ticket.get('probe_lease'):
        return
    return _finish(ticket, failure)


def _finish(ticket, failure=None):
    return rpc('finish_provider_circuit_v1', {
        'circuit_scope': ticket['scope'], 'incident': ticket['incident_id'],
        'expected_version': ticket['version'], 'lease': ticket.get('probe_lease'),
        'failure': failure.details if failure else None, 'actor': ticket.get('actor')})


@contextmanager
def recovery_lease(incident, version, actor):
    ticket = rpc('lease_provider_recovery_v1', {'circuit_scope': 'ollama', 'incident': str(incident),
                 'expected_version': version, 'actor': actor})
    if not ticket.get('allowed'):
        raise OperationFailure('stale_recovery_or_probe_busy', 409)
    token = _recovery.set(ticket)
    ticket['models'] = []
    try:
        yield ticket
    except ProviderFailure as failure:
        _finish(ticket, failure)
        raise
    except Exception:
        _finish(ticket, ProviderFailure('recovery_probe_failed', 503))
        raise
    else:
        ticket['validation'] = rpc('record_provider_probe_v1', {
            'circuit_scope': ticket['scope'], 'incident': ticket['incident_id'],
            'expected_version': ticket['version'], 'lease': ticket['probe_lease'], 'models': ticket['models']})
    finally:
        _recovery.reset(token)
