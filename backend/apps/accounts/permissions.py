from rest_framework import permissions

class IsFirmMember(permissions.BasePermission):
    """Allows access only to authenticated users belonging to a firm."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.firm or request.user.is_superuser))


class IsAdminOrSuperAdmin(permissions.BasePermission):
    """Allows access only to Firm Admin or Superadmin."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return request.user.is_admin or request.user.is_superuser


class IsSuperAdmin(permissions.BasePermission):
    """Allows access only to Superadmin."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return request.user.is_superadmin or request.user.is_superuser


class IsAdminOrReadOnly(permissions.BasePermission):
    """Read for every firm member; create / edit / delete for Admin+ only (spec §2.2)."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        allowed = bool(request.user.is_admin or request.user.is_superuser)
        if not allowed:
            from apps.common.logging import log_permission_denied
            log_permission_denied(request.user, f'{getattr(view, "basename", "?")}.{request.method.lower()}',
                                  getattr(view, 'basename', ''), view.kwargs.get('pk', ''), 'read-only for staff')
        return allowed
