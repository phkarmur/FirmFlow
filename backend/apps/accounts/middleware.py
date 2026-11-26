from django.http import JsonResponse
from apps.common.logging import log_event

# API paths a user with a temporary password can still use
_ALLOWED = ('/api/v1/auth/me/', '/api/v1/auth/logout/', '/api/v1/auth/change_password/', '/api/v1/auth/login/')


class PasswordChangeRequiredMiddleware:
    """When an admin gave the user a temporary password (User.must_change_password), block every
    other API call until the user sets a new password. The UI shows the change-password screen."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (user is not None and user.is_authenticated and getattr(user, 'must_change_password', False)
                and request.path.startswith('/api/') and not request.path.startswith(_ALLOWED)):
            log_event('auth.password_change_required', 'User', user.id, result='denied', level='INFO', path=request.path)
            return JsonResponse({'error': 'You must set a new password first.', 'code': 'password_change_required'}, status=403)
        return self.get_response(request)
