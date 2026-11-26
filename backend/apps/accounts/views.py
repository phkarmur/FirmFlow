from rest_framework import views, viewsets, status, permissions, serializers
from rest_framework.exceptions import PermissionDenied
from apps.common.logging import log_event, log_permission_denied
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.utils import timezone
from .models import User, Firm, Branch
from .serializers import UserSerializer, UserCreateSerializer, FirmSerializer, BranchSerializer, LoginSerializer
from .permissions import IsFirmMember, IsAdminOrSuperAdmin, IsSuperAdmin
from apps.common.models import AuditLog

@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].lower()
        password = serializer.validated_data['password']
        from .security import client_ip, login_locked, record_login_failure, clear_login_failures, lockout_message
        ip = client_ip(request)

        locked, why = login_locked(email, ip)
        if locked:
            # Same answer for known and unknown e-mails; the password is not checked while locked
            log_event('auth.login', 'User', '', result='locked', level='WARNING', email=email, ip=ip, locked_by=why)
            return Response({'error': lockout_message(), 'code': 'locked'}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        user = authenticate(request, email=email, password=password)
        if not user:
            existing = User.objects.filter(email=email).first()
            if existing and existing.check_password(password) and not existing.is_active:
                log_event('auth.login', 'User', existing.id, result='denied', level='WARNING', reason='deactivated', ip=ip)
                return Response({'error': 'This account has been deactivated. Please contact your firm admin.'}, status=status.HTTP_403_FORBIDDEN)
            record_login_failure(email, ip)
            return Response({'error': 'Invalid email or password.'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.is_active:
            return Response({'error': 'This account has been deactivated. Please contact your firm admin.'}, status=status.HTTP_403_FORBIDDEN)

        login(request, user)
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        cleared = clear_login_failures(email)
        log_event('auth.login', 'User', user.id, actor_user_id=user.id, ip=ip, cleared_failures=cleared,
                  must_change_password=user.must_change_password)

        csrf_token = get_token(request)
        return Response({
            'message': 'Login successful',
            'csrf_token': csrf_token,
            'user': UserSerializer(user).data
        })


class LogoutView(views.APIView):
    def post(self, request):
        logout(request)
        return Response({'message': 'Logged out successfully.'})


class CurrentUserView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        firm_data = FirmSerializer(user.firm).data if user.firm else None
        return Response({
            'user': UserSerializer(user).data,
            'firm': firm_data,
            'csrf_token': get_token(request),
        })


class FirmSettingsView(views.APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        firm = request.user.firm
        if not firm:
            return Response({'error': 'No firm associated with current user.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(FirmSerializer(firm).data)

    def patch(self, request):
        firm = request.user.firm
        if not firm:
            return Response({'error': 'No firm associated with current user.'}, status=status.HTTP_404_NOT_FOUND)
        # Spec §2.2: firm settings, FY and branding are Superadmin only
        if not (request.user.is_superadmin or request.user.is_superuser):
            log_permission_denied(request.user, 'firm.settings_update', 'Firm', firm.id, 'not superadmin')
            return Response({'error': 'Only the Superadmin can change firm settings.'}, status=status.HTTP_403_FORBIDDEN)
        # Spec FY1: fy_start_month cannot change after tasks exist
        if 'fy_start_month' in request.data:
            from apps.tasks.models import Task
            try:
                new_month = int(request.data.get('fy_start_month'))
            except (TypeError, ValueError):
                return Response({'fy_start_month': 'Must be a number 1-12.'}, status=status.HTTP_400_BAD_REQUEST)
            if not 1 <= new_month <= 12:
                return Response({'fy_start_month': 'Must be a number 1-12.'}, status=status.HTTP_400_BAD_REQUEST)
            if new_month != firm.fy_start_month and Task.objects.filter(firm=firm).exists():
                return Response({'fy_start_month': 'Financial year start month cannot change after tasks exist.'},
                                status=status.HTTP_400_BAD_REQUEST)

        old_data = FirmSerializer(firm).data
        serializer = FirmSerializer(firm, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        AuditLog.log(
            firm_id=firm.id,
            action='firm.settings_update',
            entity_type='Firm',
            entity_id=str(firm.id),
            actor_user_id=request.user.id,
            old_value=old_data,
            new_value=serializer.data,
            request=request
        )
        log_event('firm.settings_update', 'Firm', firm.id,
                  changed=[k for k in serializer.data if serializer.data.get(k) != old_data.get(k)])
        return Response(serializer.data)


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]
    # Users are never hard-deleted (history must stay); deactivate with PATCH is_active=false
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def _guard_superadmin(self, target=None, new_role=None):
        """Spec §2.2: only a Superadmin may create, edit or promote to Superadmin."""
        actor = self.request.user
        if actor.is_superadmin or actor.is_superuser:
            return
        if new_role == User.Role.SUPERADMIN or (target is not None and target.system_role == User.Role.SUPERADMIN):
            log_permission_denied(actor, 'user.superadmin_change', 'User', getattr(target, 'id', ''), 'admin touching superadmin')
            raise PermissionDenied('Only a Superadmin can create, edit or promote a Superadmin.')
        if target is not None and target.id == actor.id and new_role and new_role != actor.system_role:
            raise PermissionDenied('You cannot change your own role.')

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return User.objects.none()
        return User.objects.filter(firm=firm).prefetch_related('user_branches__branch')

    @action(detail=True, methods=['post'])
    def set_temporary_password(self, request, pk=None):
        """Admin: give the user a new random temporary password. It is shown one time to the admin.
        The user is signed out everywhere and must choose a new password at the next sign-in."""
        import secrets
        from .security import clear_login_failures
        target = self.get_object()
        self._guard_superadmin(target=target)
        if target.id == request.user.id:
            return Response({'error': 'Use Profile > Change password for your own account.'}, status=status.HTTP_400_BAD_REQUEST)
        if not target.is_active:
            return Response({'error': 'This user is deactivated.'}, status=status.HTTP_400_BAD_REQUEST)
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
        temp = '-'.join(''.join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))   # e.g. Ab3d-Xy7k-Pq2m
        target.set_password(temp)
        target.must_change_password = True
        target.save(update_fields=['password', 'must_change_password'])
        cleared = clear_login_failures(target.email)
        AuditLog.log(firm_id=target.firm_id, action='user.temporary_password', entity_type='User',
                     entity_id=str(target.id), actor_user_id=request.user.id, request=request)
        log_event('user.temporary_password', 'User', target.id, actor_user_id=request.user.id, cleared_failures=cleared)
        return Response({'temporary_password': temp,
                         'message': f'Give this password to {target.full_name}. They must change it when they sign in.'})

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        self._guard_superadmin(new_role=serializer.validated_data.get('system_role'))
        user = serializer.save()
        AuditLog.log(
            firm_id=self.request.user.firm.id,
            action='user.create',
            entity_type='User',
            entity_id=str(user.id),
            actor_user_id=self.request.user.id,
            new_value={'email': user.email, 'full_name': user.full_name, 'role': user.system_role},
            request=self.request
        )
        log_event('user.create', 'User', user.id, role=user.system_role)

    def perform_update(self, serializer):
        instance = self.get_object()
        old_role = instance.system_role
        old_active = instance.is_active
        old_can_create = instance.can_create_tasks
        self._guard_superadmin(target=instance, new_role=serializer.validated_data.get('system_role'))

        # Rule U6: Firm MUST always have >= 1 active superadmin
        new_active = serializer.validated_data.get('is_active', instance.is_active)
        new_role = serializer.validated_data.get('system_role', instance.system_role)
        if instance.system_role == User.Role.SUPERADMIN and (not new_active or new_role != User.Role.SUPERADMIN):
            active_superadmins = User.objects.filter(firm=instance.firm, system_role=User.Role.SUPERADMIN, is_active=True).exclude(id=instance.id).count()
            if active_superadmins == 0:
                raise serializers.ValidationError({'error': 'Cannot deactivate or demote the last active Superadmin.'})

        if instance.id == self.request.user.id and serializer.validated_data.get('is_active') is False:
            raise serializers.ValidationError({'error': 'You cannot deactivate your own account.'})

        # Rule U5: Deactivation requires open task re-assign check
        if old_active and not new_active:
            from apps.tasks.models import Task
            open_tasks_count = Task.objects.filter(
                assigned_user=instance,
                status__in=['not_started', 'in_process', 'on_hold']
            ).count()
            if open_tasks_count > 0:
                log_event('user.deactivate_blocked', 'User', instance.id, open_assigned=open_tasks_count)
                raise serializers.ValidationError({
                    'error': f'User has {open_tasks_count} open assigned tasks. Please re-assign them before deactivating.',
                    'open_assigned_tasks': open_tasks_count,
                })
            serializer.validated_data['left_on'] = timezone.localdate()

        user = serializer.save()
        AuditLog.log(
            firm_id=self.request.user.firm.id,
            action='user.update',
            entity_type='User',
            entity_id=str(user.id),
            actor_user_id=self.request.user.id,
            old_value={'role': old_role, 'is_active': old_active, 'can_create_tasks': old_can_create},
            new_value={'email': user.email, 'role': user.system_role, 'is_active': user.is_active,
                       'can_create_tasks': user.can_create_tasks},
            request=self.request
        )
        log_event('user.update', 'User', user.id, old_role=old_role, new_role=user.system_role,
                  old_active=old_active, new_active=user.is_active,
                  old_can_create_tasks=old_can_create, new_can_create_tasks=user.can_create_tasks,
                  effective_can_create_tasks=user.effective_can_create_tasks)

    @action(detail=True, methods=['post'])
    def move_tasks(self, request, pk=None):
        """
        Spec §5.4 A5 / U5: move this user's OPEN tasks to another user.
        Body: {to_user_id, roles: [assigned, leader, manager, member] (default all), reason, preview: true|false}
        preview=true -> counts + first 50 tasks, nothing changes.
        Each task is moved in its own transaction, so one bad task does not stop the rest.
        """
        from apps.tasks.models import Task, TaskMember, TaskAssignmentLog
        from apps.tasks.selectors import PENDING, role_filter
        from apps.tasks.services.task_service import TaskService, TaskMemberService
        source = self.get_object()
        roles = request.data.get('roles') or ['assigned', 'leader', 'manager', 'member']
        if not isinstance(roles, list) or any(r not in ('assigned', 'leader', 'manager', 'member') for r in roles):
            raise serializers.ValidationError({'roles': 'Roles must be a list of: assigned, leader, manager, member.'})
        preview = str(request.data.get('preview', 'false')).lower() in ('true', '1', 'yes')
        base = Task.objects.filter(firm=source.firm, status__in=PENDING)
        per_role = {r: role_filter(base, source.id, r) for r in roles}
        if preview:
            sample = role_filter(base, source.id).filter(id__in=[t.id for r in roles for t in per_role[r][:50]])
            data = {
                'counts': {r: qs.count() for r, qs in per_role.items()},
                'tasks': [{'id': str(t.id), 'task_number': t.task_number, 'title': t.title, 'status': t.status,
                           'due_date': t.due_date} for t in sample.order_by('due_date')[:50]],
            }
            log_event('user.move_tasks_preview', 'User', source.id, counts=data['counts'])
            return Response(data)

        target = User.objects.filter(id=request.data.get('to_user_id'), firm=source.firm, is_active=True).first() \
            if request.data.get('to_user_id') else None
        if target is None or target.id == source.id:
            raise serializers.ValidationError({'to_user_id': 'Choose another active user to receive the tasks.'})
        reason = (request.data.get('reason') or '').strip()
        if len(reason) < 3:
            raise serializers.ValidationError({'reason': 'A reason (minimum 3 characters) is required.'})

        moved = {r: 0 for r in roles}
        errors = []
        for role in roles:
            for task in list(per_role[role]):
                try:
                    if role == 'member':
                        TaskMemberService.remove_member(task, source, request.user, request=request)
                        if target.id not in (task.assigned_user_id, task.leader_user_id, task.manager_user_id) and \
                                not TaskMember.objects.filter(task=task, user=target, removed_at__isnull=True).exists():
                            TaskMemberService.add_member(task, target, request.user, request=request)
                    else:
                        TaskService.reassign_task(task, role, target, request.user, reason=reason, request=request,
                                                  trigger=TaskAssignmentLog.Trigger.BULK)
                    moved[role] += 1
                except Exception as exc:  # noqa: BLE001 - report per task, continue with the rest
                    msg = str(getattr(exc, 'detail', exc))
                    errors.append({'task_number': task.task_number, 'role': role, 'error': msg[:300]})
                    log_event('user.move_tasks_item', 'Task', task.id, result='error', level='WARNING', role=role, error=msg)
        AuditLog.log(firm_id=source.firm_id, action='user.move_tasks', entity_type='User', entity_id=str(source.id),
                     actor_user_id=request.user.id,
                     new_value={'to': target.full_name, 'moved': moved, 'errors': len(errors), 'reason': reason},
                     request=request)
        log_event('user.move_tasks', 'User', source.id, to_user=target.id, moved=moved, errors=len(errors))
        return Response({'moved': moved, 'errors': errors})

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated, IsFirmMember])
    def mentionable(self, request):
        """Returns active firm staff for @mention autocomplete."""
        firm = request.user.firm
        if not firm:
            return Response([])
        users = User.objects.filter(firm=firm, is_active=True).values('id', 'full_name', 'email', 'designation', 'system_role')
        return Response(list(users))


class BranchViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BranchSerializer
    permission_classes = [permissions.IsAuthenticated, IsFirmMember]

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return Branch.objects.none()
        return Branch.objects.filter(firm=firm, is_active=True)


class FirmLogoView(views.APIView):
    """
    POST multipart 'logo' (PNG / JPEG / WEBP, max 1 MB) or DELETE. Superadmin only.
    The file type is checked by opening the image (not by the file name).
    The stored name is random, never the uploaded name (spec §5.8 F1).
    """
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    MAX_BYTES = 1024 * 1024
    ALLOWED = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}

    def post(self, request):
        import uuid
        from PIL import Image, UnidentifiedImageError
        from django.core.files.base import ContentFile
        firm = request.user.firm
        upload = request.FILES.get('logo')
        if not upload:
            return Response({'logo': 'Choose an image file.'}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > self.MAX_BYTES:
            log_event('firm.logo_upload', 'Firm', firm.id, result='error', level='WARNING', reason='too large', size=upload.size)
            return Response({'logo': 'The logo must be 1 MB or smaller.'}, status=status.HTTP_400_BAD_REQUEST)
        data = upload.read()
        try:
            import io
            img = Image.open(io.BytesIO(data))
            fmt = img.format
            img.verify()
            width, height = Image.open(io.BytesIO(data)).size
        except (UnidentifiedImageError, OSError, SyntaxError):
            fmt = None
        if fmt not in self.ALLOWED:
            log_event('file.reject', 'Firm', firm.id, level='WARNING', result='error',
                      reason='not png/jpeg/webp', detected=fmt, size=upload.size)
            return Response({'logo': 'Use a PNG, JPEG or WEBP image.'}, status=status.HTTP_400_BAD_REQUEST)
        if width > 2000 or height > 2000:
            return Response({'logo': 'The logo must be at most 2000 x 2000 pixels.'}, status=status.HTTP_400_BAD_REQUEST)
        old_name = firm.logo.name if firm.logo else None
        firm.logo.save(f'{uuid.uuid4().hex}.{self.ALLOWED[fmt]}', ContentFile(data), save=True)
        if old_name:
            firm.logo.storage.delete(old_name)
        AuditLog.log(firm_id=firm.id, action='firm.logo_update', entity_type='Firm', entity_id=str(firm.id),
                     actor_user_id=request.user.id, new_value={'format': fmt, 'size': len(data)}, request=request)
        log_event('file.upload', 'Firm', firm.id, purpose='logo', mime=fmt, size=len(data), width=width, height=height)
        return Response(FirmSerializer(firm, context={'request': request}).data)

    def delete(self, request):
        firm = request.user.firm
        if firm.logo:
            name = firm.logo.name
            firm.logo = None
            firm.save(update_fields=['logo', 'updated_at'])
            firm._meta.get_field('logo').storage.delete(name)
            AuditLog.log(firm_id=firm.id, action='firm.logo_remove', entity_type='Firm', entity_id=str(firm.id),
                         actor_user_id=request.user.id, request=request)
            log_event('firm.logo_remove', 'Firm', firm.id)
        return Response(FirmSerializer(firm, context={'request': request}).data)


class ProfileView(views.APIView):
    """Own profile (spec §6.2 item 7): name, phone, notification preferences."""
    permission_classes = [permissions.IsAuthenticated]

    def _data(self, user):
        from apps.notifications.models import NotificationPreference
        pref, _ = NotificationPreference.objects.get_or_create(user=user)
        return {
            'id': str(user.id), 'email': user.email, 'full_name': user.full_name, 'phone': user.phone,
            'designation': user.designation, 'system_role': user.system_role,
            'notifications': {'email_enabled': pref.email_enabled, 'digest_enabled': pref.digest_enabled},
        }

    def get(self, request):
        return Response(self._data(request.user))

    def patch(self, request):
        from apps.notifications.models import NotificationPreference
        user = request.user
        changed = []
        full_name = request.data.get('full_name')
        if full_name is not None:
            if not str(full_name).strip():
                return Response({'full_name': 'Name is required.'}, status=status.HTTP_400_BAD_REQUEST)
            user.full_name = str(full_name).strip()[:150]
            changed.append('full_name')
        if 'phone' in request.data:
            user.phone = str(request.data.get('phone') or '').strip()[:20]
            changed.append('phone')
        if changed:
            user.save(update_fields=changed + ['updated_at'])
        prefs = request.data.get('notifications')
        if isinstance(prefs, dict):
            pref, _ = NotificationPreference.objects.get_or_create(user=user)
            for key in ('email_enabled', 'digest_enabled'):
                if key in prefs:
                    setattr(pref, key, bool(prefs[key]))
                    changed.append(f'notifications.{key}')
            pref.save()
        log_event('user.profile_update', 'User', user.id, changed=changed)
        return Response(self._data(user))


class ChangePasswordView(views.APIView):
    """Change own password. Needs the current password; Django password rules apply (min 10 chars)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from django.contrib.auth import update_session_auth_hash
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        user = request.user
        current = request.data.get('current_password') or ''
        new = request.data.get('new_password') or ''
        if not user.check_password(current):
            log_event('auth.password_change', 'User', user.id, result='error', level='WARNING', reason='wrong current password')
            return Response({'current_password': 'The current password is not correct.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new, user=user)
        except DjangoValidationError as exc:
            return Response({'new_password': list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        if user.check_password(new):
            return Response({'new_password': ['The new password must be different from the current password.']}, status=status.HTTP_400_BAD_REQUEST)
        was_temporary = user.must_change_password
        user.set_password(new)
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])
        # Other devices are signed out (the session hash changes); this device stays signed in
        update_session_auth_hash(request, user)
        log_event('auth.password_change.detail', 'User', user.id, actor_user_id=user.id, was_temporary=was_temporary)
        AuditLog.log(firm_id=user.firm_id, action='auth.password_change', entity_type='User',
                     entity_id=str(user.id), actor_user_id=user.id, request=request)
        log_event('auth.password_change', 'User', user.id)
        return Response({'message': 'Password changed.'})


def _session_ids_of(user_id):
    """Session keys (database sessions) that belong to this user and are not expired."""
    from django.contrib.sessions.models import Session
    out = []
    for sess in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        try:
            if sess.get_decoded().get('_auth_user_id') == str(user_id):
                out.append(sess.session_key)
        except Exception:   # a damaged session row is not ours to judge; skip it
            continue
    return out


class LogoutOthersView(views.APIView):
    """POST: sign out this user on every other browser / device. This device stays signed in."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from django.contrib.sessions.models import Session
        current = request.session.session_key
        keys = [k for k in _session_ids_of(request.user.id) if k != current]
        Session.objects.filter(session_key__in=keys).delete()
        AuditLog.log(firm_id=request.user.firm_id, action='auth.logout_others', entity_type='User',
                     entity_id=str(request.user.id), actor_user_id=request.user.id, new_value={'sessions': len(keys)}, request=request)
        log_event('auth.logout_others', 'User', request.user.id, actor_user_id=request.user.id, sessions_ended=len(keys))
        return Response({'message': f'Signed out on {len(keys)} other device(s).', 'sessions_ended': len(keys)})


class PasswordResetRequestView(views.APIView):
    """POST {email}: send a one-time reset link (valid PASSWORD_RESET_TIMEOUT seconds).
    The answer is always the same, so it does not tell if the e-mail has an account."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []   # no CSRF needed for a signed-out user

    def post(self, request):
        from django.conf import settings
        from django.core.mail import send_mail
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        from .security import client_ip, reset_request_allowed
        email = str(request.data.get('email') or '').strip().lower()
        answer = Response({'message': 'If this e-mail has an active account, a reset link has been sent. Check your inbox (and spam folder).'})
        if not email or '@' not in email:
            return Response({'email': 'Enter a valid e-mail address.'}, status=status.HTTP_400_BAD_REQUEST)
        ip = client_ip(request)
        if not reset_request_allowed(email, ip):
            log_event('auth.password_reset.request', 'User', '', result='throttled', level='WARNING', email=email, ip=ip)
            return answer
        user = User.objects.filter(email=email, is_active=True).first()
        if not user:
            log_event('auth.password_reset.request', 'User', '', result='no_account', level='INFO', email=email, ip=ip)
            return answer
        uid = urlsafe_base64_encode(force_bytes(str(user.id)))
        token = default_token_generator.make_token(user)
        link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?uid={uid}&token={token}"
        minutes = settings.PASSWORD_RESET_TIMEOUT // 60
        try:
            send_mail('FirmFlow: reset your password',
                      f"Hello {user.full_name},\n\nUse this link to set a new password. It works one time and expires in {minutes} minutes:\n\n{link}\n\n"
                      "If you did not ask for this, ignore this e-mail. Your password does not change.\n",
                      settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
            log_event('auth.password_reset.request', 'User', user.id, result='sent', ip=ip)
        except Exception as exc:
            # The user gets the same answer; the log tells the admin that SMTP failed
            log_event('auth.password_reset.request', 'User', user.id, result='error', level='ERROR', ip=ip, error=str(exc)[:300])
        AuditLog.log(firm_id=user.firm_id, action='auth.password_reset_request', entity_type='User',
                     entity_id=str(user.id), actor_user_id=user.id, request=request)
        return answer


class PasswordResetConfirmView(views.APIView):
    """POST {uid, token, new_password}: set the new password from the e-mail link."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        from django.contrib.auth.tokens import default_token_generator
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.utils.http import urlsafe_base64_decode
        from .security import clear_login_failures
        uid = str(request.data.get('uid') or '')
        token = str(request.data.get('token') or '')
        new = str(request.data.get('new_password') or '')
        user = None
        try:
            user = User.objects.filter(id=urlsafe_base64_decode(uid).decode(), is_active=True).first()
        except Exception:
            user = None
        if not user or not default_token_generator.check_token(user, token):
            log_event('auth.password_reset.confirm', 'User', getattr(user, 'id', ''), result='error', level='WARNING', reason='bad or expired link')
            return Response({'error': 'This reset link is not valid or has expired. Ask for a new link.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new, user=user)
        except DjangoValidationError as exc:
            return Response({'new_password': list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new)   # changes the password hash: the link stops working and all sessions end
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])
        cleared = clear_login_failures(user.email)
        AuditLog.log(firm_id=user.firm_id, action='auth.password_reset', entity_type='User',
                     entity_id=str(user.id), actor_user_id=user.id, request=request)
        log_event('auth.password_reset.confirm', 'User', user.id, cleared_failures=cleared)
        return Response({'message': 'Password changed. Sign in with the new password.'})
