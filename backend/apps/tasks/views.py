import re
import uuid
from datetime import datetime, timedelta
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Task, PersonalTodo, StickyNote, TaskTimeLog
from .serializers import (
    TaskListSerializer, TaskDetailSerializer, TaskCreateSerializer, TaskUpdateSerializer,
    TaskCommentSerializer, TaskIssueSerializer, TaskTimeLogSerializer,
    PersonalTodoSerializer, StickyNoteSerializer
)
from .services.task_service import TaskService, TaskMemberService
from .services import attachments as attachment_service
from . import permissions as task_perm
from . import selectors
from apps.accounts.models import User
from apps.accounts.permissions import IsFirmMember, IsAdminOrSuperAdmin
from apps.common.dates import current_fy
from apps.common.logging import log_event, log_permission_denied
from apps.common.crypto import pan_blind_index

PAN_RE = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')


def _uuid(value, field):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({field: 'A valid id is required.'})


def _date(value, field, required=True):
    if value in (None, ''):
        if required:
            raise ValidationError({field: 'Date is required (YYYY-MM-DD).'})
        return None
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except ValueError:
        raise ValidationError({field: 'Date must be in YYYY-MM-DD format.'})


def _bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


class TaskViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsFirmMember]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['priority', 'client', 'task_type', 'fy', 'period', 'billing_state']
    ordering_fields = ['due_date', 'created_at', 'priority', 'status', 'task_number']
    ordering = ['due_date', '-created_at']
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        firm = user.firm
        if not firm:
            return Task.objects.none()
        params = self.request.query_params
        is_admin = user.is_admin or user.is_superuser
        # Admins can open deleted tasks by id (Deleted report); lists hide them unless asked.
        include_deleted = is_admin and (self.action != 'list' or params.get('show_deleted', '').lower() == 'true')

        qs = selectors.base_queryset(firm, include_deleted).select_related(
            'firm', 'client', 'task_type', 'fy', 'period',
            'assigned_user', 'leader_user', 'manager_user'
        )
        qs = selectors.visible_to(qs, user)
        if self.action not in ('list', 'export'):
            return qs

        qs = selectors.annotate_flags(qs)

        # Role filter: admins may pass user_id; staff always filter on themselves.
        role = params.get('role') or None
        if role and role not in selectors.ROLE_PARAMS:
            raise ValidationError({'role': f'Role must be one of {", ".join(selectors.ROLE_PARAMS)}.'})
        target_user = params.get('user_id') if is_admin else None
        if target_user:
            qs = selectors.role_filter(qs, _uuid(target_user, 'user_id'), role)
        elif role:
            qs = selectors.role_filter(qs, user.id, role)

        # Tile filters (same rules as dashboard counts)
        tile = params.get('tile') or selectors.LEGACY_DATE_FILTERS.get(params.get('date_filter') or '')
        if params.get('unassigned', '').lower() == 'true':
            tile = 'unassigned'
        if tile:
            if tile not in selectors.TILE_KEYS:
                raise ValidationError({'tile': f'Unknown tile "{tile}".'})
            qs = selectors.apply_tile(qs, tile, firm)

        # status=a,b,c
        status_param = params.get('status')
        if status_param:
            wanted = [s.strip() for s in status_param.split(',') if s.strip()]
            valid = {c for c, _ in Task.Status.choices}
            bad = [s for s in wanted if s not in valid]
            if bad:
                raise ValidationError({'status': f'Unknown status: {", ".join(bad)}.'})
            if 'deleted' in wanted and not is_admin:
                raise ValidationError({'status': 'Only admins can list deleted tasks.'})
            qs = qs.filter(status__in=wanted)

        # service=<id> (all task types of a service), assigned/leader by id handled by user_id+role
        service_id = params.get('service')
        if service_id:
            qs = qs.filter(task_type__service_id=_uuid(service_id, 'service'))
        due_from, due_to = params.get('due_from'), params.get('due_to')
        if due_from:
            qs = qs.filter(due_date__gte=_date(due_from, 'due_from'))
        if due_to:
            qs = qs.filter(due_date__lte=_date(due_to, 'due_to'))

        # Search: task number, title, client name, GSTIN, or exact PAN
        q = (params.get('search') or '').strip()
        if q:
            cond = (Q(task_number__icontains=q) | Q(title__icontains=q) |
                    Q(client__name__icontains=q) | Q(client__gstin__icontains=q))
            if PAN_RE.match(q.upper()):
                cond |= Q(client__pan_hash=pan_blind_index(q))
            qs = qs.filter(cond)
        return qs

    def get_serializer_class(self):
        if self.action in ('list', 'export'):
            return TaskListSerializer
        if self.action == 'create':
            return TaskCreateSerializer
        return TaskDetailSerializer

    def _detail(self, task, code=status.HTTP_200_OK):
        # Re-read through the visibility rules; the actor may have lost access (e.g. re-assigned away).
        fresh = self.get_queryset().filter(pk=task.pk).first()
        if fresh is None:
            return Response({'message': 'Saved. You no longer have access to this task.', 'id': str(task.pk)}, status=code)
        return Response(TaskDetailSerializer(fresh, context={'request': self.request}).data, status=code)

    def create(self, request, *args, **kwargs):
        user = request.user
        firm = user.firm
        if not user.effective_can_create_tasks:
            reason = ('user can_create_tasks=False' if user.can_create_tasks is False
                      else 'firm staff_can_create_task is off')
            log_permission_denied(user, 'task.create', 'Task', reason=reason)
            return Response({'error': 'You are not allowed to create tasks. Ask an admin to allow it for you '
                                      '(Team page) or for all staff (Settings).'},
                            status=status.HTTP_403_FORBIDDEN)

        serializer = TaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        branch = data.get('branch')
        if branch is None:
            ub = user.user_branches.select_related('branch').first()
            branch = ub.branch if ub else None

        period = data.get('period')
        fy = data.get('fy') or (period.fy if period else None)
        if not fy and data['task_type'].requires_fy:
            fy = current_fy(firm)
            if fy is None:
                raise ValidationError({'fy': 'No financial year exists for today. Ask an admin to run FY generation.'})

        task = TaskService.create_task(
            firm=firm, branch=branch, client=data['client'], task_type=data['task_type'], creator=user,
            fy=fy, period=period, assigned_user=data.get('assigned_user'),
            leader_user=data.get('leader_user'), manager_user=data.get('manager_user'),
            due_date=data.get('due_date'), priority=data.get('priority') or 'normal',
            description=data.get('description', ''), title=data.get('title'), request=request,
        )
        return self._detail(task, status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        """Edit safe fields only. `version` is required (optimistic locking, spec §4 rule 7)."""
        task = self.get_object()
        if 'version' in request.data and request.data.get('version') is not None:
            try:
                if int(request.data.get('version')) != task.version:
                    log_event('task.conflict', 'Task', task.id, result='error', level='WARNING',
                              expected_version=request.data.get('version'), actual_version=task.version)
                    return Response({'error': 'Conflict: Someone else has updated this task. Please refresh before saving changes.'},
                                    status=status.HTTP_409_CONFLICT)
            except (TypeError, ValueError):
                raise ValidationError({'version': 'Version must be a number.'})
        ser = TaskUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        changes = {k: v for k, v in ser.validated_data.items() if k != 'version'}
        task = TaskService.update_fields(task, request.user, changes,
                                         expected_version=ser.validated_data['version'], request=request)
        return self._detail(task)

    def update(self, request, *args, **kwargs):
        if not kwargs.get('partial'):
            return Response({'error': 'Use PATCH with only the fields you want to change.'},
                            status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return self.partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Soft delete (spec §4 rule 4) - Admin+ and a reason."""
        task = self.get_object()
        if not (request.user.is_admin or request.user.is_superuser):
            log_permission_denied(request.user, 'task.delete', 'Task', task.id, 'not admin')
            return Response({'error': 'Only Admin or Superadmin can delete tasks.'}, status=status.HTTP_403_FORBIDDEN)
        reason = (request.data.get('reason') or request.query_params.get('reason') or '').strip()
        if not reason:
            return Response({'error': 'A delete reason is required.'}, status=status.HTTP_400_BAD_REQUEST)
        TaskService.soft_delete(task, request.user, reason=reason, request=request,
                                expected_version=request.data.get('version'))
        return Response({'message': 'Task deleted successfully.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def pickup(self, request, pk=None):
        task = TaskService.pickup_task(self.get_object(), request.user, request=request)
        return self._detail(task)

    @action(detail=True, methods=['post'])
    def reassign(self, request, pk=None):
        task = self.get_object()
        field = request.data.get('field', 'assigned')
        new_user_id = request.data.get('new_user_id')
        new_user = None
        if new_user_id:
            new_user = User.objects.filter(id=_uuid(new_user_id, 'new_user_id'), firm=request.user.firm).first()
            if new_user is None:
                raise ValidationError({'new_user_id': 'User not found in this firm.'})
        task = TaskService.reassign_task(task, field, new_user, request.user,
                                         reason=request.data.get('reason', ''), request=request,
                                         expected_version=request.data.get('version'))
        return self._detail(task)

    @action(detail=True, methods=['post'])
    def change_status(self, request, pk=None):
        task = TaskService.update_status(
            self.get_object(), request.data.get('status'), changed_by=request.user,
            reason=request.data.get('reason', ''), on_hold_reason=request.data.get('on_hold_reason', ''),
            request=request, expected_version=request.data.get('version'),
        )
        return self._detail(task)

    @action(detail=True, methods=['post'])
    def tick_milestone(self, request, pk=None):
        task = self.get_object()
        ms_id = _uuid(request.data.get('milestone_id'), 'milestone_id')
        prog = task.milestone_progress.select_related('milestone').filter(milestone_id=ms_id).first()
        if prog is None:
            raise NotFound('Milestone not found on this task.')
        TaskService.tick_milestone(task, prog, user=request.user, note=request.data.get('note', ''),
                                   request=request, expected_version=request.data.get('version'))
        return self._detail(task)

    @action(detail=True, methods=['post'])
    def toggle_todo(self, request, pk=None):
        task = self.get_object()
        todo = task.todos.filter(id=_uuid(request.data.get('todo_id'), 'todo_id')).first()
        if todo is None:
            raise NotFound('To-do not found on this task.')
        TaskService.toggle_todo(task, todo, request.user, request=request)
        return self._detail(task)

    @action(detail=True, methods=['post'])
    def add_comment(self, request, pk=None):
        mentions = request.data.get('mentions', [])
        if not isinstance(mentions, list):
            raise ValidationError({'mentions': 'Mentions must be a list of user ids.'})
        comment = TaskService.add_comment(self.get_object(), request.user, request.data.get('body', ''),
                                          mentions=mentions, is_internal=_bool(request.data.get('is_internal'), True),
                                          request=request)
        return Response(TaskCommentSerializer(comment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def raise_issue(self, request, pk=None):
        issue = TaskService.raise_issue(self.get_object(), request.user, request.data.get('label_id'),
                                        detail=request.data.get('detail', ''),
                                        due_date=_date(request.data.get('due_date'), 'due_date', required=False),
                                        request=request)
        return Response(TaskIssueSerializer(issue).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def resolve_issue(self, request, pk=None):
        task = self.get_object()
        issue = task.issues.select_related('label').filter(id=_uuid(request.data.get('issue_id'), 'issue_id')).first()
        if issue is None:
            raise NotFound('Issue not found on this task.')
        issue = TaskService.resolve_issue(task, issue, request.user, note=request.data.get('note', ''), request=request)
        return Response(TaskIssueSerializer(issue).data)

    @action(detail=True, methods=['post'])
    def log_time(self, request, pk=None):
        time_log = TaskService.log_time(
            self.get_object(), request.user,
            work_date=_date(request.data.get('work_date'), 'work_date'),
            minutes=request.data.get('minutes'),
            is_billable=_bool(request.data.get('is_billable'), True),
            note=request.data.get('note', ''), request=request,
        )
        return Response(TaskTimeLogSerializer(time_log, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)

    # ---------------------------------------------------------------- members
    def _member_user(self, request):
        uid = _uuid(request.data.get('user_id'), 'user_id')
        member = User.objects.filter(id=uid, firm=request.user.firm).first()
        if member is None:
            raise ValidationError({'user_id': 'User not found in this firm.'})
        return member

    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        task = TaskMemberService.add_member(self.get_object(), self._member_user(request), request.user, request=request)
        return self._detail(task)

    @action(detail=True, methods=['post'])
    def remove_member(self, request, pk=None):
        task = TaskMemberService.remove_member(self.get_object(), self._member_user(request), request.user, request=request)
        return self._detail(task)

    # ---------------------------------------------------------------- attachments (spec §5.8)
    @action(detail=True, methods=['post'])
    def upload_attachment(self, request, pk=None):
        att = attachment_service.add_attachment(
            self.get_object(), request.user, request.FILES.get('file'),
            confirm_duplicate=_bool(request.data.get('confirm_duplicate'), False), request=request)
        from .serializers import TaskAttachmentSerializer
        return Response(TaskAttachmentSerializer(att).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def delete_attachment(self, request, pk=None):
        task = self.get_object()
        att = task.attachments.filter(id=_uuid(request.data.get('attachment_id'), 'attachment_id')).first()
        if att is None:
            raise NotFound('Attachment not found on this task.')
        attachment_service.delete_attachment(task, att, request.user, request=request)
        return self._detail(task)

    @action(detail=True, methods=['get'], url_path=r'attachments/(?P<att_id>[0-9a-fA-F-]{32,36})/download')
    def download_attachment(self, request, pk=None, att_id=None):
        """Authenticated streaming download (spec §5.8 F2). Never a public path."""
        from django.http import FileResponse
        task = self.get_object()
        task_perm.require(task_perm.can_work(task, request.user), request.user, 'file.download', task,
                          'Only people with a role on this task can download its files.')
        att = task.attachments.filter(id=att_id, deleted_at__isnull=True).first()
        if att is None:
            raise NotFound('Attachment not found.')
        try:
            fh = att.file.open('rb')
        except (FileNotFoundError, OSError) as exc:
            log_event('file.download', 'Task', task.id, result='error', level='ERROR', attachment_id=att.id, error=str(exc))
            raise NotFound('The file is missing in storage. Ask an admin to check the server.')
        log_event('file.download', 'Task', task.id, attachment_id=att.id, size=att.size_bytes)
        response = FileResponse(fh, as_attachment=True, filename=att.file_name, content_type=att.mime)
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-store'
        return response

    # ---------------------------------------------------------------- bulk actions + export (spec §6.1-2)
    BULK_ACTIONS = ('assign', 'priority', 'due_date', 'delete')

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsAdminOrSuperAdmin])
    def bulk_action(self, request):
        """
        Body: {ids: [...], action: assign|priority|due_date|delete, value, reason}
        Each task goes through TaskService (same rules, logs, notifications) in its own transaction;
        one failing task does not stop the others. Max 500 tasks.
        """
        ids = request.data.get('ids') or []
        act = request.data.get('action')
        value = request.data.get('value')
        reason = (request.data.get('reason') or '').strip()
        if act not in self.BULK_ACTIONS:
            raise ValidationError({'action': f'Action must be one of {", ".join(self.BULK_ACTIONS)}.'})
        if not isinstance(ids, list) or not ids or len(ids) > 500:
            raise ValidationError({'ids': 'Select 1 to 500 tasks.'})
        if act in ('assign', 'delete', 'due_date') and len(reason) < 3:
            raise ValidationError({'reason': 'A reason (minimum 3 characters) is required.'})
        new_user = None
        if act == 'assign' and value:
            new_user = User.objects.filter(id=_uuid(value, 'value'), firm=request.user.firm).first()
            if new_user is None:
                raise ValidationError({'value': 'User not found in this firm.'})
        if act == 'priority' and value not in ('normal', 'high'):
            raise ValidationError({'value': 'Priority must be normal or high.'})
        due = _date(value, 'value') if act == 'due_date' else None

        tasks = Task.objects.filter(firm=request.user.firm, id__in=[_uuid(i, 'ids') for i in ids])
        done, errors = 0, []
        for task in tasks:
            try:
                if act == 'assign':
                    TaskService.reassign_task(task, 'assigned', new_user, request.user, reason=reason, request=request,
                                              trigger='bulk')
                elif act == 'priority':
                    TaskService.update_fields(task, request.user, {'priority': value}, request=request)
                elif act == 'due_date':
                    TaskService.update_fields(task, request.user, {'due_date': due}, request=request)
                else:
                    TaskService.soft_delete(task, request.user, reason, request=request)
                done += 1
            except Exception as exc:  # noqa: BLE001 - report per task
                msg = str(getattr(exc, 'detail', exc))
                errors.append({'task_number': task.task_number, 'error': msg[:300]})
        log_event('task.bulk_action', 'Task', '', bulk_action=act, requested=len(ids), done=done, errors=len(errors))
        return Response({'done': done, 'errors': errors})

    @action(detail=False, methods=['get'])
    def export(self, request):
        """Same filters as the list. ?format_type=csv|xlsx. Max 10 000 rows (spec §6.3: every list exportable)."""
        import csv
        import io
        fmt = request.query_params.get('format_type', 'csv')
        qs = self.filter_queryset(self.get_queryset()).select_related('client', 'fy', 'period')[:10000]
        header = ['Task No', 'Client', 'Task type', 'FY', 'Period', 'Title', 'Status', 'Priority', 'Due date',
                  'Assigned to', 'Leader', 'Manager', 'Billing', 'Blocked', 'Created']
        rows = [[t.task_number, t.client.name, t.task_type_name_snapshot, t.fy.label if t.fy else '',
                 t.period.label if t.period else '', t.title, t.status, t.priority, t.due_date.isoformat(),
                 t.assigned_user.full_name if t.assigned_user else '', t.leader_user.full_name if t.leader_user else '',
                 t.manager_user.full_name if t.manager_user else '', t.billing_state,
                 'yes' if getattr(t, 'has_open_issue', False) else '', t.created_at.date().isoformat()] for t in qs]
        log_event('task.export', 'Task', '', format=fmt, rows=len(rows))
        if fmt == 'xlsx':
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = 'Tasks'
            ws.append(header)
            for r in rows:
                ws.append(r)
            buf = io.BytesIO()
            wb.save(buf)
            resp = HttpResponse(buf.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            resp['Content-Disposition'] = 'attachment; filename="tasks.xlsx"'
            return resp
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(header)
        w.writerows(rows)
        resp = HttpResponse(out.getvalue(), content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="tasks.csv"'
        return resp

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsAdminOrSuperAdmin])
    def bulk_shift_due_date(self, request):
        """Statutory extension (spec §5.3 DD3)."""
        firm = request.user.firm
        task_type_id = _uuid(request.data.get('task_type_id'), 'task_type_id')
        from apps.services.models import TaskType
        if not TaskType.objects.filter(id=task_type_id, service__category__firm=firm).exists():
            raise ValidationError({'task_type_id': 'Task type not found in this firm.'})
        period_id = request.data.get('period_id')
        period_id = _uuid(period_id, 'period_id') if period_id else None
        new_due_date = _date(request.data.get('new_due_date'), 'new_due_date')
        count = TaskService.bulk_shift_due_date(firm, request.user, task_type_id, new_due_date,
                                                period_id=period_id,
                                                reason=request.data.get('reason', 'Statutory extension'),
                                                request=request)
        return Response({'message': f'Shifted due date for {count} tasks to {new_due_date}.', 'count': count})

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsAdminOrSuperAdmin])
    def import_spreadsheet(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'Please upload a spreadsheet file.'}, status=status.HTTP_400_BAD_REQUEST)
        from .importer import TaskSpreadsheetImporter
        result = TaskSpreadsheetImporter.import_tasks(request.user.firm, file, user=request.user)
        log_event('task.import', 'Task', '', imported=result.get('imported_count'), errors=len(result.get('errors', [])))
        return Response(result)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated, IsAdminOrSuperAdmin])
    def download_template(self, request):
        from .importer import TaskSpreadsheetImporter
        response = HttpResponse(TaskSpreadsheetImporter.generate_template_csv(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="tasks_import_template.csv"'
        return response


class PersonalTodoViewSet(viewsets.ModelViewSet):
    serializer_class = PersonalTodoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PersonalTodo.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class StickyNoteViewSet(viewsets.ModelViewSet):
    serializer_class = StickyNoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return StickyNote.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TaskTimeLogViewSet(viewsets.ModelViewSet):
    """
    Read / edit / delete time logs. New logs are created with POST /tasks/{id}/log_time/
    so the task permission and day-total rules apply.
    Staff see only their own logs; admins see the whole firm.
    """
    serializer_class = TaskTimeLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsFirmMember]
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']
    EDIT_WINDOW = timedelta(days=1)

    def get_queryset(self):
        user = self.request.user
        if not user.firm:
            return TaskTimeLog.objects.none()
        qs = TaskTimeLog.objects.filter(task__firm=user.firm).select_related('user', 'task')
        if not (user.is_admin or user.is_superuser):
            qs = qs.filter(user=user)
        return qs

    def _check_window(self, request, time_log, verb):
        is_admin = request.user.is_admin or request.user.is_superuser
        within = (timezone.now() - time_log.created_at) < self.EDIT_WINDOW
        if not is_admin and not (time_log.user_id == request.user.id and within):
            log_permission_denied(request.user, f'time.{verb}', 'TaskTimeLog', time_log.id, 'edit window expired')
            raise PermissionDenied(f'Time log {verb} window has expired (1 day). Only an admin can {verb} past entries.')

    def update(self, request, *args, **kwargs):
        time_log = self.get_object()
        try:
            self._check_window(request, time_log, 'edit')
        except PermissionDenied as exc:
            return Response({'error': str(exc.detail)}, status=status.HTTP_403_FORBIDDEN)
        response = super().update(request, *args, **kwargs)
        log_event('time.edit', 'TaskTimeLog', time_log.id, task_id=time_log.task_id,
                  fields=sorted(k for k in request.data.keys()))
        return response

    def destroy(self, request, *args, **kwargs):
        time_log = self.get_object()
        try:
            self._check_window(request, time_log, 'delete')
        except PermissionDenied as exc:
            return Response({'error': str(exc.detail)}, status=status.HTTP_403_FORBIDDEN)
        log_event('time.delete', 'TaskTimeLog', time_log.id, task_id=time_log.task_id, minutes=time_log.minutes)
        return super().destroy(request, *args, **kwargs)
