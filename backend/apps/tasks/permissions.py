"""
Task-level authorization (spec §2.1, §2.2, §9 S5).

One place decides who may do what on a task. Views and services both call
these helpers, so the same rule applies to the UI, the API and the scheduler.
actor=None means the system (scheduler / worker) and is always allowed.
"""
from rest_framework.exceptions import PermissionDenied
from apps.common.logging import log_permission_denied

ROLE_ASSIGNED = 'assigned'
ROLE_LEADER = 'leader'
ROLE_MANAGER = 'manager'
ROLE_MEMBER = 'member'
ALL_ROLES = (ROLE_ASSIGNED, ROLE_LEADER, ROLE_MANAGER, ROLE_MEMBER)


def is_admin(user):
    return bool(user and (getattr(user, 'is_admin', False) or getattr(user, 'is_superuser', False)))


def task_roles(task, user):
    """Return the set of task roles the user holds on this task."""
    if user is None:
        return set()
    roles = set()
    if task.assigned_user_id == user.id:
        roles.add(ROLE_ASSIGNED)
    if task.leader_user_id == user.id:
        roles.add(ROLE_LEADER)
    if task.manager_user_id == user.id:
        roles.add(ROLE_MANAGER)
    if task.members.filter(user=user, removed_at__isnull=True).exists():
        roles.add(ROLE_MEMBER)
    return roles


def is_pool_task(task):
    return task.assigned_user_id is None and task.status in ('not_started', 'in_process')


def can_view(task, user):
    if user is None or is_admin(user):
        return True
    if task.status == 'deleted':
        return False
    if task_roles(task, user):
        return True
    return is_pool_task(task) and task.firm.allow_pickup


def can_work(task, user):
    """Comment, log time, tick/untick to-do, raise/resolve issue: any task role."""
    if user is None or is_admin(user):
        return True
    return bool(task_roles(task, user))


def can_reassign(task, user):
    """Assign / re-assign: Admin+, or leader/manager on this task."""
    if user is None or is_admin(user):
        return True
    return bool(task_roles(task, user) & {ROLE_LEADER, ROLE_MANAGER})


def can_edit_fields(task, user):
    """Edit title / description / priority / dates: Admin+, or leader/manager."""
    return can_reassign(task, user)


def can_change_status(task, user, new_status):
    """
    Status change: Admin+, or assigned/leader/manager.
    Completing as staff also needs firm.staff_can_complete and role assigned or leader.
    Delete and reopen are Admin+ only (checked in the service with a clear message).
    """
    if user is None or is_admin(user):
        return True
    roles = task_roles(task, user)
    if new_status == 'completed':
        return bool(task.firm.staff_can_complete and roles & {ROLE_ASSIGNED, ROLE_LEADER})
    return bool(roles & {ROLE_ASSIGNED, ROLE_LEADER, ROLE_MANAGER})


def can_tick_milestone(task, user, milestone):
    """Milestone: Admin+, or a task role listed in milestone.can_be_completed_by.
    An empty list means assigned / leader / manager."""
    if user is None or is_admin(user):
        return True
    allowed = set(milestone.can_be_completed_by or []) or {ROLE_ASSIGNED, ROLE_LEADER, ROLE_MANAGER}
    return bool(task_roles(task, user) & allowed)


def require(allowed, user, action, task=None, message=None):
    """Raise 403 and write a permission.denied log line when not allowed."""
    if allowed:
        return
    log_permission_denied(
        user, action, entity_type='Task',
        entity_id=getattr(task, 'id', ''),
        reason=message or 'not allowed',
    )
    raise PermissionDenied(message or 'You do not have permission to do this on this task.')


def permissions_for(task, user):
    """Flags for the UI so it shows only the actions the user can do."""
    roles = task_roles(task, user)
    admin = is_admin(user)
    return {
        'roles': sorted(roles),
        'is_admin': admin,
        'can_work': can_work(task, user),
        'can_reassign': can_reassign(task, user),
        'can_edit': can_edit_fields(task, user),
        'can_change_status': admin or bool(roles & {ROLE_ASSIGNED, ROLE_LEADER, ROLE_MANAGER}),
        'can_complete': can_change_status(task, user, 'completed'),
        'can_delete': admin,
        'can_reopen': admin,
        'can_pickup': is_pool_task(task) and bool(task.firm.allow_pickup),
    }
