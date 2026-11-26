from rest_framework import serializers
from .models import Notification, NotificationPreference

class NotificationSerializer(serializers.ModelSerializer):
    task_number = serializers.CharField(source='task.task_number', read_only=True, default='')
    # False when the reader no longer has access to the task (re-assigned away, removed, deleted).
    # The UI then shows the message without opening the task (which would give 404).
    can_open = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ['id', 'kind', 'task', 'task_number', 'title', 'body', 'link', 'can_open', 'is_read', 'read_at', 'created_at']
        read_only_fields = ['id', 'kind', 'task', 'title', 'body', 'link', 'created_at']

    def get_can_open(self, obj):
        if obj.task_id is None:
            return bool(obj.link)
        from apps.tasks.permissions import can_view
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return bool(user and user.is_authenticated and can_view(obj.task, user))


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ['email_enabled', 'in_app_enabled', 'digest_enabled']
