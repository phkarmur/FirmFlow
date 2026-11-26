"""
Login and password-reset protection (Phase C).

Rules (settings, can be changed with environment variables):
- LOGIN_MAX_FAILURES (10) failed logins for one e-mail in LOGIN_LOCKOUT_MINUTES (15) -> that e-mail is
  locked for the rest of the window. The same message is given for unknown e-mails, so the lock does not
  tell if an account exists.
- LOGIN_MAX_FAILURES_PER_IP (50) failed logins from one IP address in the same window -> that IP is locked.
- PASSWORD_RESET_MAX_PER_HOUR (5) reset requests for one e-mail per hour.
Every decision writes a structured log line ("auth.*").
"""
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from apps.common.logging import log_event
from .models import AuthThrottle


def client_ip(request) -> str:
    # Behind nginx the real address is in X-Forwarded-For (first entry). Only trusted when the
    # setting TRUST_X_FORWARDED_FOR is on, because a client can send this header itself.
    if getattr(settings, 'TRUST_X_FORWARDED_FOR', False):
        fwd = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if fwd:
            return fwd.split(',')[0].strip()[:64]
    return (request.META.get('REMOTE_ADDR') or '')[:64]


def _window():
    return timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)


def _cleanup():
    AuthThrottle.objects.filter(created_at__lt=timezone.now() - timedelta(days=1)).delete()


def login_locked(email: str, ip: str):
    """Return (locked, reason). reason is 'email' or 'ip' (for logs only, never shown to the user)."""
    since = _window()
    by_email = AuthThrottle.objects.filter(kind=AuthThrottle.KIND_LOGIN_FAIL, key=email, created_at__gte=since).count()
    if by_email >= settings.LOGIN_MAX_FAILURES:
        return True, 'email'
    if ip:
        by_ip = AuthThrottle.objects.filter(kind=AuthThrottle.KIND_LOGIN_FAIL, ip=ip, created_at__gte=since).count()
        if by_ip >= settings.LOGIN_MAX_FAILURES_PER_IP:
            return True, 'ip'
    return False, ''


def record_login_failure(email: str, ip: str):
    _cleanup()
    AuthThrottle.objects.create(kind=AuthThrottle.KIND_LOGIN_FAIL, key=email, ip=ip)
    count = AuthThrottle.objects.filter(kind=AuthThrottle.KIND_LOGIN_FAIL, key=email, created_at__gte=_window()).count()
    log_event('auth.login', 'User', '', result='error', level='WARNING', email=email, ip=ip,
              failures_in_window=count, limit=settings.LOGIN_MAX_FAILURES)
    return count


def clear_login_failures(email: str):
    deleted, _ = AuthThrottle.objects.filter(kind=AuthThrottle.KIND_LOGIN_FAIL, key=email).delete()
    return deleted


def reset_request_allowed(email: str, ip: str) -> bool:
    since = timezone.now() - timedelta(hours=1)
    n = AuthThrottle.objects.filter(kind=AuthThrottle.KIND_RESET_REQUEST, key=email, created_at__gte=since).count()
    if n >= settings.PASSWORD_RESET_MAX_PER_HOUR:
        return False
    _cleanup()
    AuthThrottle.objects.create(kind=AuthThrottle.KIND_RESET_REQUEST, key=email, ip=ip)
    return True


def lockout_message():
    return (f'Too many failed sign-in attempts. Wait {settings.LOGIN_LOCKOUT_MINUTES} minutes and try again, '
            'or use "Forgot password".')
