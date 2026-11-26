"""
Structured JSON logging helpers (spec §10).

Every write path calls log_event() at the service layer, so the same line
is written whether the call came from the UI, the API or the scheduler.
The request id is kept in a context variable that RequestLoggingMiddleware sets.
"""
import json
import logging
import contextvars
from django.utils import timezone

_request_id = contextvars.ContextVar('firmflow_request_id', default=None)
_actor_id = contextvars.ContextVar('firmflow_actor_id', default=None)

logger = logging.getLogger('firmflow.structured')


def set_request_context(request_id=None, actor_user_id=None):
    _request_id.set(request_id)
    _actor_id.set(str(actor_user_id) if actor_user_id else None)


def get_request_id():
    return _request_id.get()


def _safe(value):
    """Make a value JSON safe (UUIDs, dates, sets, model objects)."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe(v) for v in value]
    return str(value)


def log_event(action, entity_type='', entity_id='', result='ok', level='INFO',
              actor_user_id=None, duration_ms=None, **detail):
    """
    Write one structured log line.
    MUST NOT receive PAN, full GSTIN, passwords, tokens or file contents.
    """
    entry = {
        'ts': timezone.now().isoformat(),
        'level': level,
        'request_id': get_request_id(),
        'actor_user_id': str(actor_user_id) if actor_user_id else _actor_id.get(),
        'action': action,
        'entity_type': entity_type,
        'entity_id': str(entity_id) if entity_id else '',
        'result': result,
        'duration_ms': duration_ms,
        'detail': _safe(detail),
    }
    lvl = getattr(logging, level, logging.INFO)
    logger.log(lvl, json.dumps(entry, default=str))
    return entry


def log_permission_denied(actor, action, entity_type='', entity_id='', reason=''):
    """Spec §10: the most useful line for 'I cannot see my task' tickets."""
    return log_event(
        'permission.denied', entity_type=entity_type, entity_id=entity_id,
        result='error', level='WARNING',
        actor_user_id=getattr(actor, 'id', None),
        denied_action=action, reason=reason,
        actor_role=getattr(actor, 'system_role', None),
    )
