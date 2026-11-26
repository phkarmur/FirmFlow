import csv
import time
import uuid
from django.db.models import Count, Q
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from apps.accounts.permissions import IsFirmMember, IsAdminOrSuperAdmin
from apps.tasks.models import Task, TaskTimeLog, TaskAssignmentLog, TaskMember
from apps.tasks import selectors
from apps.accounts.models import User
from apps.services.models import TaskType
from apps.common.dates import firm_today
from apps.common.logging import log_event, log_permission_denied

S = Task.Status
MAX_ROWS = 500   # spec §8: no report sends more than 500 rows without paging


def _log_report(name, request, started, rows, **params):
    log_event('report.run', 'Report', name, duration_ms=round((time.monotonic() - started) * 1000, 2),
              row_count=rows, params={k: v for k, v in params.items() if v not in (None, '')})


def _csv(filename, header, rows):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    for r in rows:
        writer.writerow(r)
    return response


class OfficeDashboardStatsView(APIView):
    """Office dashboard tiles (spec §6.1). Same rules as the task list (?tile=<key>)."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        started = time.monotonic()
        firm = request.user.firm
        qs = selectors.base_queryset(firm)
        fy_id = request.query_params.get('fy_id')
        if fy_id:
            qs = qs.filter(fy_id=fy_id)
        counts = selectors.tile_counts(qs, firm)
        # Old key names kept so older UI builds keep working
        counts['with_pending_issues'] = counts['with_issues']
        counts['unassigned_pool'] = counts['unassigned']
        _log_report('office_dashboard', request, started, len(counts), fy_id=fy_id)
        return Response(counts)


class MyDashboardStatsView(APIView):
    """'My dashboard' (spec §6.2): counts on tasks ASSIGNED to me + counts by role."""
    permission_classes = [permissions.IsAuthenticated, IsFirmMember]

    def get(self, request):
        started = time.monotonic()
        user = request.user
        firm = user.firm
        today = firm_today(firm)
        base = selectors.base_queryset(firm)
        mine = selectors.role_filter(base, user.id, 'assigned')
        stats = {
            'my_pending': selectors.apply_tile(mine, 'pending', firm, today).count(),
            'my_priority': selectors.apply_tile(mine, 'priority_high', firm, today).count(),
            'my_due_today': selectors.apply_tile(mine, 'due_today', firm, today).count(),
            'my_due_7_days': selectors.apply_tile(mine, 'due_in_7_days', firm, today).count(),
            'my_overdue': selectors.apply_tile(mine, 'overdue', firm, today).count(),
            'my_with_issues': selectors.apply_tile(mine, 'with_issues', firm, today).count(),
            'my_completed_this_month': selectors.apply_tile(mine, 'completed_this_month', firm, today).count(),
            'by_role': {
                role: selectors.apply_tile(selectors.role_filter(base, user.id, role), 'pending', firm, today).count()
                for role in selectors.ROLE_PARAMS
            },
            'unassigned_available_to_pickup': (
                selectors.apply_tile(base, 'unassigned', firm, today).count() if firm.allow_pickup else 0),
        }
        _log_report('my_dashboard', request, started, 1)
        return Response(stats)


class EmployeeReportView(APIView):
    """
    Spec §8 reports 2 and 3. Rows = staff, columns = tile counts, ?role=assigned|leader|manager|member.
    Staff see their own row only (spec §2.2).
    """
    permission_classes = [permissions.IsAuthenticated, IsFirmMember]
    KEYS = ('pending', 'due_today', 'due_in_7_days', 'overdue', 'long_due', 'with_issues', 'completed')
    ROLE_FIELD = {'assigned': 'assigned_user_id', 'leader': 'leader_user_id', 'manager': 'manager_user_id'}

    def get(self, request):
        started = time.monotonic()
        firm = request.user.firm
        role = request.query_params.get('role') or 'assigned'
        if role not in selectors.ROLE_PARAMS:
            raise ValidationError({'role': f'Role must be one of {", ".join(selectors.ROLE_PARAMS)}.'})
        users = User.objects.filter(firm=firm, is_active=True).order_by('full_name')
        if not (request.user.is_admin or request.user.is_superuser):
            users = users.filter(id=request.user.id)
        base = selectors.base_queryset(firm)
        today = firm_today(firm)

        counts = {k: {} for k in self.KEYS}
        for key in self.KEYS:
            tiled = selectors.apply_tile(base, key, firm, today)
            if role == 'member':
                rows = TaskMember.objects.filter(task__in=tiled, removed_at__isnull=True) \
                    .values('user_id').annotate(c=Count('task_id', distinct=True))
                counts[key] = {r['user_id']: r['c'] for r in rows}
            else:
                field = self.ROLE_FIELD[role]
                rows = tiled.exclude(**{f'{field}__isnull': True}).values(field).annotate(c=Count('id'))
                counts[key] = {r[field]: r['c'] for r in rows}

        results = []
        for u in users:
            row = {'user_id': u.id, 'name': u.full_name, 'email': u.email, 'designation': u.designation,
                   'role': u.system_role, 'task_role': role}
            for key in self.KEYS:
                row[key] = counts[key].get(u.id, 0)
            results.append(row)
        _log_report('employees', request, started, len(results), role=role)

        if request.query_params.get('export') == 'csv':
            return _csv('employee_report.csv',
                        ['Staff Name', 'Email', 'Designation', 'Task Role', 'Pending', 'Due Today', 'Due in 7 Days',
                         'Overdue', 'Long Due', 'With Issues', 'Completed'],
                        [[r['name'], r['email'], r['designation'], role, r['pending'], r['due_today'], r['due_in_7_days'],
                          r['overdue'], r['long_due'], r['with_issues'], r['completed']] for r in results])
        return Response(results)


class TimeLogReportView(APIView):
    """Report 12. Staff see only their own logs (a user_id for someone else is refused)."""
    permission_classes = [permissions.IsAuthenticated, IsFirmMember]

    def get(self, request):
        started = time.monotonic()
        firm = request.user.firm
        is_admin = request.user.is_admin or request.user.is_superuser
        logs = TaskTimeLog.objects.filter(task__firm=firm).select_related('user', 'task', 'task__client')
        user_id = request.query_params.get('user_id')
        if not is_admin:
            if user_id and str(user_id) != str(request.user.id):
                log_permission_denied(request.user, 'report.timelogs', 'User', user_id, 'staff asked for another user')
                return Response({'error': 'You can only see your own time logs.'}, status=403)
            logs = logs.filter(user=request.user)
        elif user_id:
            logs = logs.filter(user_id=user_id)
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            logs = logs.filter(work_date__gte=start_date)
        if end_date:
            logs = logs.filter(work_date__lte=end_date)
        logs = logs.order_by('-work_date', '-created_at')
        row = lambda l: {
            'id': l.id, 'user_name': l.user.full_name, 'task_id': l.task_id,
            'task_number': l.task.task_number, 'task_title': l.task.title,
            'client_name': l.task.client.name, 'work_date': l.work_date, 'minutes': l.minutes,
            'hours': round(l.minutes / 60, 2), 'is_billable': l.is_billable, 'note': l.note,
            'task_status': l.task.status,
        }
        if request.query_params.get('export') == 'csv':
            return _csv('time_logs.csv', ['Date', 'Staff', 'Task', 'Client', 'Hours', 'Billable', 'Note'],
                        [[r['work_date'], r['user_name'], r['task_number'], r['client_name'], r['hours'], r['is_billable'], r['note']]
                         for r in (row(l) for l in logs[:10000])])
        from django.db.models import Sum
        p = _page(request, logs)
        results = [row(l) for l in p['slice']]
        _log_report('timelogs', request, started, len(results), user_id=user_id, start_date=start_date, end_date=end_date)
        return Response({'count': p['count'], 'page': p['page'], 'total_pages': p['total_pages'],
                         'total_hours': round((logs.aggregate(m=Sum('minutes'))['m'] or 0) / 60, 1), 'results': results})


class InactiveStaffTasksReportView(APIView):
    """Report 15: open tasks whose assigned user is inactive."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        started = time.monotonic()
        tasks = Task.objects.filter(firm=request.user.firm, assigned_user__is_active=False,
                                    status__in=selectors.PENDING).select_related('assigned_user', 'client')
        p = _page(request, tasks.order_by('due_date'))
        results = [{
            'task_id': t.id, 'task_number': t.task_number, 'title': t.title, 'client_name': t.client.name,
            'inactive_staff_name': t.assigned_user.full_name, 'inactive_staff_email': t.assigned_user.email,
            'due_date': t.due_date, 'status': t.status,
        } for t in p['slice']]
        _log_report('inactive_staff_tasks', request, started, len(results))
        return Response({'count': p['count'], 'page': p['page'], 'total_pages': p['total_pages'], 'results': results})


class ClientWiseReportView(APIView):
    """Report 7: client-wise task status (one grouped query, not one per client)."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        started = time.monotonic()
        firm = request.user.firm
        clients = firm.clients.filter(is_active=True).annotate(
            total_tasks=Count('tasks', filter=~Q(tasks__status=S.DELETED)),
            pending=Count('tasks', filter=Q(tasks__status__in=selectors.PENDING)),
            completed=Count('tasks', filter=Q(tasks__status=S.COMPLETED)),
            unbilled=Count('tasks', filter=Q(tasks__status=S.COMPLETED, tasks__billing_state=Task.BillingState.UNBILLED)),
        ).order_by('name')
        group_id = request.query_params.get('client_group')
        if group_id:
            clients = clients.filter(client_group_id=group_id)
        q = (request.query_params.get('search') or '').strip()
        if q:
            clients = clients.filter(name__icontains=q)
        row = lambda c: {'client_id': c.id, 'client_name': c.name, 'pan_masked': c.pan_masked, 'gstin': c.gstin,
                         'total_tasks': c.total_tasks, 'pending': c.pending, 'completed': c.completed, 'unbilled': c.unbilled}
        if request.query_params.get('export') == 'csv':
            return _csv('client_task_report.csv', ['Client Name', 'PAN', 'GSTIN', 'Total Tasks', 'Pending', 'Completed', 'Unbilled'],
                        [[r['client_name'], r['pan_masked'], r['gstin'], r['total_tasks'], r['pending'], r['completed'], r['unbilled']]
                         for r in (row(c) for c in clients[:10000])])
        p = _page(request, clients)
        results = [row(c) for c in p['slice']]
        _log_report('clients', request, started, len(results), client_group=group_id)
        return Response({'count': p['count'], 'page': p['page'], 'total_pages': p['total_pages'], 'results': results})


class TaskTypeWiseReportView(APIView):
    """Report 8: task-type-wise count by status."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        started = time.monotonic()
        firm = request.user.firm
        types = TaskType.objects.filter(service__category__firm=firm, is_active=True).select_related('service').annotate(
            total=Count('tasks', filter=~Q(tasks__status=S.DELETED)),
            not_started=Count('tasks', filter=Q(tasks__status=S.NOT_STARTED)),
            in_process=Count('tasks', filter=Q(tasks__status=S.IN_PROCESS)),
            on_hold=Count('tasks', filter=Q(tasks__status=S.ON_HOLD)),
            completed=Count('tasks', filter=Q(tasks__status=S.COMPLETED)),
        )
        results = [{'task_type_id': tt.id, 'name': tt.name, 'service': tt.service.name, 'code': tt.code,
                    'total': tt.total, 'not_started': tt.not_started, 'in_process': tt.in_process,
                    'on_hold': tt.on_hold, 'completed': tt.completed} for tt in types]
        _log_report('task_types', request, started, len(results))
        return Response(results)


class TaskActivityReportView(APIView):
    """Report 10: tasks created / completed / deleted between dates."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        started = time.monotonic()
        firm = request.user.firm
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        created_qs = Task.objects.filter(firm=firm)
        completed_qs = Task.objects.filter(firm=firm, completed_at__isnull=False)
        deleted_qs = Task.objects.filter(firm=firm, status=S.DELETED)
        if start_date:
            created_qs = created_qs.filter(created_at__date__gte=start_date)
            completed_qs = completed_qs.filter(completed_at__date__gte=start_date)
            deleted_qs = deleted_qs.filter(deleted_at__date__gte=start_date)
        if end_date:
            created_qs = created_qs.filter(created_at__date__lte=end_date)
            completed_qs = completed_qs.filter(completed_at__date__lte=end_date)
            deleted_qs = deleted_qs.filter(deleted_at__date__lte=end_date)
        data = {
            'created_count': created_qs.count(),
            'completed_count': completed_qs.count(),
            'deleted_count': deleted_qs.count(),
            'recent_created': [{'number': t.task_number, 'title': t.title, 'date': t.created_at}
                               for t in created_qs.order_by('-created_at')[:20]],
            'recent_completed': [{'number': t.task_number, 'title': t.title, 'date': t.completed_at}
                                 for t in completed_qs.order_by('-completed_at')[:20]],
            'recent_deleted': [{'number': t.task_number, 'title': t.title, 'reason': t.delete_reason, 'date': t.deleted_at}
                               for t in deleted_qs.order_by('-deleted_at')[:20]],
        }
        _log_report('activity', request, started, 3, start_date=start_date, end_date=end_date)
        return Response(data)


class DeletedTasksReportView(APIView):
    """Report 14: deleted tasks with reason."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        started = time.monotonic()
        tasks = Task.objects.filter(firm=request.user.firm, status=S.DELETED) \
            .select_related('client', 'deleted_by').order_by('-deleted_at')
        p = _page(request, tasks)
        results = [{'task_id': t.id, 'task_number': t.task_number, 'title': t.title, 'client_name': t.client.name,
                    'deleted_by': t.deleted_by.full_name if t.deleted_by else 'Unknown',
                    'delete_reason': t.delete_reason, 'deleted_at': t.deleted_at} for t in p['slice']]
        _log_report('deleted', request, started, len(results))
        return Response({'count': p['count'], 'page': p['page'], 'total_pages': p['total_pages'], 'results': results})


class AssignmentChangesReportView(APIView):
    """Report 13: assignment changes between dates."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        started = time.monotonic()
        logs = TaskAssignmentLog.objects.filter(task__firm=request.user.firm) \
            .select_related('task', 'old_user', 'new_user', 'changed_by')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            logs = logs.filter(changed_at__date__gte=start_date)
        if end_date:
            logs = logs.filter(changed_at__date__lte=end_date)
        p = _page(request, logs.order_by('-changed_at'))
        results = [{'task_id': l.task_id, 'task_number': l.task.task_number, 'field': l.field,
                    'old_user': l.old_user.full_name if l.old_user else 'Unassigned',
                    'new_user': l.new_user.full_name if l.new_user else 'Unassigned',
                    'changed_by': l.changed_by.full_name if l.changed_by else 'System',
                    'reason': l.reason, 'trigger': l.trigger, 'changed_at': l.changed_at} for l in p['slice']]
        _log_report('assignment_changes', request, started, len(results), start_date=start_date, end_date=end_date)
        return Response({'count': p['count'], 'page': p['page'], 'total_pages': p['total_pages'], 'results': results})


# ---------------------------------------------------------------------------- Phase B2 reports

def _page(request, rows):
    """Server paging for list reports: ?page=&page_size= (max 500). CSV export ignores paging."""
    try:
        page = max(1, int(request.query_params.get('page', 1)))
        size = min(500, max(1, int(request.query_params.get('page_size', 50))))
    except ValueError:
        raise ValidationError({'page': 'page and page_size must be numbers.'})
    total = len(rows) if isinstance(rows, list) else rows.count()
    start = (page - 1) * size
    return {'count': total, 'page': page, 'page_size': size,
            'total_pages': max(1, -(-total // size)), 'slice': rows[start:start + size]}


def _dates(request):
    return request.query_params.get('start_date') or None, request.query_params.get('end_date') or None


class ServiceStaffGridView(APIView):
    """Report 9: service x staff grid of PENDING tasks (by task role, default assigned)."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]
    FIELD = {'assigned': 'assigned_user_id', 'leader': 'leader_user_id', 'manager': 'manager_user_id'}

    def get(self, request):
        started = time.monotonic()
        firm = request.user.firm
        role = request.query_params.get('role') or 'assigned'
        if role not in self.FIELD:
            raise ValidationError({'role': 'Role must be assigned, leader or manager.'})
        tile = request.query_params.get('tile') or 'pending'
        if tile not in selectors.TILE_KEYS:
            raise ValidationError({'tile': 'Unknown tile.'})
        qs = selectors.apply_tile(selectors.base_queryset(firm), tile, firm)
        field = self.FIELD[role]
        rows = qs.exclude(**{f'{field}__isnull': True}).values(
            'task_type__service_id', 'task_type__service__name', 'task_type__service__category__name', field
        ).annotate(c=Count('id'))
        users = {u.id: u.full_name for u in User.objects.filter(firm=firm, is_active=True).order_by('full_name')}
        services, grid = {}, {}
        for r in rows:
            sid = r['task_type__service_id']
            services[sid] = f"{r['task_type__service__category__name']} → {r['task_type__service__name']}"
            grid.setdefault(str(sid), {})[str(r[field])] = r['c']
        data = {
            'role': role, 'tile': tile,
            'users': [{'id': str(k), 'name': v} for k, v in users.items()],
            'services': [{'id': str(k), 'name': v} for k, v in sorted(services.items(), key=lambda x: x[1])],
            'grid': grid,
        }
        _log_report('service_staff_grid', request, started, len(services), role=role, tile=tile)
        if request.query_params.get('export') == 'csv':
            return _csv('service_staff_grid.csv', ['Service'] + [u['name'] for u in data['users']],
                        [[s['name']] + [grid.get(s['id'], {}).get(u['id'], 0) for u in data['users']] for s in data['services']])
        return Response(data)


class IssuesReportView(APIView):
    """Reports 5 and 11: open issues by label, and issues raised / resolved between dates."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        from apps.tasks.models import TaskIssue
        started = time.monotonic()
        firm = request.user.firm
        start, end = _dates(request)
        issues = TaskIssue.objects.filter(task__firm=firm).exclude(task__status=S.DELETED) \
            .select_related('task', 'task__client', 'label', 'raised_by', 'resolved_by')
        by_label = list(issues.filter(status='open').values('label__name', 'label__is_client_side')
                        .annotate(open=Count('id')).order_by('-open'))
        raised = issues
        resolved = issues.filter(status='resolved')
        if start:
            raised = raised.filter(raised_at__date__gte=start)
            resolved = resolved.filter(resolved_at__date__gte=start)
        if end:
            raised = raised.filter(raised_at__date__lte=end)
            resolved = resolved.filter(resolved_at__date__lte=end)
        status_filter = request.query_params.get('status') or 'open'
        listing = issues.filter(status=status_filter) if status_filter in ('open', 'resolved') else issues
        label = request.query_params.get('label')
        if label:
            listing = listing.filter(label__name=label)
        if start:
            listing = listing.filter(raised_at__date__gte=start)
        if end:
            listing = listing.filter(raised_at__date__lte=end)
        listing = listing.order_by('-raised_at')
        today = firm_today(firm)

        def row(i):
            return {'id': str(i.id), 'task_id': str(i.task_id), 'task_number': i.task.task_number,
                    'client_name': i.task.client.name, 'label': i.label.name, 'detail': i.detail,
                    'status': i.status, 'raised_by': i.raised_by.full_name if i.raised_by else '',
                    'raised_at': i.raised_at, 'due_date': i.due_date,
                    'is_overdue': bool(i.status == 'open' and i.due_date and i.due_date < today),
                    'resolved_by': i.resolved_by.full_name if i.resolved_by else '', 'resolved_at': i.resolved_at}
        if request.query_params.get('export') == 'csv':
            rows = [row(i) for i in listing[:10000]]
            return _csv('issues.csv', ['Task', 'Client', 'Issue', 'Detail', 'Status', 'Raised by', 'Raised at', 'Follow-up', 'Resolved by', 'Resolved at'],
                        [[r['task_number'], r['client_name'], r['label'], r['detail'], r['status'], r['raised_by'],
                          r['raised_at'], r['due_date'], r['resolved_by'], r['resolved_at']] for r in rows])
        p = _page(request, listing)
        data = {'by_label': by_label, 'raised_count': raised.count(), 'resolved_count': resolved.count(),
                'overdue_followups': issues.filter(status='open', due_date__lt=today).count(),
                'count': p['count'], 'page': p['page'], 'total_pages': p['total_pages'],
                'results': [row(i) for i in p['slice']]}
        _log_report('issues', request, started, len(data['results']), start_date=start, end_date=end, status=status_filter, label=label)
        return Response(data)


class PerformersReportView(APIView):
    """Spec §6.1-14 live activity: per staff counts between dates + top / bottom by a metric."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]
    METRICS = ('completed', 'hours', 'issues_resolved', 'comments')

    def get(self, request):
        from django.db.models import Sum
        from apps.tasks.models import TaskIssue, TaskComment
        started = time.monotonic()
        firm = request.user.firm
        start, end = _dates(request)
        metric = request.query_params.get('metric') or 'completed'
        if metric not in self.METRICS:
            raise ValidationError({'metric': f'Metric must be one of {", ".join(self.METRICS)}.'})

        def rng(qs, field):
            if start:
                qs = qs.filter(**{f'{field}__date__gte' if field.endswith('_at') else f'{field}__gte': start})
            if end:
                qs = qs.filter(**{f'{field}__date__lte' if field.endswith('_at') else f'{field}__lte': end})
            return qs
        completed = dict(rng(Task.objects.filter(firm=firm, status=S.COMPLETED), 'completed_at')
                         .values_list('completed_by').annotate(c=Count('id')))
        minutes = dict(rng(TaskTimeLog.objects.filter(task__firm=firm), 'work_date')
                       .values_list('user').annotate(m=Sum('minutes')))
        resolved = dict(rng(TaskIssue.objects.filter(task__firm=firm, status='resolved'), 'resolved_at')
                        .values_list('resolved_by').annotate(c=Count('id')))
        comments = dict(rng(TaskComment.objects.filter(task__firm=firm), 'created_at')
                        .values_list('user').annotate(c=Count('id')))
        rows = []
        for u in User.objects.filter(firm=firm, is_active=True).order_by('full_name'):
            rows.append({'user_id': str(u.id), 'name': u.full_name, 'role': u.system_role,
                         'completed': completed.get(u.id, 0), 'hours': round((minutes.get(u.id) or 0) / 60, 1),
                         'issues_resolved': resolved.get(u.id, 0), 'comments': comments.get(u.id, 0)})
        ranked = sorted(rows, key=lambda r: r[metric], reverse=True)
        data = {'metric': metric, 'rows': rows, 'top': ranked[:3], 'bottom': list(reversed(ranked[-3:])) if len(ranked) > 3 else []}
        _log_report('performers', request, started, len(rows), metric=metric, start_date=start, end_date=end)
        if request.query_params.get('export') == 'csv':
            return _csv('staff_activity.csv', ['Staff', 'Completed', 'Hours', 'Issues resolved', 'Comments'],
                        [[r['name'], r['completed'], r['hours'], r['issues_resolved'], r['comments']] for r in rows])
        return Response(data)


class AuditLogView(APIView):
    """Spec §6.1-15: searchable, read-only audit log (Admin+). Filters: action, entity_type, entity_id, actor, dates."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        from apps.common.models import AuditLog
        started = time.monotonic()
        qs = AuditLog.objects.filter(firm_id=request.user.firm_id)
        q = request.query_params
        if q.get('action'):
            qs = qs.filter(action__icontains=q['action'])
        if q.get('entity_type'):
            qs = qs.filter(entity_type=q['entity_type'])
        if q.get('entity_id'):
            qs = qs.filter(entity_id=q['entity_id'])
        if q.get('actor') == 'system':
            # Entries made by the system (scheduled jobs etc.) have no user
            qs = qs.filter(actor_user_id__isnull=True)
        elif q.get('actor'):
            try:
                qs = qs.filter(actor_user_id=uuid.UUID(q['actor']))
            except ValueError:
                raise ValidationError({'actor': 'Not a valid user id.'})
        start, end = _dates(request)
        if start:
            qs = qs.filter(created_at__date__gte=start)
        if end:
            qs = qs.filter(created_at__date__lte=end)
        qs = qs.order_by('-created_at')
        names = dict(User.objects.filter(firm_id=request.user.firm_id).values_list('id', 'full_name'))

        def row(a):
            return {'id': str(a.id), 'created_at': a.created_at, 'actor': names.get(a.actor_user_id, 'System' if a.actor_type == 'system' else '?'),
                    'action': a.action, 'entity_type': a.entity_type, 'entity_id': a.entity_id,
                    'old_value': a.old_value, 'new_value': a.new_value, 'ip': a.ip}
        if q.get('export') == 'csv':
            return _csv('audit_log.csv', ['Time', 'Actor', 'Action', 'Entity', 'Entity id', 'Old', 'New', 'IP'],
                        [[r['created_at'], r['actor'], r['action'], r['entity_type'], r['entity_id'], r['old_value'], r['new_value'], r['ip']]
                         for r in (row(a) for a in qs[:10000])])
        p = _page(request, qs)
        _log_report('audit_log', request, started, len(p['slice']) if hasattr(p['slice'], '__len__') else 0)
        # "Who" filter: every person who has at least one entry in this firm's log (also inactive staff)
        base = AuditLog.objects.filter(firm_id=request.user.firm_id)
        actor_ids = list(base.exclude(actor_user_id__isnull=True).order_by('actor_user_id').values_list('actor_user_id', flat=True).distinct())
        actors = sorted(({'id': str(i), 'name': names.get(i, '?')} for i in actor_ids), key=lambda a: a['name'].lower())
        if base.filter(actor_user_id__isnull=True).exists():
            actors.append({'id': 'system', 'name': 'System'})
        log_event('report.audit_log.filters', entity_type='report', actor_user_id=request.user.id,
                  actor_filter=q.get('actor', ''), action_filter=q.get('action', ''), actor_options=len(actors))
        return Response({'count': p['count'], 'page': p['page'], 'total_pages': p['total_pages'],
                         'results': [row(a) for a in p['slice']],
                         # order_by('action') removes the model's default ordering, so distinct() really returns each action once
                         'actors': actors,
                         'actions': list(AuditLog.objects.filter(firm_id=request.user.firm_id).order_by('action').values_list('action', flat=True).distinct()[:200])})
