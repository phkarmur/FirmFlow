from rest_framework import serializers
from .models import Client, ClientGroup, ClientContact
from .validators import validate_pan_format, validate_gstin_format, check_pan_entity_type_warning
from apps.common.crypto import pan_blind_index

class ClientContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientContact
        fields = ['id', 'client', 'name', 'role', 'email', 'phone', 'is_primary', 'receives_task_emails', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_client(self, value):
        request = self.context.get('request')
        if request and value.firm_id != request.user.firm_id:
            raise serializers.ValidationError('Client does not belong to this firm.')
        return value


class ClientGroupSerializer(serializers.ModelSerializer):
    client_count = serializers.IntegerField(source='clients.count', read_only=True)

    class Meta:
        model = ClientGroup
        fields = ['id', 'name', 'client_count', 'created_at']
        read_only_fields = ['id', 'created_at']


class ClientListSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source='client_group.name', read_only=True, default='')

    class Meta:
        model = Client
        fields = [
            'id', 'name', 'client_group', 'group_name', 'client_type',
            'pan_masked', 'gstin', 'email', 'phone', 'state_code',
            'is_active', 'is_blocked_for_new_tasks', 'created_at'
        ]


class ClientDetailSerializer(serializers.ModelSerializer):
    contacts = ClientContactSerializer(many=True, read_only=True)
    group_name = serializers.CharField(source='client_group.name', read_only=True, default='')
    pan = serializers.CharField(write_only=True, required=False, allow_blank=True)
    pan_warning = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Client
        fields = [
            'id', 'name', 'client_group', 'group_name', 'client_type',
            'pan', 'remove_pan', 'pan_masked', 'pan_warning', 'gstin', 'tan', 'cin',
            'email', 'phone', 'address', 'state_code',
            'is_active', 'is_blocked_for_new_tasks', 'notes',
            'contacts', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'pan_masked', 'created_at', 'updated_at']

    def get_pan_warning(self, obj):
        decrypted = obj.get_pan_decrypted()
        if decrypted:
            return check_pan_entity_type_warning(decrypted, obj.client_type)
        return None

    remove_pan = serializers.BooleanField(write_only=True, required=False, default=False)

    def validate_client_group(self, value):
        request = self.context.get('request')
        if value is not None and request and value.firm_id != request.user.firm_id:
            raise serializers.ValidationError('Client group does not belong to this firm.')
        return value

    def validate(self, attrs):
        """
        - Blank `pan` means "no change" (an edit form that does not show the PAN
          must not wipe it). Use remove_pan=true to clear it.
        - GSTIN is validated (format, state, checksum, PAN match) only when the
          GSTIN or PAN changes, so old records can still be edited.
        """
        request = self.context.get('request')
        firm = getattr(getattr(request, 'user', None), 'firm', None)
        raw_pan = (attrs.get('pan') or '').strip()
        if not raw_pan:
            attrs.pop('pan', None)
        clean_pan = ''
        if raw_pan:
            clean_pan = validate_pan_format(raw_pan)
            attrs['pan'] = clean_pan
            if firm:
                dup = Client.objects.filter(firm=firm, pan_hash=pan_blind_index(clean_pan))
                if self.instance:
                    dup = dup.exclude(id=self.instance.id)
                if dup.exists():
                    raise serializers.ValidationError({'pan': f'A client with this PAN already exists: {dup.first().name}.'})

        gstin_changed = 'gstin' in attrs and (attrs.get('gstin') or '') != (getattr(self.instance, 'gstin', '') or '')
        if gstin_changed or (clean_pan and (attrs.get('gstin') or getattr(self.instance, 'gstin', ''))):
            gstin = (attrs.get('gstin', getattr(self.instance, 'gstin', '')) or '').strip().upper()
            if gstin:
                pan_for_check = clean_pan or (self.instance.get_pan_decrypted() if self.instance and not attrs.get('remove_pan') else '')
                try:
                    attrs['gstin'] = validate_gstin_format(gstin, pan_for_check)
                except serializers.ValidationError as exc:
                    raise serializers.ValidationError({'gstin': exc.detail})
                if not attrs.get('state_code'):
                    attrs['state_code'] = attrs['gstin'][:2]
            else:
                attrs['gstin'] = ''
        for key in ('tan', 'cin'):
            if attrs.get(key):
                attrs[key] = attrs[key].strip().upper()
        return attrs

    def create(self, validated_data):
        raw_pan = validated_data.pop('pan', None)
        validated_data.pop('remove_pan', None)
        request = self.context.get('request')
        firm = request.user.firm if request and request.user.is_authenticated else None

        client = Client(firm=firm, **validated_data)
        if raw_pan:
            client.set_pan(raw_pan)
        client.save()
        return client

    def update(self, instance, validated_data):
        raw_pan = validated_data.pop('pan', None)
        remove_pan = validated_data.pop('remove_pan', False)
        if raw_pan:
            instance.set_pan(raw_pan)
        elif remove_pan:
            instance.set_pan('')

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ClientPickerSerializer(serializers.ModelSerializer):
    """Minimal fields for the create-task client search (staff may see these)."""
    class Meta:
        model = Client
        fields = ['id', 'name', 'client_type', 'pan_masked', 'is_active']
        read_only_fields = fields
