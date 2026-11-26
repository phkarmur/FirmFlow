import uuid
from django.db import models, transaction
from django.utils import timezone
from apps.common.models import BaseModel
from apps.common.storage import private_storage
from apps.accounts.models import Firm, Branch, User
from apps.clients.models import Client
from apps.services.models import TaskType, Milestone, PendingIssueLabel
from apps.periods.models import FinancialYear, Period

class TaskSequence(models.Model):
    """
    Per-firm and per-FY atomic counter for generating human-readable task numbers:
    FF-YYYY-000123.
    """
    firm = models.ForeignKey(Firm, on_delete=models.CASCADE)
    year = models.IntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('firm', 'year')

    @classmethod
    def get_next_number(cls, firm, year: int) -> str:
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(firm=firm, year=year)
            seq.last_number += 1
            seq.save(update_fields=['last_number'])
            return f"FF-{year}-{seq.last_number:06d}"


class Task(BaseModel):
    class Status(models.TextChoices):
        NOT_STARTED = 'not_started', 'Not Started'
        IN_PROCESS = 'in_process', 'In Process'
        ON_HOLD = 'on_hold', 'On Hold'
        COMPLETED = 'completed', 'Completed'
        DELETED = 'deleted', 'Deleted'

    class Priority(models.TextChoices):
        NORMAL = 'normal', 'Normal'
        HIGH = 'high', 'High'

    class BillingState(models.TextChoices):
        UNBILLED = 'unbilled', 'Unbilled'
        BILLED = 'billed', 'Billed'
        FREE = 'free', 'Free'

    class Source(models.TextChoices):
        MANUAL = 'manual', 'Manual'
        BULK = 'bulk', 'Bulk'
        RECURRING = 'recurring', 'Recurring'
        IMPORT = 'import', 'Import'
        CLIENT_PORTAL = 'client_portal', 'Client Portal'

    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='tasks')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='tasks')
    task_number = models.CharField(max_length=50, unique=True, editable=False, db_index=True)

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='tasks')
    task_type = models.ForeignKey(TaskType, on_delete=models.PROTECT, related_name='tasks')
    task_type_name_snapshot = models.CharField(max_length=150)

    fy = models.ForeignKey(FinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name='tasks')
    period = models.ForeignKey(Period, on_delete=models.PROTECT, null=True, blank=True, related_name='tasks')

    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, default='')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED, db_index=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL, db_index=True)

    due_date = models.DateField(db_index=True)
    due_date_source = models.CharField(max_length=20, default='rule') # 'rule' | 'manual'
    start_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks_completed')

    # Roles on the task
    assigned_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tasks')
    leader_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='lead_tasks')
    manager_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_tasks')

    billing_state = models.CharField(max_length=20, choices=BillingState.choices, default=BillingState.UNBILLED)
    on_hold_reason = models.TextField(blank=True, default='')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tasks_created')
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks_deleted')
    delete_reason = models.TextField(blank=True, default='')

    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    bulk_batch_run_id = models.UUIDField(null=True, blank=True)
    custom_fields = models.JSONField(default=dict, blank=True)

    version = models.PositiveIntegerField(default=1) # Optimistic locking

    class Meta:
        ordering = ['due_date', '-created_at']
        indexes = [
            models.Index(fields=['firm', 'status', 'due_date']),
            models.Index(fields=['firm', 'assigned_user', 'status']),
            models.Index(fields=['firm', 'client', 'status']),
        ]
        # Prevent accidental duplicate recurring tasks for same client + task type + period
        constraints = [
            models.UniqueConstraint(
                fields=['client', 'task_type', 'fy', 'period'],
                condition=models.Q(period__isnull=False) & ~models.Q(status='deleted'),
                name='unique_client_task_period'
            )
        ]

    def __str__(self):
        return f"[{self.task_number}] {self.title}"


class TaskMember(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_memberships')
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='members_added')
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('task', 'user')

    def __str__(self):
        return f"{self.user.full_name} on {self.task.task_number}"


class TaskMilestoneProgress(BaseModel):
    class State(models.TextChoices):
        PENDING = 'pending', 'Pending'
        DONE = 'done', 'Done'
        SKIPPED = 'skipped', 'Skipped'

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='milestone_progress')
    milestone = models.ForeignKey(Milestone, on_delete=models.PROTECT, related_name='task_progress')
    status = models.CharField(max_length=10, choices=State.choices, default=State.PENDING)
    done_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['milestone__sort_order']
        unique_together = ('task', 'milestone')

    def __str__(self):
        return f"{self.task.task_number} - {self.milestone.name} ({self.status})"


class TaskTodo(BaseModel):
    class Source(models.TextChoices):
        TEMPLATE = 'template', 'Template'
        MANUAL = 'manual', 'Manual'

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='todos')
    text = models.CharField(max_length=255)
    is_done = models.BooleanField(default=False)
    done_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_mandatory = models.BooleanField(default=False)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.TEMPLATE)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"{self.task.task_number}: {self.text} [{'x' if self.is_done else ' '}]"


class TaskIssue(BaseModel):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        RESOLVED = 'resolved', 'Resolved'
        DELETED = 'deleted', 'Deleted'

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='issues')
    label = models.ForeignKey(PendingIssueLabel, on_delete=models.PROTECT, related_name='issues')
    detail = models.TextField(blank=True, default='')
    raised_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='issues_raised')
    raised_at = models.DateTimeField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issues_resolved')
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-raised_at']

    def __str__(self):
        return f"Issue on {self.task.task_number}: {self.label.name} ({self.status})"


class TaskComment(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='comments_posted')
    body = models.TextField()
    mentions = models.JSONField(default=list, blank=True) # list of user IDs
    edited_at = models.DateTimeField(null=True, blank=True)
    is_internal = models.BooleanField(default=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.user.full_name if self.user else 'Unknown'} on {self.task.task_number}"


class TaskAttachment(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    file_name = models.CharField(max_length=255)
    # Private storage, random name (storage_key). Never served as a static file.
    file = models.FileField(upload_to='task_attachments/%Y/%m/', storage=private_storage, max_length=255)
    mime = models.CharField(max_length=100)
    size_bytes = models.BigIntegerField()
    storage_key = models.CharField(max_length=255) # Random UUID key
    sha256 = models.CharField(max_length=64)
    is_client_visible = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.file_name} ({self.task.task_number})"


class TaskTimeLog(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='time_logs')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='time_logs')
    work_date = models.DateField(db_index=True)
    minutes = models.PositiveIntegerField() # > 0 and <= 1440
    is_billable = models.BooleanField(default=True)
    note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-work_date', '-created_at']

    def __str__(self):
        return f"{self.user.full_name}: {self.minutes} mins on {self.work_date}"


class TaskAssignmentLog(BaseModel):
    class Field(models.TextChoices):
        ASSIGNED = 'assigned', 'Assigned User'
        LEADER = 'leader', 'Task Leader'
        MANAGER = 'manager', 'Task Manager'
        MEMBER_ADDED = 'member_added', 'Member Added'
        MEMBER_REMOVED = 'member_removed', 'Member Removed'

    class Trigger(models.TextChoices):
        MANUAL = 'manual', 'Manual'
        RULE = 'rule', 'Rule'
        BULK = 'bulk', 'Bulk'
        SYSTEM = 'system', 'System'
        PICKUP = 'pickup', 'Pickup / Self-Assign'
        MENTION = 'mention', 'Mention'

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='assignment_logs')
    field = models.CharField(max_length=20, choices=Field.choices)
    old_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    new_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    changed_at = models.DateTimeField(default=timezone.now)
    reason = models.TextField(blank=True, default='')
    trigger = models.CharField(max_length=15, choices=Trigger.choices, default=Trigger.MANUAL)

    class Meta:
        ordering = ['-changed_at']


class TaskStatusLog(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='status_logs')
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(default=timezone.now)
    reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-changed_at']


class PersonalTodo(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='personal_todos')
    text = models.CharField(max_length=255)
    is_done = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['is_done', 'due_date', '-created_at']


class StickyNote(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sticky_notes')
    title = models.CharField(max_length=100, blank=True, default='')
    content = models.TextField(blank=True, default='')
    color = models.CharField(max_length=20, default='yellow')

    class Meta:
        ordering = ['-created_at']
