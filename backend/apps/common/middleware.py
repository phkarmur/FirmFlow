import time
import uuid
from apps.common.logging import log_event, set_request_context

# Paths that are too noisy to log on every request
_SKIP_PREFIXES = ('/static/', '/media/', '/favicon.ico')


class RequestLoggingMiddleware:
    """
    Structured JSON request logging (spec §10).
    - Reads or creates X-Request-ID, stores it in a context variable for
      service-layer log lines, and returns it in the response header.
    - Writes one 'http.request' line per request.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        # Limit header length to stop log injection with very long ids
        request_id = request_id[:64]
        request.request_id = request_id
        user = getattr(request, 'user', None)
        actor = user.id if user is not None and getattr(user, 'is_authenticated', False) else None
        set_request_context(request_id, actor)
        start_time = time.monotonic()

        response = self.get_response(request)

        duration_ms = round((time.monotonic() - start_time) * 1000, 2)
        response['X-Request-ID'] = request_id

        if not request.path.startswith(_SKIP_PREFIXES):
            user = getattr(request, 'user', None)
            actor = user.id if user is not None and getattr(user, 'is_authenticated', False) else None
            status_code = response.status_code
            level = 'INFO' if status_code < 400 else ('WARNING' if status_code < 500 else 'ERROR')
            log_event(
                'http.request', result='ok' if status_code < 400 else 'error', level=level,
                actor_user_id=actor, duration_ms=duration_ms,
                method=request.method, path=request.path, status_code=status_code,
            )
        set_request_context(None, None)
        return response
