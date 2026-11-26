import uuid
from django.db import models
from django.utils import timezone
from apps.common.models import BaseModel
from apps.accounts.models import Firm, User
from apps.tasks.models import Task

class Notification(BaseModel):
    class Kind(models.TextChoices):
        TASK_ASSIGNED = 'task_assigned', 'Task Assigned'
        TASK_REASSIGNED = 'task_reassigned', 'Task Reassigned'
        ROLE_GRANTED = 'role_granted', 'Role Granted'
        COMMENT_POSTED = 'comment_posted', 'Comment Posted'
        MENTIONED = 'mentioned', 'Mentioned'
        ISSUE_RAISED = 'issue_raised', 'Issue Raised'
        ISSUE_RESOLVED = 'issue_resolved', 'Issue Resolved'
        DUE_TODAY = 'due_today', 'Due Today'
        OVERDUE = 'overdue', 'Overdue'
        MILESTONE_DONE = 'milestone_done', 'Milestone Done'
        TASK_COMPLETED = 'task_completed', 'Task Completed'
        TASK_DELETED = 'task_deleted', 'Task Deleted'
        BULK_RUN = 'bulk_run', 'Bulk Run'

    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='notifications')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=30, choices=Kind.choices, db_index=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default='')
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    channels_sent = models.JSONField(default=dict, blank=True) # {'in_app': True, 'email': True}
    # Optional in-app link when there is no single task (e.g. daily "3 tasks due today" summary)
    link = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"[{self.kind}] to {self.user.full_name}: {self.title}"


class NotificationPreference(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_preference')
    email_enabled = models.BooleanField(default=True)
    in_app_enabled = models.BooleanField(default=True)
    digest_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"Prefs for {self.user.full_name}"
