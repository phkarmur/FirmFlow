import time
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.db import connection
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import smtplib
from django.conf import settings

from apps.common.logging import log_event


def _err(exc):
    # /healthz is public: the error text (host names, paths) shows only when DEBUG is on; the log always has it
    return f'error: {exc}' if settings.DEBUG else 'error (see server log)'


_HEALTH_CACHE = {
    'timestamp': 0,
    'data': None,
    'status_code': 200,
}

class HealthCheckView(APIView):
    """
    Health check endpoint verifying:
    - Database connection
    - Storage write capability
    - SMTP server reachable
    Cached for 60 seconds.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        now = time.time()
        # 60s cache
        if _HEALTH_CACHE['data'] and (now - _HEALTH_CACHE['timestamp'] < 60):
            return Response(_HEALTH_CACHE['data'], status=_HEALTH_CACHE['status_code'])

        checks = {}
        all_ok = True

        # 1. Database check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
                checks['database'] = 'ok' if row and row[0] == 1 else 'fail'
        except Exception as e:
            checks['database'] = _err(e)
            all_ok = False

        # 2. Storage write check
        try:
            test_path = 'healthz_probe.txt'
            default_storage.save(test_path, ContentFile(b'ok'))
            default_storage.delete(test_path)
            checks['storage'] = 'ok'
        except Exception as e:
            checks['storage'] = _err(e)
            all_ok = False

        # 2b. Private storage (task attachments) write check
        try:
            from apps.common.storage import private_storage
            ps = private_storage()
            name = ps.save('healthz_probe.txt', ContentFile(b'ok'))
            ps.delete(name)
            checks['private_storage'] = 'ok'
        except Exception as e:
            checks['private_storage'] = _err(e)
            all_ok = False

        # 2c. Redis (Celery broker). Required when e-mails / jobs run through Celery
        # (setting HEALTH_REQUIRE_REDIS, default = NOTIFY_EMAIL_ASYNC); otherwise only reported.
        try:
            import redis
            broker = getattr(settings, 'CELERY_BROKER_URL', '')
            if broker.startswith('redis'):
                redis.Redis.from_url(broker, socket_connect_timeout=2, socket_timeout=2).ping()
                checks['redis'] = 'ok'
            else:
                checks['redis'] = 'not used'
        except Exception as e:
            checks['redis'] = _err(e)
            if getattr(settings, 'HEALTH_REQUIRE_REDIS', False):
                all_ok = False
            else:
                checks['redis_warning'] = True

        # 3. SMTP connectivity check
        try:
            if settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend':
                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=3)
                server.quit()
                checks['smtp'] = 'ok'
            else:
                checks['smtp'] = 'ok (dev backend)'
        except Exception as e:
            checks['smtp'] = _err(e)
            # Do not completely fail healthcheck in local dev if mailpit is not up yet
            checks['smtp_warning'] = True

        status_code = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        payload = {
            'status': 'healthy' if all_ok else 'unhealthy',
            'checks': checks,
            'timestamp': now,
        }

        log_event('healthz', 'System', '', result='ok' if all_ok else 'error',
                  level='INFO' if all_ok else 'ERROR', **{k: str(v) for k, v in checks.items()})
        _HEALTH_CACHE['timestamp'] = now
        _HEALTH_CACHE['data'] = payload
        _HEALTH_CACHE['status_code'] = status_code

        return Response(payload, status=status_code)


class RootApiView(APIView):
    """
    Root endpoint for FirmFlow backend API.
    If requested from a web browser, seamlessly redirects to Swagger interactive docs.
    If requested with application/json, returns API status and core routes.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        accept_header = request.META.get('HTTP_ACCEPT', '')
        if 'text/html' in accept_header:
            from django.shortcuts import redirect
            return redirect('/api/docs/')
        return Response({
            'app': 'FirmFlow — CA Practice Management API',
            'version': '1.0.0',
            'status': 'healthy',
            'endpoints': {
                'docs': '/api/docs/',
                'health': '/healthz',
                'admin': '/admin/',
                'auth': '/api/v1/auth/',
                'tasks': '/api/v1/tasks/',
                'clients': '/api/v1/clients/',
                'services': '/api/v1/services/',
                'reports': '/api/v1/reports/',
            },
            'frontend_url': 'http://localhost:5173'
        })

