from rest_framework import serializers
from .models import BulkBatch, BulkBatchRun, BulkBatchRunItem

class BulkBatchRunItemSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    task_number = serializers.CharField(source='task.task_number', read_only=True, default='')

    class Meta:
        model = BulkBatchRunItem
        fields = ['id', 'client', 'client_name', 'task', 'task_number', 'outcome', 'message']


class BulkBatchRunSerializer(serializers.ModelSerializer):
    items = BulkBatchRunItemSerializer(many=True, read_only=True)
    batch_name = serializers.CharField(source='batch.name', read_only=True)
    period_label = serializers.CharField(source='period.label', read_only=True)

    class Meta:
        model = BulkBatchRun
        fields = ['id', 'batch', 'batch_name', 'fy', 'period', 'period_label', 'run_at', 'status', 'created_count', 'skipped_count', 'error_count', 'items']


class BulkBatchRunLiteSerializer(serializers.ModelSerializer):
    period_label = serializers.CharField(source='period.label', read_only=True)
    run_by_name = serializers.CharField(source='run_by.full_name', read_only=True, default='System')

    class Meta:
        model = BulkBatchRun
        fields = ['id', 'period', 'period_label', 'run_at', 'run_by_name', 'status', 'created_count', 'skipped_count', 'error_count']


class BulkBatchSerializer(serializers.ModelSerializer):
    task_type_name = serializers.CharField(source='task_type.name', read_only=True)
    period_kind = serializers.CharField(source='task_type.period_kind', read_only=True)
    last_runs = serializers.SerializerMethodField()
    next_run_date = serializers.SerializerMethodField()

    class Meta:
        model = BulkBatch
        fields = [
            'id', 'name', 'task_type', 'task_type_name', 'period_kind', 'client_selection',
            'default_assigned_user', 'default_leader_user', 'default_manager_user',
            'schedule', 'is_active', 'last_runs', 'next_run_date', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_last_runs(self, obj):
        runs = obj.runs.exclude(status='preview').select_related('period', 'run_by').order_by('-run_at')[:5]
        return BulkBatchRunLiteSerializer(runs, many=True).data

    def get_next_run_date(self, obj):
        import calendar
        from datetime import date
        from apps.common.dates import firm_today
        sch = obj.schedule or {}
        dom = sch.get('day_of_month')
        if not obj.is_active or not dom:
            return None
        months = sch.get('months') or list(range(1, 13))
        today = firm_today(obj.firm)
        for add in range(0, 13):
            idx = today.month - 1 + add
            y, m = today.year + idx // 12, idx % 12 + 1
            if m in months:
                d = date(y, m, min(int(dom), calendar.monthrange(y, m)[1]))
                if d >= today:
                    return d
        return None

    def validate_client_selection(self, value):
        import uuid
        from apps.clients.models import Client, ClientGroup
        value = (value or 'all').strip()
        firm = self._firm()
        if value == 'all':
            return value
        try:
            if value.startswith('group:'):
                gid = uuid.UUID(value[6:])
                if firm and not ClientGroup.objects.filter(id=gid, firm=firm).exists():
                    raise serializers.ValidationError('Client group not found.')
                return f'group:{gid}'
            if value.startswith('list:'):
                ids = [uuid.UUID(x) for x in value[5:].strip('[] ').split(',') if x.strip()]
                if not ids:
                    raise serializers.ValidationError('Choose at least one client.')
                if firm and Client.objects.filter(id__in=ids, firm=firm).count() != len(set(ids)):
                    raise serializers.ValidationError('Some chosen clients were not found.')
                return 'list:[' + ','.join(str(i) for i in ids) + ']'
        except ValueError:
            raise serializers.ValidationError('Invalid client id in the selection.')
        raise serializers.ValidationError('Use "all", "group:<id>" or "list:[id,id]".')

    def _firm(self):
        request = self.context.get('request')
        return request.user.firm if request else None

    def validate_task_type(self, value):
        firm = self._firm()
        if firm and value.service.category.firm_id != firm.id:
            raise serializers.ValidationError('Task type does not belong to this firm.')
        if not value.is_active:
            raise serializers.ValidationError('Task type is inactive.')
        return value

    def validate_schedule(self, value):
        """
        {day_of_month: 1-28 (empty = manual only), months: [1..12] optional,
         period_offset: -1 (previous period, default) or 0 (current period)}
        """
        value = dict(value or {})
        dom = value.get('day_of_month')
        if dom not in (None, ''):
            try:
                dom = int(dom)
            except (TypeError, ValueError):
                raise serializers.ValidationError('day_of_month must be a number 1-28.')
            if not 1 <= dom <= 28:
                raise serializers.ValidationError('day_of_month must be 1-28 so it runs every month.')
            value['day_of_month'] = dom
        months = value.get('months') or []
        if any((not str(m).isdigit()) or not 1 <= int(m) <= 12 for m in months):
            raise serializers.ValidationError('months must be numbers 1-12.')
        value['months'] = [int(m) for m in months]
        offset = value.get('period_offset', -1)
        if str(offset) not in ('-1', '0'):
            raise serializers.ValidationError('period_offset must be -1 (previous period) or 0 (current period).')
        value['period_offset'] = int(offset)
        return value

    def validate(self, attrs):
        firm = self._firm()
        for key in ('default_assigned_user', 'default_leader_user', 'default_manager_user'):
            user = attrs.get(key)
            if user is not None and firm and (user.firm_id != firm.id or not user.is_active):
                raise serializers.ValidationError({key: 'User must be an active member of this firm.'})
        return attrs
