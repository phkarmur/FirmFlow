from rest_framework import serializers

TASK_ROLES = ('assigned', 'leader', 'manager', 'member')
DUE_RULE_KINDS = ('fixed_day_after_period_end', 'fixed_date', 'per_period_sequence', 'days_after_creation', 'none')


def _firm_of(serializer):
    request = serializer.context.get('request')
    return getattr(getattr(request, 'user', None), 'firm', None)


def _check_firm(serializer, obj_firm_id, field):
    firm = _firm_of(serializer)
    if firm is not None and obj_firm_id != firm.id:
        raise serializers.ValidationError({field: 'Not found in this firm.'})


def validate_due_rule(rule):
    """Check the shape of TaskType.default_due_rule (see tasks/services/due_dates.py)."""
    if rule in (None, {}):
        return {}
    if not isinstance(rule, dict) or rule.get('kind') not in DUE_RULE_KINDS:
        raise serializers.ValidationError(f'kind must be one of: {", ".join(DUE_RULE_KINDS)}.')
    kind = rule['kind']
    try:
        if kind == 'fixed_day_after_period_end':
            day, after = int(rule.get('day', 20)), int(rule.get('months_after', 1))
            if not (1 <= day <= 31 and 0 <= after <= 12):
                raise ValueError
            return {'kind': kind, 'day': day, 'months_after': after}
        if kind == 'fixed_date':
            m, d = int(rule['month']), int(rule['day'])
            if not (1 <= m <= 12 and 1 <= d <= 31):
                raise ValueError
            return {'kind': kind, 'month': m, 'day': d}
        if kind == 'per_period_sequence':
            dates = rule.get('dates') or {}
            clean = {}
            for k, v in dates.items():
                mm, dd = str(v).split('-')
                if not (1 <= int(mm) <= 12 and 1 <= int(dd) <= 31 and 1 <= int(k) <= 12):
                    raise ValueError
                clean[str(int(k))] = f'{int(mm):02d}-{int(dd):02d}'
            if not clean:
                raise ValueError
            return {'kind': kind, 'dates': clean}
        if kind == 'days_after_creation':
            days = int(rule.get('days', 15))
            if not 0 <= days <= 3650:
                raise ValueError
            return {'kind': kind, 'days': days}
        return {'kind': 'none'}
    except (KeyError, ValueError, TypeError, AttributeError):
        raise serializers.ValidationError(f'Values for "{kind}" are not valid. Check day / month numbers.')
from .models import ServiceCategory, Service, TaskType, TaskTypeTodoTemplate, Milestone, PendingIssueLabel, ComplianceEvent

class TaskTypeTodoTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskTypeTodoTemplate
        fields = ['id', 'task_type', 'text', 'sort_order', 'is_mandatory', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_task_type(self, value):
        _check_firm(self, value.service.category.firm_id, 'task_type')
        return value



class MilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milestone
        fields = ['id', 'task_type', 'name', 'sort_order', 'is_terminal', 'can_be_completed_by', 'auto_resolve_issue_labels', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_task_type(self, value):
        _check_firm(self, value.service.category.firm_id, 'task_type')
        return value

    def validate_can_be_completed_by(self, value):
        if not isinstance(value, list) or any(v not in TASK_ROLES for v in value):
            raise serializers.ValidationError(f'Use a list of: {", ".join(TASK_ROLES)} (empty = assigned, leader, manager).')
        return value

    def validate_auto_resolve_issue_labels(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Use a list of issue label names.')
        firm = _firm_of(self)
        if firm is not None and value:
            known = set(PendingIssueLabel.objects.filter(firm=firm).values_list('name', flat=True))
            missing = [v for v in value if v not in known]
            if missing:
                raise serializers.ValidationError(f'Unknown issue labels: {", ".join(missing)}.')
        return value



class TaskTypeSerializer(serializers.ModelSerializer):
    milestones = MilestoneSerializer(many=True, read_only=True)
    todo_templates = TaskTypeTodoTemplateSerializer(many=True, read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)
    category_name = serializers.CharField(source='service.category.name', read_only=True)

    class Meta:
        model = TaskType
        fields = [
            'id', 'service', 'service_name', 'category_name', 'name', 'code',
            'default_due_rule', 'recurrence', 'default_priority',
            'requires_fy', 'requires_period', 'period_kind',
            'is_billable_default', 'uses_assessment_year',
            'allow_out_of_order_milestones', 'is_active',
            'milestones', 'todo_templates', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def validate_service(self, value):
        _check_firm(self, value.category.firm_id, 'service')
        return value

    def validate_default_due_rule(self, value):
        return validate_due_rule(value)

    def validate(self, attrs):
        kind = attrs.get('period_kind', getattr(self.instance, 'period_kind', 'month'))
        if kind == 'none':
            attrs['requires_period'] = False
        return attrs



class ServiceSerializer(serializers.ModelSerializer):
    task_types = TaskTypeSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Service
        fields = ['id', 'category', 'category_name', 'name', 'sort_order', 'is_active', 'task_types', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_category(self, value):
        _check_firm(self, value.firm_id, 'category')
        return value



class ServiceCategorySerializer(serializers.ModelSerializer):
    services = ServiceSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceCategory
        fields = ['id', 'name', 'sort_order', 'is_active', 'services', 'created_at']
        read_only_fields = ['id', 'created_at']


class PendingIssueLabelSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingIssueLabel
        fields = ['id', 'name', 'is_client_side', 'blocks_completion', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class ComplianceEventSerializer(serializers.ModelSerializer):
    """Dashboard compliance calendar row. Computed fields use the firm's 'today'."""
    due_text = serializers.SerializerMethodField()
    next_due_date = serializers.SerializerMethodField()
    days_left = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()

    class Meta:
        model = ComplianceEvent
        fields = ['id', 'code', 'title', 'scope', 'description', 'due_day', 'due_months', 'warn_days',
                  'is_active', 'sort_order', 'due_text', 'next_due_date', 'days_left', 'state']
        read_only_fields = ['id', 'due_text', 'next_due_date', 'days_left', 'state']

    def _calc(self, obj):
        from .compliance import next_due_date, due_state
        cache = self.context.setdefault('_calc', {})
        if obj.pk not in cache:
            today = self.context.get('today')
            if today is None:
                from apps.common.dates import firm_today
                today = firm_today(obj.firm)
            due = next_due_date(obj.due_day, obj.due_months, today)
            state, days_left = due_state(due, today, obj.warn_days)
            cache[obj.pk] = (due, state, days_left)
        return cache[obj.pk]

    def get_due_text(self, obj):
        from .compliance import due_text
        return due_text(obj.due_day, obj.due_months)

    def get_next_due_date(self, obj):
        return self._calc(obj)[0]

    def get_state(self, obj):
        return self._calc(obj)[1]

    def get_days_left(self, obj):
        return self._calc(obj)[2]

    def validate_code(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError('Code is required.')
        request = self.context.get('request')
        qs = ComplianceEvent.objects.filter(firm=request.user.firm, code__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Another calendar item already uses this code.')
        return value

    def validate_due_day(self, value):
        if not 1 <= value <= 31:
            raise serializers.ValidationError('Due day must be 1 to 31.')
        return value

    def validate_due_months(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Months must be a list, e.g. [3, 6, 9, 12]. Empty = every month.')
        try:
            months = sorted(set(int(m) for m in value))
        except (TypeError, ValueError):
            raise serializers.ValidationError('Months must be numbers 1 to 12.')
        if any(m < 1 or m > 12 for m in months):
            raise serializers.ValidationError('Months must be numbers 1 to 12.')
        return [] if len(months) == 12 else months

    def validate_warn_days(self, value):
        if value > 15:
            raise serializers.ValidationError('Warning days must be 0 to 15.')
        return value
