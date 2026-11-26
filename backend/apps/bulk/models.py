import uuid
from django.db import models
from django.utils import timezone
from apps.common.models import BaseModel
from apps.accounts.models import Firm, Branch, User
from apps.clients.models import Client
from apps.services.models import TaskType
from apps.periods.models import FinancialYear, Period
from apps.tasks.models import Task

class BulkBatch(BaseModel):
    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='bulk_batches')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='bulk_batches')
    name = models.CharField(max_length=150)
    task_type = models.ForeignKey(TaskType, on_delete=models.CASCADE, related_name='bulk_batches')
    client_selection = models.CharField(max_length=255, default='all') # 'all', 'group:<id>', 'list:[ids]'
    default_assigned_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    default_leader_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    default_manager_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    schedule = models.JSONField(default=dict, blank=True) # {day_of_month: 1, months: [1,2,...12]}
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.task_type.name})"


class BulkBatchRun(BaseModel):
    class Status(models.TextChoices):
        PREVIEW = 'preview', 'Preview'
        COMMITTED = 'committed', 'Committed'
        FAILED = 'failed', 'Failed'

    batch = models.ForeignKey(BulkBatch, on_delete=models.CASCADE, related_name='runs')
    fy = models.ForeignKey(FinancialYear, on_delete=models.CASCADE)
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    run_at = models.DateTimeField(default=timezone.now)
    run_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PREVIEW)
    created_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-run_at']

    def __str__(self):
        return f"{self.batch.name} - {self.period.label} ({self.status})"


class BulkBatchRunItem(BaseModel):
    class Outcome(models.TextChoices):
        CREATED = 'created', 'Created'
        SKIPPED_DUPLICATE = 'skipped_duplicate', 'Skipped (Duplicate)'
        SKIPPED_INACTIVE = 'skipped_inactive', 'Skipped (Inactive Client)'
        SKIPPED_BLOCKED = 'skipped_blocked', 'Skipped (Blocked Client)'
        ERROR = 'error', 'Error'

    run = models.ForeignKey(BulkBatchRun, on_delete=models.CASCADE, related_name='items')
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    message = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['client__name']

    def __str__(self):
        return f"{self.client.name}: {self.outcome}"
