"""
Single source of truth for task visibility and derived flags (spec §4.1, §6.3).

Dashboard counts and the task list both call these functions, so a tile
count and the list it opens can never disagree.
"""
from datetime import timedelta
from django.db.models import Q, Exists, OuterRef
from apps.tasks.models import Task, TaskIssue, TaskMember
from apps.common.dates import firm_today

S = Task.Status
PENDING = (S.NOT_STARTED, S.IN_PROCESS, S.ON_HOLD)
ACTIVE = (S.NOT_STARTED, S.IN_PROCESS)          # on_hold is excluded from overdue (spec §4 rule 3)
ROLE_PARAMS = ('assigned', 'leader', 'manager', 'member')

# Every dashboard tile key. The list endpoint accepts ?tile=<key>.
TILE_KEYS = (
    'pending', 'not_started', 'in_process', 'on_hold', 'priority_high',
    'due_today', 'due_in_7_days', 'overdue', 'long_due', 'with_issues',
    'waiting_on_client', 'completed', 'completed_fy', 'completed_this_month', 'unbilled', 'unassigned',
)
# Old ?date_filter= values still work
LEGACY_DATE_FILTERS = {'overdue': 'overdue', 'due_today': 'due_today',
                       'due_in_7_days': 'due_in_7_days', 'with_issues': 'with_issues'}


def base_queryset(firm, include_deleted=False):
    qs = Task.objects.filter(firm=firm)
    if not include_deleted:
        qs = qs.exclude(status=S.DELETED)
    return qs


def active_member_q(user_id):
    return Exists(TaskMember.objects.filter(task=OuterRef('pk'), user_id=user_id, removed_at__isnull=True))


def role_filter(qs, user_id, role=None):
    """Filter tasks where user_id holds `role` (or any role when role is empty)."""
    if role == 'assigned':
        return qs.filter(assigned_user_id=user_id)
    if role == 'leader':
        return qs.filter(leader_user_id=user_id)
    if role == 'manager':
        return qs.filter(manager_user_id=user_id)
    if role == 'member':
        return qs.filter(active_member_q(user_id))
    return qs.filter(Q(assigned_user_id=user_id) | Q(leader_user_id=user_id) |
                     Q(manager_user_id=user_id) | active_member_q(user_id))


def visible_to(qs, user):
    """Staff see tasks where they hold a role, plus the open unassigned pool."""
    if user.is_admin or user.is_superuser:
        return qs
    any_role = (Q(assigned_user_id=user.id) | Q(leader_user_id=user.id) |
                Q(manager_user_id=user.id) | active_member_q(user.id))
    if user.firm and user.firm.allow_pickup:
        pool = Q(assigned_user__isnull=True, status__in=ACTIVE)
        return qs.filter(any_role | pool)
    return qs.filter(any_role)


def open_issue_exists(client_side=None):
    sub = TaskIssue.objects.filter(task=OuterRef('pk'), status=TaskIssue.Status.OPEN)
    if client_side is not None:
        sub = sub.filter(label__is_client_side=client_side)
    return Exists(sub)


def annotate_flags(qs):
    return qs.annotate(has_open_issue=open_issue_exists(), has_client_issue=open_issue_exists(True))


def apply_tile(qs, key, firm, today=None):
    """Apply one dashboard tile rule. Unknown keys return qs unchanged."""
    today = today or firm_today(firm)
    if key == 'pending':
        return qs.filter(status__in=PENDING)
    if key in ('not_started', 'in_process', 'on_hold'):
        return qs.filter(status=key)
    if key == 'priority_high':
        return qs.filter(status__in=PENDING, priority=Task.Priority.HIGH)
    if key == 'due_today':
        return qs.filter(status__in=PENDING, due_date=today)
    if key == 'due_in_7_days':
        return qs.filter(status__in=PENDING, due_date__gt=today, due_date__lte=today + timedelta(days=7))
    if key == 'overdue':
        return qs.filter(status__in=ACTIVE, due_date__lt=today)
    if key == 'long_due':
        cutoff = today - timedelta(days=firm.long_due_days or 30)
        return qs.filter(status__in=PENDING, created_at__date__lt=cutoff)
    if key == 'with_issues':
        return qs.filter(status__in=PENDING).filter(open_issue_exists())
    if key == 'waiting_on_client':
        return qs.filter(status__in=PENDING).filter(open_issue_exists(True))
    if key == 'completed':
        return qs.filter(status=S.COMPLETED)
    if key == 'completed_fy':
        from apps.common.dates import current_fy
        fy = current_fy(firm, today)
        if fy is None:
            return qs.none()
        return qs.filter(status=S.COMPLETED, completed_at__date__gte=fy.start_date, completed_at__date__lte=fy.end_date)
    if key == 'completed_this_month':
        return qs.filter(status=S.COMPLETED, completed_at__date__gte=today.replace(day=1))
    if key == 'unbilled':
        return qs.filter(status=S.COMPLETED, billing_state=Task.BillingState.UNBILLED)
    if key == 'unassigned':
        return qs.filter(status__in=ACTIVE, assigned_user__isnull=True)
    return qs


def tile_counts(qs, firm, keys=TILE_KEYS, today=None):
    today = today or firm_today(firm)
    return {k: apply_tile(qs, k, firm, today).count() for k in keys}
