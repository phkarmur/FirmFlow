from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from .models import (
    Task, TaskMember, TaskMilestoneProgress, TaskTodo,
    TaskIssue, TaskComment, TaskAttachment, TaskTimeLog,
    TaskAssignmentLog, TaskStatusLog, PersonalTodo, StickyNote
)
from apps.services.serializers import MilestoneSerializer, PendingIssueLabelSerializer
from apps.accounts.serializers import UserSerializer
from apps.periods.models import FinancialYear, Period
from apps.accounts.models import User, Branch
from apps.common.dates import firm_today
from apps.tasks.permissions import permissions_for

class TaskMilestoneProgressSerializer(serializers.ModelSerializer):
    milestone_name = serializers.CharField(source='milestone.name', read_only=True)
    milestone_sort_order = serializers.IntegerField(source='milestone.sort_order', read_only=True)
    is_terminal = serializers.BooleanField(source='milestone.is_terminal', read_only=True)
    done_by_name = serializers.CharField(source='done_by.full_name', read_only=True, default='')

    class Meta:
        model = TaskMilestoneProgress
        fields = [
            'id', 'milestone', 'milestone_name', 'milestone_sort_order',
            'is_terminal', 'status', 'done_by', 'done_by_name',
            'done_at', 'note'
        ]
        read_only_fields = ['id', 'milestone', 'done_by', 'done_at']


class TaskTodoSerializer(serializers.ModelSerializer):
    done_by_name = serializers.CharField(source='done_by.full_name', read_only=True, default='')

    class Meta:
        model = TaskTodo
        fields = ['id', 'task', 'text', 'is_done', 'done_by', 'done_by_name', 'done_at', 'sort_order', 'is_mandatory', 'source']
        read_only_fields = ['id', 'task', 'done_by', 'done_at']


class TaskIssueSerializer(serializers.ModelSerializer):
    label_name = serializers.CharField(source='label.name', read_only=True)
    is_client_side = serializers.BooleanField(source='label.is_client_side', read_only=True)
    blocks_completion = serializers.BooleanField(source='label.blocks_completion', read_only=True)
    raised_by_name = serializers.CharField(source='raised_by.full_name', read_only=True, default='')
    resolved_by_name = serializers.CharField(source='resolved_by.full_name', read_only=True, default='')

    class Meta:
        model = TaskIssue
        fields = [
            'id', 'task', 'label', 'label_name', 'is_client_side', 'blocks_completion',
            'detail', 'raised_by', 'raised_by_name', 'raised_at',
            'due_date', 'status', 'resolved_by', 'resolved_by_name',
            'resolved_at', 'resolution_note'
        ]
        read_only_fields = ['id', 'task', 'raised_by', 'raised_at', 'resolved_by', 'resolved_at']


class TaskCommentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True, default='')

    class Meta:
        model = TaskComment
        fields = ['id', 'task', 'user', 'user_name', 'body', 'mentions', 'created_at', 'edited_at', 'is_internal']
        read_only_fields = ['id', 'task', 'user', 'created_at', 'edited_at']


class TaskAttachmentSerializer(serializers.ModelSerializer):
    """No file URL: downloads go through the authenticated endpoint only (spec §5.8 F2)."""
    uploaded_by_name = serializers.CharField(source='uploaded_by.full_name', read_only=True, default='')
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = TaskAttachment
        fields = [
            'id', 'task', 'uploaded_by', 'uploaded_by_name',
            'file_name', 'mime', 'size_bytes', 'sha256',
            'is_client_visible', 'created_at', 'download_url'
        ]
        read_only_fields = fields

    def get_download_url(self, obj):
        return f'/api/v1/tasks/{obj.task_id}/attachments/{obj.id}/download/'


class TaskTimeLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True, default='')
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = TaskTimeLog
        fields = ['id', 'task', 'user', 'user_name', 'work_date', 'minutes', 'is_billable', 'note', 'created_at', 'can_edit']
        read_only_fields = ['id', 'task', 'user', 'created_at']

    def validate_minutes(self, value):
        if value is None or value <= 0 or value > 1440:
            raise serializers.ValidationError('Minutes worked must be between 1 and 1440 (24 hours).')
        return value

    def validate_work_date(self, value):
        request = self.context.get('request')
        firm = getattr(getattr(request, 'user', None), 'firm', None)
        if value and value > firm_today(firm):
            raise serializers.ValidationError('Cannot log time for a future date.')
        return value

    def get_can_edit(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        if request.user.is_admin or request.user.is_superuser:
            return True
        # Creator can edit within 24 hours (§3.2: 1 day window)
        if obj.user_id == request.user.id:
            return (timezone.now() - obj.created_at) < timedelta(days=1)
        return False


class TaskAssignmentLogSerializer(serializers.ModelSerializer):
    old_user_name = serializers.CharField(source='old_user.full_name', read_only=True, default='Unassigned')
    new_user_name = serializers.CharField(source='new_user.full_name', read_only=True, default='Unassigned')
    changed_by_name = serializers.CharField(source='changed_by.full_name', read_only=True, default='System')

    class Meta:
        model = TaskAssignmentLog
        fields = ['id', 'field', 'old_user_name', 'new_user_name', 'changed_by_name', 'changed_at', 'reason', 'trigger']


class TaskStatusLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source='changed_by.full_name', read_only=True, default='System')

    class Meta:
        model = TaskStatusLog
        fields = ['id', 'old_status', 'new_status', 'changed_by_name', 'changed_at', 'reason']


class TaskListSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    client_pan = serializers.CharField(source='client.pan_masked', read_only=True)
    task_type_name = serializers.CharField(source='task_type_name_snapshot', read_only=True)
    period_label = serializers.CharField(source='period.label', read_only=True, default='')
    fy_label = serializers.CharField(source='fy.label', read_only=True, default='')
    assigned_user_name = serializers.CharField(source='assigned_user.full_name', read_only=True, default='Unassigned')
    leader_user_name = serializers.CharField(source='leader_user.full_name', read_only=True, default='')
    manager_user_name = serializers.CharField(source='manager_user.full_name', read_only=True, default='')

    # Derived flags (§4.1). Blocked flags come from queryset annotations
    # (selectors.annotate_flags) so the list does not run 2 queries per row.
    is_overdue = serializers.SerializerMethodField()
    is_due_today = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()
    is_waiting_on_client = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'task_number', 'client', 'client_name', 'client_pan',
            'task_type', 'task_type_name', 'fy', 'fy_label', 'period', 'period_label',
            'title', 'status', 'priority', 'due_date',
            'assigned_user', 'assigned_user_name',
            'leader_user', 'leader_user_name',
            'manager_user', 'manager_user_name',
            'billing_state', 'version',
            'is_overdue', 'is_due_today', 'is_blocked', 'is_waiting_on_client',
            'created_at'
        ]
        read_only_fields = fields

    def _today(self, obj):
        cache = self.context.setdefault('_today', {})
        if obj.firm_id not in cache:
            cache[obj.firm_id] = firm_today(obj.firm)
        return cache[obj.firm_id]

    def get_is_overdue(self, obj):
        return obj.status in [Task.Status.NOT_STARTED, Task.Status.IN_PROCESS] and obj.due_date < self._today(obj)

    def get_is_due_today(self, obj):
        return obj.status not in [Task.Status.COMPLETED, Task.Status.DELETED] and obj.due_date == self._today(obj)

    def get_is_blocked(self, obj):
        if hasattr(obj, 'has_open_issue'):
            return obj.has_open_issue
        return obj.issues.filter(status=TaskIssue.Status.OPEN).exists()

    def get_is_waiting_on_client(self, obj):
        if hasattr(obj, 'has_client_issue'):
            return obj.has_client_issue
        return obj.issues.filter(status=TaskIssue.Status.OPEN, label__is_client_side=True).exists()


class TaskDetailSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    client_pan = serializers.CharField(source='client.pan_masked', read_only=True)
    client_gstin = serializers.CharField(source='client.gstin', read_only=True)
    task_type_name = serializers.CharField(source='task_type_name_snapshot', read_only=True)
    period_label = serializers.CharField(source='period.label', read_only=True, default='')
    fy_label = serializers.CharField(source='fy.label', read_only=True, default='')

    assigned_user_name = serializers.CharField(source='assigned_user.full_name', read_only=True, default='Unassigned')
    leader_user_name = serializers.CharField(source='leader_user.full_name', read_only=True, default='')
    manager_user_name = serializers.CharField(source='manager_user.full_name', read_only=True, default='')

    milestones = TaskMilestoneProgressSerializer(source='milestone_progress', many=True, read_only=True)
    todos = TaskTodoSerializer(many=True, read_only=True)
    issues = TaskIssueSerializer(many=True, read_only=True)
    comments = TaskCommentSerializer(many=True, read_only=True)
    attachments = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()
    time_logs = TaskTimeLogSerializer(many=True, read_only=True)
    assignment_logs = TaskAssignmentLogSerializer(many=True, read_only=True)
    status_logs = TaskStatusLogSerializer(many=True, read_only=True)
    my_permissions = serializers.SerializerMethodField()
    uses_assessment_year = serializers.BooleanField(source='task_type.uses_assessment_year', read_only=True)
    ay_label = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'task_number', 'client', 'client_name', 'client_pan', 'client_gstin',
            'task_type', 'task_type_name', 'fy', 'fy_label', 'period', 'period_label',
            'title', 'description', 'status', 'priority', 'due_date', 'due_date_source',
            'start_date', 'completed_at', 'completed_by',
            'assigned_user', 'assigned_user_name',
            'leader_user', 'leader_user_name',
            'manager_user', 'manager_user_name',
            'billing_state', 'on_hold_reason', 'version',
            'milestones', 'todos', 'issues', 'comments', 'attachments',
            'time_logs', 'assignment_logs', 'status_logs',
            'my_permissions', 'uses_assessment_year', 'ay_label', 'members',
            'created_at', 'updated_at'
        ]
        # Fully read-only: every change goes through TaskService (see TaskUpdateSerializer)
        read_only_fields = fields

    def get_attachments(self, obj):
        rows = obj.attachments.filter(deleted_at__isnull=True).select_related('uploaded_by')
        return TaskAttachmentSerializer(rows, many=True).data

    def get_members(self, obj):
        return [{'user': str(m.user_id), 'name': m.user.full_name, 'added_at': m.created_at}
                for m in obj.members.filter(removed_at__isnull=True).select_related('user')]

    def get_my_permissions(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        return permissions_for(obj, request.user)

    def get_ay_label(self, obj):
        if obj.fy and obj.task_type.uses_assessment_year:
            return f"AY {obj.fy.assessment_year_label}"
        return ''


class TaskUpdateSerializer(serializers.Serializer):
    """Only these fields may be edited with PATCH. Status, roles and billing use their own actions."""
    version = serializers.IntegerField(required=True)
    title = serializers.CharField(required=False, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=Task.Priority.choices, required=False)
    due_date = serializers.DateField(required=False)
    start_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        unknown = set(self.initial_data.keys()) - set(self.fields.keys())
        if unknown:
            raise serializers.ValidationError({'unknown_fields': (
                f"These fields cannot be changed here: {', '.join(sorted(unknown))}. "
                'Use the status, re-assign or billing actions.')})
        return attrs


class TaskCreateSerializer(serializers.ModelSerializer):
    fy = serializers.PrimaryKeyRelatedField(queryset=FinancialYear.objects.all(), required=False, allow_null=True, default=None)
    period = serializers.PrimaryKeyRelatedField(queryset=Period.objects.all(), required=False, allow_null=True, default=None)
    assigned_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True, default=None)
    leader_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True, default=None)
    manager_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True, default=None)
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all(), required=False, allow_null=True, default=None)
    due_date = serializers.DateField(required=False, allow_null=True, default=None)

    class Meta:
        model = Task
        fields = [
            'client', 'task_type', 'fy', 'period', 'title', 'description',
            'priority', 'due_date', 'assigned_user', 'leader_user', 'manager_user',
            'branch'
        ]
        extra_kwargs = {
            'title': {'required': False, 'allow_blank': True},
            'description': {'required': False, 'allow_blank': True},
            'priority': {'required': False},
        }


class PersonalTodoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalTodo
        fields = ['id', 'text', 'is_done', 'due_date', 'created_at']
        read_only_fields = ['id', 'created_at']


class StickyNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = StickyNote
        fields = ['id', 'title', 'content', 'color', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
