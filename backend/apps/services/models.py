import uuid
from django.db import models
from apps.common.models import BaseModel
from apps.accounts.models import Firm

class ServiceCategory(BaseModel):
    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='service_categories')
    name = models.CharField(max_length=150)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'service categories'
        ordering = ['sort_order', 'name']
        unique_together = ('firm', 'name')

    def __str__(self):
        return self.name


class Service(BaseModel):
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=150)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']
        unique_together = ('category', 'name')

    def __str__(self):
        return f"{self.category.name} → {self.name}"


class TaskType(BaseModel):
    class Recurrence(models.TextChoices):
        NONE = 'none', 'One-off / None'
        MONTHLY = 'monthly', 'Monthly'
        QUARTERLY = 'quarterly', 'Quarterly'
        HALF_YEARLY = 'half_yearly', 'Half Yearly'
        YEARLY = 'yearly', 'Yearly'
        CUSTOM = 'custom', 'Custom'

    class Priority(models.TextChoices):
        NORMAL = 'normal', 'Normal'
        HIGH = 'high', 'High'

    class PeriodKind(models.TextChoices):
        NONE = 'none', 'None'
        MONTH = 'month', 'Month'
        QUARTER = 'quarter', 'Quarter'
        HALF = 'half', 'Half Year'
        YEAR = 'year', 'Year'

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='task_types')
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, blank=True, default='')
    default_due_rule = models.JSONField(default=dict, blank=True)
    recurrence = models.CharField(max_length=20, choices=Recurrence.choices, default=Recurrence.NONE)
    default_priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    requires_fy = models.BooleanField(default=True)
    requires_period = models.BooleanField(default=True)
    period_kind = models.CharField(max_length=10, choices=PeriodKind.choices, default=PeriodKind.MONTH)
    is_billable_default = models.BooleanField(default=True)
    uses_assessment_year = models.BooleanField(default=False)
    allow_out_of_order_milestones = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('service', 'name')

    def __str__(self):
        return f"{self.service.name} → {self.name}"


class TaskTypeTodoTemplate(BaseModel):
    task_type = models.ForeignKey(TaskType, on_delete=models.CASCADE, related_name='todo_templates')
    text = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)
    is_mandatory = models.BooleanField(default=False)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"[{self.task_type.name}] {self.text}"


class Milestone(BaseModel):
    task_type = models.ForeignKey(TaskType, on_delete=models.CASCADE, related_name='milestones')
    name = models.CharField(max_length=150)
    sort_order = models.PositiveIntegerField(default=0)
    is_terminal = models.BooleanField(default=False) # Completing this milestone marks task as Completed
    can_be_completed_by = models.JSONField(default=list, blank=True) # ['assigned', 'leader', 'manager']
    auto_resolve_issue_labels = models.JSONField(default=list, blank=True) # labels auto-resolved at this stage

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"[{self.task_type.name}] Step {self.sort_order}: {self.name}"


class PendingIssueLabel(BaseModel):
    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='issue_labels')
    name = models.CharField(max_length=100)
    is_client_side = models.BooleanField(default=False) # True = Waiting on Client
    blocks_completion = models.BooleanField(default=True) # Prevents task completion while open
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('firm', 'name')

    def __str__(self):
        return f"{self.name} ({'Client' if self.is_client_side else 'Internal'})"


class ComplianceEvent(BaseModel):
    """
    One row of the dashboard "Statutory Compliance Calendar".
    Admins manage the list on the Settings page (add / edit / remove / enable / disable).
    The due date repeats every year on due_day of each month in due_months
    (empty list = every month). A day past the month end uses the last day (31 -> 30 Jun).
    """
    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='compliance_events')
    code = models.CharField(max_length=30)
    title = models.CharField(max_length=150)
    scope = models.CharField(max_length=150, blank=True, default='')
    description = models.CharField(max_length=255, blank=True, default='')
    due_day = models.PositiveSmallIntegerField()                 # 1-31
    due_months = models.JSONField(default=list, blank=True)      # [] = every month, else [1..12]
    warn_days = models.PositiveSmallIntegerField(default=2)      # orange this many days before; red on the day
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'title']
        unique_together = ('firm', 'code')

    def __str__(self):
        return f"{self.code} - {self.title}"
