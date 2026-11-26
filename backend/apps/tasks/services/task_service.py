import re
import time
from datetime import date
from django.db import transaction, IntegrityError
from django.db.models import F, Sum
from django.utils import timezone
from rest_framework.exceptions import (
    PermissionDenied, ValidationError as DRFValidationError, APIException,
)
from apps.tasks.models import (
    Task, TaskSequence, TaskMember, TaskMilestoneProgress,
    TaskTodo, TaskIssue, TaskComment, TaskTimeLog,
    TaskAssignmentLog, TaskStatusLog
)
from apps.services.models import TaskType, PendingIssueLabel
from apps.accounts.models import User
from apps.common.models import AuditLog
from apps.common.logging import log_event
from apps.common.dates import firm_today
from apps.notifications.models import Notification
from apps.notifications.service import notify, roles_of, name as uname
from apps.tasks import permissions as perm
from apps.tasks.services.due_dates import calculate_due_date


class TaskConflict(APIException):
    """Optimistic locking failure (spec §4 rule 7)."""
    status_code = 409
    default_detail = 'Conflict: someone else changed this task. Please refresh and try again.'
    default_code = 'conflict'


S = Task.Status

# Spec §4 state machine. Anything not listed is forbidden.
ALLOWED_TRANSITIONS = {
    # not_started -> on_hold: waiting on the client before work starts.
    # not_started -> completed: small tasks done in one step (completion checks still apply).
    S.NOT_STARTED: {S.IN_PROCESS, S.ON_HOLD, S.COMPLETED, S.DELETED},
    S.IN_PROCESS: {S.ON_HOLD, S.COMPLETED, S.DELETED},
    S.ON_HOLD: {S.IN_PROCESS, S.DELETED},
    S.COMPLETED: {S.IN_PROCESS, S.DELETED},   # completed -> in_process = reopen (Admin+)
    S.DELETED: set(),                          # soft delete is final; task_number never reused
}
PENDING_STATUSES = (S.NOT_STARTED, S.IN_PROCESS, S.ON_HOLD)
ROLE_FIELDS = ('assigned', 'leader', 'manager')
EDITABLE_FIELDS = ('title', 'description', 'priority', 'due_date', 'start_date')


class TaskService:
    """
    Central service layer: every task rule, permission check and log line
    lives here, so UI, API, import and scheduler behave the same way.
    actor=None means the system (scheduler / import without a user).
    """

    # ------------------------------------------------------------------ helpers
    @classmethod
    def _lock(cls, task, expected_version=None):
        """Re-read the task with a row lock. Fail with 409 if the version differs."""
        fresh = Task.objects.select_for_update().select_related('firm').get(pk=task.pk)
        if expected_version not in (None, ''):
            try:
                expected = int(expected_version)
            except (TypeError, ValueError):
                raise DRFValidationError({'version': 'Version must be a number.'})
            if fresh.version != expected:
                log_event('task.conflict', 'Task', fresh.id, result='error', level='WARNING',
                          expected_version=expected, actual_version=fresh.version)
                raise TaskConflict()
        return fresh

    @classmethod
    def _validate_user(cls, user, firm, field):
        if user is None:
            return
        if user.firm_id != firm.id:
            raise DRFValidationError({field: 'User does not belong to this firm.'})
        if not user.is_active:
            raise DRFValidationError({field: 'User is inactive and cannot be given a task role.'})

    @classmethod
    def calculate_default_due_date(cls, task_type: TaskType, period=None, reference_date=None, fy=None) -> date:
        due, why = calculate_due_date(task_type.default_due_rule, period=period, fy=fy, today=reference_date)
        log_event('task.due_rule', 'TaskType', task_type.id, rule=task_type.default_due_rule,
                  period=getattr(period, 'label', None), fy=getattr(fy, 'label', None),
                  due_date=due, explanation=why)
        return due

    # ------------------------------------------------------------------ create
    @classmethod
    @transaction.atomic
    def create_task(cls, firm, branch, client, task_type, creator,
                    fy=None, period=None, assigned_user=None, leader_user=None,
                    manager_user=None, due_date=None, priority='normal',
                    description='', title=None, source='manual', bulk_batch_run_id=None,
                    request=None) -> Task:
        started = time.monotonic()
        if client.firm_id != firm.id:
            raise DRFValidationError({'client': 'Client does not belong to this firm.'})
        if not client.is_active:
            raise DRFValidationError({'client': 'Cannot create task for an inactive client.'})
        if client.is_blocked_for_new_tasks:
            raise DRFValidationError({'client': 'Client is blocked for new tasks (e.g. pending fees).'})
        if task_type.service.category.firm_id != firm.id:
            raise DRFValidationError({'task_type': 'Task type does not belong to this firm.'})
        if not task_type.is_active:
            raise DRFValidationError({'task_type': 'Task type is inactive.'})
        if period is not None:
            if fy is None:
                fy = period.fy
            elif period.fy_id != fy.id:
                raise DRFValidationError({'period': 'Period does not belong to the selected financial year.'})
        if fy is not None and fy.firm_id != firm.id:
            raise DRFValidationError({'fy': 'Financial year does not belong to this firm.'})
        cls._validate_user(assigned_user, firm, 'assigned_user')
        cls._validate_user(leader_user, firm, 'leader_user')
        cls._validate_user(manager_user, firm, 'manager_user')
        if branch is None:
            branch = firm.branches.filter(is_default=True).first() or firm.branches.first()
        elif branch.firm_id != firm.id:
            raise DRFValidationError({'branch': 'Branch does not belong to this firm.'})

        today = firm_today(firm)
        if not due_date:
            due_date = cls.calculate_default_due_date(task_type, period, reference_date=today, fy=fy)
            due_date_source = 'rule'
        else:
            due_date_source = 'manual'

        if not title:
            period_label = period.label if period else (f"FY {fy.label}" if fy else "")
            components = [task_type.name]
            if period_label:
                components.append(period_label)
            components.append(client.name)
            title = " · ".join(components)

        task_number = TaskSequence.get_next_number(firm, today.year)

        try:
            with transaction.atomic():
                task = Task.objects.create(
                    firm=firm, branch=branch, task_number=task_number,
                    client=client, task_type=task_type, task_type_name_snapshot=task_type.name,
                    fy=fy, period=period, title=title, description=description or '',
                    priority=priority or 'normal', due_date=due_date, due_date_source=due_date_source,
                    assigned_user=assigned_user, leader_user=leader_user, manager_user=manager_user,
                    created_by=creator, source=source, bulk_batch_run_id=bulk_batch_run_id,
                    status=S.NOT_STARTED, version=1,
                )
        except IntegrityError:
            log_event('task.create', 'Task', '', result='error', level='WARNING',
                      reason='duplicate', client_id=client.id, task_type_id=task_type.id,
                      period=getattr(period, 'label', None))
            raise DRFValidationError({'duplicate': (
                f"A task for {client.name} / {task_type.name} / "
                f"{period.label if period else 'this period'} already exists."
            )})

        TaskTodo.objects.bulk_create([
            TaskTodo(task=task, text=t.text, sort_order=t.sort_order,
                     is_mandatory=t.is_mandatory, source=TaskTodo.Source.TEMPLATE)
            for t in task_type.todo_templates.all().order_by('sort_order')
        ])
        TaskMilestoneProgress.objects.bulk_create([
            TaskMilestoneProgress(task=task, milestone=ms, status=TaskMilestoneProgress.State.PENDING)
            for ms in task_type.milestones.all().order_by('sort_order')
        ])

        trigger = TaskAssignmentLog.Trigger.MANUAL if source == 'manual' else TaskAssignmentLog.Trigger.BULK
        for field, user in (('assigned', assigned_user), ('leader', leader_user), ('manager', manager_user)):
            if user:
                TaskAssignmentLog.objects.create(task=task, field=field, old_user=None, new_user=user,
                                                 changed_by=creator, trigger=trigger)

        AuditLog.log(firm_id=firm.id, action='task.create', entity_type='Task', entity_id=str(task.id),
                     actor_user_id=creator.id if creator else None,
                     actor_type='user' if creator else 'system',
                     new_value={'task_number': task.task_number, 'title': task.title, 'client': client.name},
                     request=request)
        if assigned_user:
            notify(Notification.Kind.TASK_ASSIGNED, [assigned_user], f'{uname(creator)} assigned you {task.task_number}',
                   body=task.title, task=task, actor=creator)
        for role_name, u in (('leader', leader_user), ('manager', manager_user)):
            if u:
                notify(Notification.Kind.ROLE_GRANTED, [u], f'You are the {role_name} on {task.task_number}',
                       body=task.title, task=task, actor=creator)
        log_event('task.create', 'Task', task.id, actor_user_id=getattr(creator, 'id', None),
                  duration_ms=round((time.monotonic() - started) * 1000, 2),
                  task_number=task.task_number, source=source, due_date=due_date,
                  due_date_source=due_date_source, past_due_at_creation=due_date < today)
        return task

    # ------------------------------------------------------------------ edit
    @classmethod
    @transaction.atomic
    def update_fields(cls, task, user, changes: dict, expected_version=None, request=None) -> Task:
        """Edit title / description / priority / due_date / start_date (Admin+, leader, manager)."""
        task = cls._lock(task, expected_version)
        perm.require(perm.can_edit_fields(task, user), user, 'task.edit', task,
                     'Only an Admin, or the leader or manager of this task, can edit it.')
        if task.status == S.DELETED:
            raise DRFValidationError({'error': 'A deleted task cannot be edited.'})
        old, new = {}, {}
        for key, value in changes.items():
            if key not in EDITABLE_FIELDS:
                continue
            if getattr(task, key) != value:
                old[key] = str(getattr(task, key))
                new[key] = str(value)
                setattr(task, key, value)
        if not new:
            return task
        if 'due_date' in new:
            task.due_date_source = 'manual'
        task.version += 1
        task.save()
        AuditLog.log(firm_id=task.firm_id, action='task.edit', entity_type='Task', entity_id=str(task.id),
                     actor_user_id=user.id, old_value=old, new_value=new, request=request)
        log_event('task.edit', 'Task', task.id, actor_user_id=user.id, old=old, new=new, version=task.version)
        return task

    # ------------------------------------------------------------------ assignment
    @classmethod
    @transaction.atomic
    def pickup_task(cls, task: Task, user: User, request=None) -> Task:
        """§5.4 A3 self-pickup from the unassigned pool."""
        task = cls._lock(task)
        if not task.firm.allow_pickup:
            raise DRFValidationError({'error': 'Task pickup is not enabled for this firm.'})
        if task.assigned_user_id and task.assigned_user_id != user.id:
            raise DRFValidationError({'error': f'Task is already assigned to {task.assigned_user.full_name}.'})
        if task.status not in (S.NOT_STARTED, S.IN_PROCESS):
            raise DRFValidationError({'error': 'Only open tasks can be picked up.'})
        if not user.is_active:
            raise PermissionDenied('Inactive users cannot pick up tasks.')

        old_user = task.assigned_user
        task.assigned_user = user
        task.version += 1
        task.save(update_fields=['assigned_user', 'version', 'updated_at'])
        TaskAssignmentLog.objects.create(task=task, field=TaskAssignmentLog.Field.ASSIGNED,
                                         old_user=old_user, new_user=user, changed_by=user,
                                         reason='Picked up from unassigned pool',
                                         trigger=TaskAssignmentLog.Trigger.PICKUP)
        AuditLog.log(firm_id=task.firm_id, action='task.pickup', entity_type='Task', entity_id=str(task.id),
                     actor_user_id=user.id, new_value={'assigned_user': user.full_name}, request=request)
        log_event('task.assign_change', 'Task', task.id, actor_user_id=user.id, field='assigned',
                  old=getattr(old_user, 'id', None), new=user.id, trigger='pickup')
        notify(Notification.Kind.TASK_REASSIGNED, [task.leader_user, task.manager_user],
               f'{user.full_name} picked up {task.task_number}', body=task.title, task=task, actor=user)
        return task

    @classmethod
    @transaction.atomic
    def reassign_task(cls, task: Task, field: str, new_user, changed_by, reason: str = '',
                      request=None, expected_version=None, trigger=TaskAssignmentLog.Trigger.MANUAL) -> Task:
        """Assign / re-assign assigned, leader or manager (spec §5.4 A1, A2)."""
        if field not in ROLE_FIELDS:
            raise DRFValidationError({'field': f'Field must be one of: {", ".join(ROLE_FIELDS)}.'})
        task = cls._lock(task, expected_version)
        perm.require(perm.can_reassign(task, changed_by), changed_by, f'task.reassign_{field}', task,
                     'Only an Admin, or the leader or manager of this task, can re-assign it.')
        if task.status == S.DELETED:
            raise DRFValidationError({'error': 'A deleted task cannot be re-assigned.'})
        reason = (reason or '').strip()
        if len(reason) < 3:
            raise DRFValidationError({'reason': 'A valid reason (minimum 3 characters) is required for re-assignment.'})
        cls._validate_user(new_user, task.firm, 'new_user_id')

        old_user = getattr(task, f"{field}_user")
        if (old_user and new_user and old_user.id == new_user.id) or (old_user is None and new_user is None):
            raise DRFValidationError({'new_user_id': 'This user already holds this role on the task.'})

        setattr(task, f"{field}_user", new_user)
        task.version += 1
        task.save(update_fields=[f"{field}_user", 'version', 'updated_at'])
        TaskAssignmentLog.objects.create(task=task, field=field, old_user=old_user, new_user=new_user,
                                         changed_by=changed_by, reason=reason, trigger=trigger)
        AuditLog.log(firm_id=task.firm_id, action=f'task.reassign_{field}', entity_type='Task',
                     entity_id=str(task.id), actor_user_id=getattr(changed_by, 'id', None),
                     old_value={'user': old_user.full_name if old_user else None},
                     new_value={'user': new_user.full_name if new_user else None, 'reason': reason},
                     request=request)
        log_event('task.assign_change', 'Task', task.id, actor_user_id=getattr(changed_by, 'id', None),
                  field=field, old=getattr(old_user, 'id', None), new=getattr(new_user, 'id', None),
                  trigger=trigger)
        cls._notify_reassign(task, field, old_user, new_user, changed_by, reason)
        return task

    @classmethod
    def _notify_reassign(cls, task, field, old_user, new_user, actor, reason):
        """Spec §7.1: new assignee, old assignee, new leader/manager, and the leader of the task."""
        who = uname(actor)
        if field == 'assigned':
            if new_user:
                notify(Notification.Kind.TASK_ASSIGNED, [new_user], f'{who} assigned you {task.task_number}',
                       body=f'{task.title}\nReason: {reason}', task=task, actor=actor)
            if old_user:
                notify(Notification.Kind.TASK_REASSIGNED, [old_user], f'{task.task_number} was re-assigned away from you',
                       body=f'Now with: {uname(new_user) if new_user else "Unassigned pool"}\nReason: {reason}',
                       task=task, actor=actor)
            if task.leader_user and task.leader_user not in (old_user, new_user):
                notify(Notification.Kind.TASK_REASSIGNED, [task.leader_user],
                       f'{who} re-assigned {task.task_number}, which you lead',
                       body=f'{uname(old_user) if old_user else "Pool"} -> {uname(new_user) if new_user else "Pool"}\nReason: {reason}',
                       task=task, actor=actor)
        else:
            if new_user:
                notify(Notification.Kind.ROLE_GRANTED, [new_user], f'You are now the {field} on {task.task_number}',
                       body=f'{task.title}\nReason: {reason}', task=task, actor=actor)
            if old_user:
                notify(Notification.Kind.TASK_REASSIGNED, [old_user], f'You are no longer the {field} on {task.task_number}',
                       body=f'Reason: {reason}', task=task, actor=actor)

    # ------------------------------------------------------------------ status
    @classmethod
    @transaction.atomic
    def update_status(cls, task: Task, new_status: str, changed_by, reason: str = '',
                      on_hold_reason: str = '', request=None, expected_version=None,
                      enforce_permission=True) -> Task:
        """
        Enforces the §4 state machine. enforce_permission=False is used only for
        automatic moves made by this service (rule 1: not_started -> in_process).
        """
        valid = {c for c, _ in S.choices}
        if new_status not in valid:
            raise DRFValidationError({'status': f'Unknown status "{new_status}".'})
        task = cls._lock(task, expected_version)
        old_status = task.status
        if old_status == new_status:
            return task

        if new_status not in ALLOWED_TRANSITIONS.get(old_status, set()):
            log_event('task.status_change', 'Task', task.id, result='error', level='WARNING',
                      actor_user_id=getattr(changed_by, 'id', None), old=old_status, new=new_status,
                      reason='transition not allowed')
            raise DRFValidationError({'status': f'Cannot move a task from "{old_status}" to "{new_status}".'})

        if enforce_permission:
            if new_status == S.DELETED or (old_status == S.COMPLETED and new_status == S.IN_PROCESS):
                what = 'delete' if new_status == S.DELETED else 'reopen'
                perm.require(changed_by is None or perm.is_admin(changed_by), changed_by, f'task.{what}', task,
                             f'Only an Admin or Superadmin can {what} a task.')
            else:
                msg = ('You cannot complete this task. Ask the task leader or an Admin.'
                       if new_status == S.COMPLETED else
                       'Only an Admin, or the assigned user, leader or manager, can change the status.')
                perm.require(perm.can_change_status(task, changed_by, new_status), changed_by,
                             'task.status_change', task, msg)

        if new_status == S.ON_HOLD:
            if not (on_hold_reason or '').strip():
                raise DRFValidationError({'on_hold_reason': 'Reason is required when placing a task on hold.'})
            task.on_hold_reason = on_hold_reason.strip()
        elif old_status == S.ON_HOLD:
            task.on_hold_reason = ''

        if new_status == S.COMPLETED:
            cls.validate_can_complete(task, actor=changed_by)
            task.completed_at = timezone.now()
            task.completed_by = changed_by

        if old_status == S.COMPLETED and new_status == S.IN_PROCESS:
            # Phase 2 will also require billing_state == unbilled (spec §4 rule 5)
            task.completed_at = None
            task.completed_by = None

        if new_status == S.DELETED:
            if not (reason or '').strip():
                raise DRFValidationError({'reason': 'A reason is required to delete a task.'})
            task.deleted_at = timezone.now()
            task.deleted_by = changed_by
            task.delete_reason = reason.strip()

        task.status = new_status
        task.version += 1
        task.save()

        log_reason = reason or on_hold_reason
        TaskStatusLog.objects.create(task=task, old_status=old_status, new_status=new_status,
                                     changed_by=changed_by, reason=log_reason)
        AuditLog.log(firm_id=task.firm_id, action='task.status_change', entity_type='Task',
                     entity_id=str(task.id), actor_user_id=getattr(changed_by, 'id', None),
                     actor_type='user' if changed_by else 'system',
                     old_value={'status': old_status}, new_value={'status': new_status, 'reason': log_reason},
                     request=request)
        log_event('task.delete' if new_status == S.DELETED else 'task.status_change', 'Task', task.id,
                  actor_user_id=getattr(changed_by, 'id', None), old=old_status, new=new_status,
                  reason=log_reason, version=task.version, automatic=not enforce_permission)
        if new_status == S.COMPLETED:
            notify(Notification.Kind.TASK_COMPLETED, [task.leader_user, task.manager_user, task.created_by],
                   f'{uname(changed_by)} completed {task.task_number}', body=task.title, task=task, actor=changed_by)
        elif new_status == S.DELETED:
            notify(Notification.Kind.TASK_DELETED, roles_of(task), f'{task.task_number} was deleted',
                   body=f'{task.title}\nReason: {log_reason}', task=task, actor=changed_by)
        return task

    @classmethod
    def validate_can_complete(cls, task: Task, actor=None):
        """§4 rule 2: mandatory to-dos done, all milestones done/skipped, no blocking issue open."""
        blockers = []
        for t in task.todos.filter(is_mandatory=True, is_done=False):
            blockers.append(f"Mandatory to-do open: '{t.text}'")
        for iss in task.issues.filter(status=TaskIssue.Status.OPEN, label__blocks_completion=True).select_related('label'):
            blockers.append(f"Open blocking issue: '{iss.label.name}'")
        for mp in task.milestone_progress.filter(status=TaskMilestoneProgress.State.PENDING).select_related('milestone'):
            blockers.append(f"Milestone not done: '{mp.milestone.name}'")
        if blockers:
            log_event('task.complete_blocked', 'Task', task.id, result='error', level='INFO',
                      actor_user_id=getattr(actor, 'id', None), open_items=blockers)
            raise DRFValidationError({'completion_blocked': blockers})

    @classmethod
    @transaction.atomic
    def soft_delete(cls, task: Task, user, reason: str, request=None, expected_version=None) -> Task:
        """Soft delete with a mandatory reason. Goes through the state machine."""
        return cls.update_status(task, S.DELETED, changed_by=user, reason=reason,
                                 request=request, expected_version=expected_version)

    @classmethod
    def _auto_start(cls, task, user, why):
        """Spec §4 rule 1: first activity moves not_started -> in_process."""
        if task.status == S.NOT_STARTED:
            return cls.update_status(task, S.IN_PROCESS, changed_by=user, reason=why, enforce_permission=False)
        return task

    @classmethod
    def _require_not_deleted(cls, task, what):
        if task.status == S.DELETED:
            raise DRFValidationError({'error': f'Cannot {what} on a deleted task.'})

    # ------------------------------------------------------------------ milestones
    @classmethod
    @transaction.atomic
    def tick_milestone(cls, task: Task, milestone_progress: TaskMilestoneProgress,
                       user, note: str = '', request=None, expected_version=None) -> TaskMilestoneProgress:
        task = cls._lock(task, expected_version)
        ms = milestone_progress.milestone
        perm.require(perm.can_tick_milestone(task, user, ms), user, 'milestone.done', task,
                     f"Your role on this task cannot complete the milestone '{ms.name}'.")
        if task.status in (S.COMPLETED, S.DELETED):
            raise DRFValidationError({'milestone': f'Cannot change milestones on a {task.status} task.'})
        if milestone_progress.status == TaskMilestoneProgress.State.DONE:
            raise DRFValidationError({'milestone': f"Milestone '{ms.name}' is already done."})

        if not task.task_type.allow_out_of_order_milestones:
            earlier_pending = task.milestone_progress.filter(
                milestone__sort_order__lt=ms.sort_order, status=TaskMilestoneProgress.State.PENDING
            ).select_related('milestone').first()
            if earlier_pending:
                raise DRFValidationError({'milestone': (
                    f"Cannot complete '{ms.name}' while earlier milestone "
                    f"'{earlier_pending.milestone.name}' is still pending.")})

        milestone_progress.status = TaskMilestoneProgress.State.DONE
        milestone_progress.done_by = user
        milestone_progress.done_at = timezone.now()
        milestone_progress.note = note or ''
        milestone_progress.save()
        task.version += 1
        task.save(update_fields=['version', 'updated_at'])
        log_event('milestone.done', 'Task', task.id, actor_user_id=getattr(user, 'id', None),
                  milestone=ms.name, is_terminal=ms.is_terminal)
        notify(Notification.Kind.MILESTONE_DONE, [task.assigned_user, task.leader_user],
               f'{uname(user)} completed "{ms.name}" on {task.task_number}', body=task.title, task=task, actor=user)

        task = cls._auto_start(task, user, 'First milestone completed')

        auto_labels = ms.auto_resolve_issue_labels or []
        if auto_labels:
            for iss in task.issues.filter(status=TaskIssue.Status.OPEN, label__name__in=auto_labels).select_related('label'):
                iss.status = TaskIssue.Status.RESOLVED
                iss.resolved_by = user
                iss.resolved_at = timezone.now()
                iss.resolution_note = f"Auto-resolved at milestone {ms.name}"
                iss.save()
                log_event('issue.auto_resolve', 'TaskIssue', iss.id, actor_user_id=getattr(user, 'id', None),
                          task_id=task.id, label=iss.label.name, milestone=ms.name)

        if ms.is_terminal:
            try:
                cls.update_status(task, S.COMPLETED, changed_by=user,
                                  reason=f'Terminal milestone {ms.name} reached')
            except (DRFValidationError, PermissionDenied) as exc:
                # Keep the task in process; the UI shows what is still open.
                log_event('task.auto_complete_skipped', 'Task', task.id, actor_user_id=getattr(user, 'id', None),
                          reason=str(getattr(exc, 'detail', exc)))
        return milestone_progress

    # ------------------------------------------------------------------ to-dos
    @classmethod
    @transaction.atomic
    def toggle_todo(cls, task: Task, todo: TaskTodo, user, request=None) -> TaskTodo:
        task = cls._lock(task)
        perm.require(perm.can_work(task, user), user, 'todo.toggle', task,
                     'Only people with a role on this task can change its to-dos.')
        if task.status in (S.COMPLETED, S.DELETED):
            raise DRFValidationError({'todo': f'Cannot change to-dos on a {task.status} task. Reopen it first.'})
        todo.is_done = not todo.is_done
        todo.done_by = user if todo.is_done else None
        todo.done_at = timezone.now() if todo.is_done else None
        todo.save()
        task.version += 1
        task.save(update_fields=['version', 'updated_at'])
        log_event('todo.done' if todo.is_done else 'todo.undone', 'Task', task.id,
                  actor_user_id=getattr(user, 'id', None), todo_id=todo.id, mandatory=todo.is_mandatory)
        if todo.is_done:
            cls._auto_start(task, user, 'First to-do completed')
        return todo

    # ------------------------------------------------------------------ issues
    @classmethod
    @transaction.atomic
    def raise_issue(cls, task: Task, user, label_id, detail='', due_date=None, request=None) -> TaskIssue:
        task = cls._lock(task)
        perm.require(perm.can_work(task, user), user, 'issue.raise', task,
                     'Only people with a role on this task can raise issues.')
        cls._require_not_deleted(task, 'raise an issue')
        if not label_id:
            raise DRFValidationError({'label_id': 'Select an issue label.'})
        label = PendingIssueLabel.objects.filter(id=label_id, firm_id=task.firm_id, is_active=True).first() \
            if _is_uuid(label_id) else None
        if label is None:
            raise DRFValidationError({'label_id': 'Unknown or inactive issue label.'})
        issue = TaskIssue.objects.create(task=task, label=label, detail=detail or '',
                                         due_date=due_date or None, raised_by=user)
        AuditLog.log(firm_id=task.firm_id, action='issue.raise', entity_type='Task', entity_id=str(task.id),
                     actor_user_id=getattr(user, 'id', None), new_value={'label': label.name}, request=request)
        log_event('issue.raise', 'TaskIssue', issue.id, actor_user_id=getattr(user, 'id', None),
                  task_id=task.id, label=label.name, client_side=label.is_client_side,
                  blocks_completion=label.blocks_completion)
        notify(Notification.Kind.ISSUE_RAISED, [task.assigned_user, task.leader_user, task.manager_user],
               f'Issue on {task.task_number}: {label.name}', body=detail or task.title, task=task, actor=user)
        return issue

    @classmethod
    @transaction.atomic
    def resolve_issue(cls, task: Task, issue: TaskIssue, user, note='', request=None) -> TaskIssue:
        task = cls._lock(task)
        perm.require(perm.can_work(task, user), user, 'issue.resolve', task,
                     'Only people with a role on this task can resolve issues.')
        if issue.status != TaskIssue.Status.OPEN:
            raise DRFValidationError({'issue_id': f'Issue is already {issue.status}.'})
        issue.status = TaskIssue.Status.RESOLVED
        issue.resolved_by = user
        issue.resolved_at = timezone.now()
        issue.resolution_note = note or ''
        issue.save()
        AuditLog.log(firm_id=task.firm_id, action='issue.resolve', entity_type='Task', entity_id=str(task.id),
                     actor_user_id=getattr(user, 'id', None), new_value={'label': issue.label.name}, request=request)
        log_event('issue.resolve', 'TaskIssue', issue.id, actor_user_id=getattr(user, 'id', None),
                  task_id=task.id, label=issue.label.name)
        notify(Notification.Kind.ISSUE_RESOLVED, [issue.raised_by, task.assigned_user],
               f'Issue resolved on {task.task_number}: {issue.label.name}', body=note or task.title, task=task, actor=user)
        return issue

    # ------------------------------------------------------------------ comments
    @classmethod
    @transaction.atomic
    def add_comment(cls, task: Task, user, body: str, mentions: list = None,
                    is_internal: bool = True, request=None) -> TaskComment:
        """
        §5.7 M1 (firm decision): a mentioned active staff member is added as a
        task member (gets access) and is notified.
        """
        task = cls._lock(task)
        perm.require(perm.can_work(task, user), user, 'comment.add', task,
                     'Only people with a role on this task can comment.')
        cls._require_not_deleted(task, 'comment')
        body = (body or '').strip()
        if not body:
            raise DRFValidationError({'body': 'Comment body cannot be empty.'})
        if len(body) > 10000:
            raise DRFValidationError({'body': 'Comment is too long (max 10000 characters).'})

        resolved_ids = {str(m) for m in (mentions or []) if _is_uuid(m)}
        raw_tokens = re.findall(r'@([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+|[a-zA-Z0-9_]+(?:\s+[a-zA-Z0-9_]+)?)', body)
        for token in raw_tokens:
            token = token.strip()
            u = (User.objects.filter(firm=task.firm, is_active=True, email__iexact=token).first()
                 or User.objects.filter(firm=task.firm, is_active=True, full_name__iexact=token).first())
            if u:
                resolved_ids.add(str(u.id))

        valid_mentions = list(User.objects.filter(id__in=resolved_ids, firm=task.firm, is_active=True))
        if len(valid_mentions) != len(resolved_ids):
            log_event('comment.mention_ignored', 'Task', task.id, actor_user_id=getattr(user, 'id', None),
                      requested=len(resolved_ids), valid=len(valid_mentions))

        comment = TaskComment.objects.create(task=task, user=user, body=body,
                                             mentions=[str(u.id) for u in valid_mentions],
                                             is_internal=bool(is_internal))

        if user is not None and task.assigned_user_id == user.id:
            task = cls._auto_start(task, user, 'Comment posted by assigned user')

        for m_user in valid_mentions:
            if m_user.id not in (task.assigned_user_id, task.leader_user_id, task.manager_user_id):
                member, created = TaskMember.objects.get_or_create(task=task, user=m_user,
                                                                   defaults={'added_by': user})
                if not created and member.removed_at is not None:
                    member.removed_at = None
                    member.save(update_fields=['removed_at', 'updated_at'])
                    created = True
                if created:
                    TaskAssignmentLog.objects.create(task=task, field=TaskAssignmentLog.Field.MEMBER_ADDED,
                                                     new_user=m_user, changed_by=user,
                                                     reason="Auto-added via @mention in comment",
                                                     trigger=TaskAssignmentLog.Trigger.MENTION)
                    log_event('task.assign_change', 'Task', task.id, actor_user_id=getattr(user, 'id', None),
                              field='member_added', new=m_user.id, trigger='mention')
            notify(Notification.Kind.MENTIONED, [m_user], f"{uname(user)} mentioned you on {task.task_number}",
                   body=body[:500], task=task, actor=user)
        # Everyone else with a role on the task (mentioned people already got 'mentioned')
        mentioned_ids = {u.id for u in valid_mentions}
        notify(Notification.Kind.COMMENT_POSTED, [u for u in roles_of(task) if u and u.id not in mentioned_ids],
               f'{uname(user)} commented on {task.task_number}', body=body[:500], task=task, actor=user)
        log_event('comment.add', 'Task', task.id, actor_user_id=getattr(user, 'id', None),
                  comment_id=comment.id, mentions=len(valid_mentions), length=len(body))
        return comment

    # ------------------------------------------------------------------ time
    @classmethod
    @transaction.atomic
    def log_time(cls, task: Task, user, work_date: date, minutes: int,
                 is_billable: bool = True, note: str = '', request=None) -> TaskTimeLog:
        """§3.2 / §5.9 time logs."""
        task = cls._lock(task)
        perm.require(perm.can_work(task, user), user, 'time.log', task,
                     'Only people with a role on this task can log time on it.')
        cls._require_not_deleted(task, 'log time')
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            raise DRFValidationError({'minutes': 'Minutes must be a whole number.'})
        if minutes <= 0 or minutes > 1440:
            raise DRFValidationError({'minutes': 'Minutes worked must be between 1 and 1440 (24 hours).'})
        if not isinstance(work_date, date):
            raise DRFValidationError({'work_date': 'Work date is required (YYYY-MM-DD).'})
        today = firm_today(task.firm)
        if work_date > today:
            raise DRFValidationError({'work_date': 'Cannot log time for a future date.'})
        day_total = TaskTimeLog.objects.filter(user=user, work_date=work_date).aggregate(s=Sum('minutes'))['s'] or 0
        if day_total + minutes > 1440:
            raise DRFValidationError({'minutes': (
                f'You already logged {day_total // 60}h {day_total % 60}m on {work_date}. '
                'A day cannot exceed 24 hours.')})

        time_log = TaskTimeLog.objects.create(task=task, user=user, work_date=work_date, minutes=minutes,
                                              is_billable=bool(is_billable), note=note or '')
        log_event('time.log', 'Task', task.id, actor_user_id=getattr(user, 'id', None),
                  time_log_id=time_log.id, minutes=minutes, work_date=work_date,
                  day_total_minutes=day_total + minutes,
                  over_12h_warning=(day_total + minutes) > 720,
                  on_completed_task=task.status == S.COMPLETED)
        cls._auto_start(task, user, 'Time log added')
        return time_log

    # ------------------------------------------------------------------ bulk due date
    @classmethod
    @transaction.atomic
    def bulk_shift_due_date(cls, firm, user, task_type_id, new_due_date, period_id=None, reason='', request=None):
        """§5.3 DD3: shift the due date of all pending tasks of a type (and period)."""
        reason = (reason or '').strip()
        if len(reason) < 3:
            raise DRFValidationError({'reason': 'A reason (e.g. notification number) is required.'})
        tasks = Task.objects.filter(firm=firm, task_type_id=task_type_id, status__in=PENDING_STATUSES)
        if period_id:
            tasks = tasks.filter(period_id=period_id)
        ids = list(tasks.values_list('id', flat=True))
        count = Task.objects.filter(id__in=ids).update(
            due_date=new_due_date, due_date_source='manual', version=F('version') + 1, updated_at=timezone.now())
        AuditLog.log(firm_id=firm.id, action='task.bulk_shift_due_date', entity_type='TaskType',
                     entity_id=str(task_type_id), actor_user_id=user.id,
                     new_value={'count': count, 'new_due_date': str(new_due_date), 'reason': reason,
                                'period_id': str(period_id) if period_id else None,
                                'task_ids': [str(i) for i in ids]},
                     request=request)
        log_event('task.bulk_shift_due_date', 'TaskType', task_type_id, actor_user_id=user.id,
                  count=count, new_due_date=new_due_date, period_id=period_id, reason=reason)
        return count


def _is_uuid(value):
    import uuid
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


class TaskMemberService:
    """Add / remove task members (spec §2.1). Admin+, or leader / manager of the task."""

    @staticmethod
    @transaction.atomic
    def add_member(task, member_user, actor, request=None):
        task = TaskService._lock(task)
        perm.require(perm.can_reassign(task, actor), actor, 'task.member_add', task,
                     'Only an Admin, or the leader or manager of this task, can add members.')
        if task.status == S.DELETED:
            raise DRFValidationError({'error': 'A deleted task cannot be changed.'})
        TaskService._validate_user(member_user, task.firm, 'user_id')
        if member_user.id in (task.assigned_user_id, task.leader_user_id, task.manager_user_id):
            raise DRFValidationError({'user_id': 'This person already has a role on the task.'})
        member, created = TaskMember.objects.get_or_create(task=task, user=member_user, defaults={'added_by': actor})
        if not created:
            if member.removed_at is None:
                raise DRFValidationError({'user_id': 'This person is already a member.'})
            member.removed_at = None
            member.added_by = actor
            member.save(update_fields=['removed_at', 'added_by', 'updated_at'])
        TaskAssignmentLog.objects.create(task=task, field=TaskAssignmentLog.Field.MEMBER_ADDED, new_user=member_user,
                                         changed_by=actor, trigger=TaskAssignmentLog.Trigger.MANUAL)
        AuditLog.log(firm_id=task.firm_id, action='task.member_add', entity_type='Task', entity_id=str(task.id),
                     actor_user_id=actor.id, new_value={'user': member_user.full_name}, request=request)
        log_event('task.assign_change', 'Task', task.id, actor_user_id=actor.id, field='member_added', new=member_user.id)
        notify(Notification.Kind.ROLE_GRANTED, [member_user], f'You were added as a member on {task.task_number}',
               body=task.title, task=task, actor=actor)
        return task

    @staticmethod
    @transaction.atomic
    def remove_member(task, member_user, actor, request=None):
        task = TaskService._lock(task)
        perm.require(perm.can_reassign(task, actor), actor, 'task.member_remove', task,
                     'Only an Admin, or the leader or manager of this task, can remove members.')
        member = TaskMember.objects.filter(task=task, user=member_user, removed_at__isnull=True).first()
        if member is None:
            raise DRFValidationError({'user_id': 'This person is not a member of the task.'})
        member.removed_at = timezone.now()
        member.save(update_fields=['removed_at', 'updated_at'])
        TaskAssignmentLog.objects.create(task=task, field=TaskAssignmentLog.Field.MEMBER_REMOVED, old_user=member_user,
                                         changed_by=actor, trigger=TaskAssignmentLog.Trigger.MANUAL)
        AuditLog.log(firm_id=task.firm_id, action='task.member_remove', entity_type='Task', entity_id=str(task.id),
                     actor_user_id=actor.id, old_value={'user': member_user.full_name}, request=request)
        log_event('task.assign_change', 'Task', task.id, actor_user_id=actor.id, field='member_removed', old=member_user.id)
        return task
