"""Safe, serializable failures shared by transport, pipelines and the queue."""
import re
from uuid import uuid4


class ProviderFailure(RuntimeError):
    systemic = True

    def __init__(self, category, status_code=503, *, details=None):
        self.category = category
        self.status_code = status_code
        self.details = dict(details or {})
        self.details.setdefault('reference_id', str(uuid4()))
        self.details.update(category=category, status_code=status_code)
        super().__init__(f"Translation service could not complete this request. Reference: {self.details['reference_id']}")


class ProviderStopped(ProviderFailure):
    def __init__(self, message='provider_blocked', status_code=503, *, details=None):
        # The former free-text argument is never made public or used for classification.
        super().__init__(message if message in ('credentials', 'billing', 'quota_exhausted', 'permission',
                                               'provider_blocked', 'operator_review') else 'provider_blocked',
                         status_code or 503, details=details)


class OperationFailure(ProviderFailure):
    systemic = False


def safe_excerpt(data, request=None):
    """Only error fields; never retain successful content, prompts or headers."""
    import json
    error = data.get('error') if isinstance(data, dict) else None
    if isinstance(error, dict):
        error = {key: error[key] for key in ('code', 'type', 'message') if key in error}
    text = json.dumps(error, ensure_ascii=False) if error is not None else '[response body withheld]'
    original = text
    for message in (request or {}).get('messages', []):
        content = message.get('content') if isinstance(message, dict) else None
        if isinstance(content, str) and content:
            text = text.replace(content, '[REDACTED]')
            text = text.replace(json.dumps(content, ensure_ascii=False)[1:-1], '[REDACTED]')
    text = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|authorization|token)\s*[:=]\s*)[^\s,;"}]+',
                  r'\1[REDACTED]', text)
    return {'body_excerpt': text[:1024], 'body_redacted': text != original,
            'body_truncated': len(text) > 1024}


def classify(status, data):
    error = data.get('error', '') if isinstance(data, dict) else ''
    code = error.get('code', error.get('type', '')) if isinstance(error, dict) else ''
    text = str(error).lower()
    details = {'original_status': status, 'provider_error_code': str(code)[:128] or None}
    if status in (401, 402, 403):
        return ProviderStopped({401: 'credentials', 402: 'billing', 403: 'permission'}[status], status, details=details)
    if status == 429 and (str(code).lower() in ('insufficient_quota', 'quota_exhausted', 'billing_hard_limit_reached')
                          or any(term in text for term in ('quota exhausted', 'quota exceeded', 'usage allowance exhausted',
                                                          'insufficient quota'))):
        return ProviderStopped('quota_exhausted', status, details=details)
    if status == 429 or status in (500, 502, 503, 504):
        return ProviderFailure('rate_limited' if status == 429 else 'upstream_unavailable', status, details=details)
    if status >= 400 or error:
        return OperationFailure('input_limit' if any(term in text for term in
                                ('context length', 'context window', 'too many tokens', 'input too long'))
                                else 'upstream_rejected', status if status >= 400 else 422, details=details)
    return None
