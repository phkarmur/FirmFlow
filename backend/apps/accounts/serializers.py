from rest_framework import serializers
from .models import User, Firm, Branch, UserBranch

DATE_FORMATS = ('DD-MM-YYYY', 'DD/MM/YYYY', 'YYYY-MM-DD')


class FirmSerializer(serializers.ModelSerializer):
    has_tasks = serializers.SerializerMethodField()
    # Site-relative URL (/media/firm_logos/...) so it works through the dev proxy and Nginx
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Firm
        fields = [
            'id', 'name', 'legal_name', 'logo', 'fy_start_month',
            'timezone', 'date_format', 'long_due_days',
            'staff_can_create_task', 'staff_can_complete', 'allow_pickup', 'max_upload_mb',
            'has_tasks', 'logo_url', 'created_at'
        ]
        read_only_fields = ['id', 'logo', 'has_tasks', 'logo_url', 'created_at']

    def get_logo_url(self, obj):
        return obj.logo.url if obj.logo else None

    def get_has_tasks(self, obj):
        # The UI locks the FY start month once tasks exist (spec FY1)
        return obj.tasks.exists()

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('Firm name is required.')
        return value.strip()

    def validate_long_due_days(self, value):
        if not 1 <= value <= 365:
            raise serializers.ValidationError('Long-due days must be 1 to 365.')
        return value

    def validate_max_upload_mb(self, value):
        if not 1 <= value <= 50:
            raise serializers.ValidationError('Upload limit must be 1 to 50 MB (Nginx allows 50 MB).')
        return value

    def validate_fy_start_month(self, value):
        if not 1 <= value <= 12:
            raise serializers.ValidationError('Month must be 1 to 12.')
        return value

    def validate_timezone(self, value):
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(value)
        except Exception:
            raise serializers.ValidationError(f'Unknown timezone "{value}". Example: Asia/Kolkata.')
        return value

    def validate_date_format(self, value):
        if value not in DATE_FORMATS:
            raise serializers.ValidationError(f'Use one of: {", ".join(DATE_FORMATS)}.')
        return value


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ['id', 'firm', 'name', 'code', 'is_default', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class UserSerializer(serializers.ModelSerializer):
    branches = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'phone', 'designation',
            'system_role', 'is_active', 'hourly_cost', 'joined_on',
            'left_on', 'created_at', 'branches',
            'can_create_tasks', 'effective_can_create_tasks', 'must_change_password'
        ]
        read_only_fields = ['id', 'created_at', 'effective_can_create_tasks', 'must_change_password']

    effective_can_create_tasks = serializers.BooleanField(read_only=True)

    def validate_email(self, value):
        value = value.strip().lower()
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def get_branches(self, obj):
        return [
            {'id': ub.branch.id, 'name': ub.branch.name, 'code': ub.branch.code, 'is_default': ub.is_default}
            for ub in obj.user_branches.select_related('branch').all()
        ]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=10)
    branch_ids = serializers.ListField(child=serializers.UUIDField(), required=False)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'phone', 'designation',
            'system_role', 'password', 'hourly_cost', 'joined_on',
            'branch_ids', 'can_create_tasks'
        ]

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate(self, attrs):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        password = attrs.get('password')
        if password:
            try:
                validate_password(password, user=User(email=attrs.get('email', ''), full_name=attrs.get('full_name', '')))
            except DjangoValidationError as exc:
                raise serializers.ValidationError({'password': list(exc.messages)})
        request = self.context.get('request')
        firm = request.user.firm if request else None
        branch_ids = attrs.get('branch_ids') or []
        if branch_ids and firm:
            ok = Branch.objects.filter(firm=firm, id__in=branch_ids).count()
            if ok != len(set(branch_ids)):
                raise serializers.ValidationError({'branch_ids': 'One or more branches do not belong to this firm.'})
        return attrs

    def create(self, validated_data):
        branch_ids = validated_data.pop('branch_ids', [])
        password = validated_data.pop('password', None)
        request = self.context.get('request')
        firm = request.user.firm if request and request.user.is_authenticated else None

        user = User.objects.create(firm=firm, **validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()

        # Assign default branch if none passed
        if branch_ids:
            for b_id in branch_ids:
                UserBranch.objects.create(user=user, branch_id=b_id)
        elif firm:
            default_branch = firm.branches.filter(is_default=True).first() or firm.branches.first()
            if default_branch:
                UserBranch.objects.create(user=user, branch=default_branch, is_default=True)

        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
