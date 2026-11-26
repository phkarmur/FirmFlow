import re
from django.db.models import Q
from django.http import HttpResponse
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Client, ClientGroup, ClientContact
from .serializers import (
    ClientListSerializer, ClientDetailSerializer, ClientPickerSerializer,
    ClientGroupSerializer, ClientContactSerializer
)
from apps.accounts.permissions import IsFirmMember, IsAdminOrSuperAdmin, IsAdminOrReadOnly as AdminWriteOrReadOnly
from apps.common.models import AuditLog
from apps.common.crypto import pan_blind_index
from apps.common.logging import log_event, log_permission_denied

PAN_RE = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')


def staff_client_ids(user):
    """Clients of tasks where the staff user holds any active task role."""
    from apps.tasks.models import Task
    from apps.tasks.selectors import role_filter
    return role_filter(Task.objects.filter(firm=user.firm).exclude(status='deleted'), user.id) \
        .values_list('client_id', flat=True)


class ClientGroupViewSet(viewsets.ModelViewSet):
    serializer_class = ClientGroupSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return ClientGroup.objects.none()
        return ClientGroup.objects.filter(firm=firm).prefetch_related('clients')

    def perform_create(self, serializer):
        serializer.save(firm=self.request.user.firm)


class ClientViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsFirmMember, AdminWriteOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['client_type', 'is_active', 'is_blocked_for_new_tasks', 'client_group']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def _is_picker(self):
        return self.action == 'list' and self.request.query_params.get('picker') == 'true'

    def get_queryset(self):
        user = self.request.user
        firm = user.firm
        if not firm:
            return Client.objects.none()
        qs = Client.objects.filter(firm=firm).select_related('client_group')
        if not (user.is_admin or user.is_superuser):
            if self._is_picker() and user.effective_can_create_tasks:
                qs = qs.filter(is_active=True)          # name-only search for task creation
            else:
                qs = qs.filter(id__in=staff_client_ids(user))
        q = (self.request.query_params.get('search') or '').strip()
        if q and self.action == 'list':
            cond = Q(name__icontains=q) | Q(gstin__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q)
            if PAN_RE.match(q.upper()):
                cond |= Q(pan_hash=pan_blind_index(q))
            qs = qs.filter(cond)
        return qs

    def get_serializer_class(self):
        if self._is_picker():
            return ClientPickerSerializer
        if self.action == 'list':
            return ClientListSerializer
        return ClientDetailSerializer

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        # Spec §3.2: same name + same phone -> warn (not block)
        name, phone = (request.data.get('name') or '').strip(), (request.data.get('phone') or '').strip()
        if name and phone:
            dups = Client.objects.filter(firm=request.user.firm, name__iexact=name, phone=phone).exclude(id=response.data['id'])
            if dups.exists():
                response.data['warnings'] = [f'Possible duplicate of existing client "{dups.first().name}" (same name and phone).']
        return response

    def perform_create(self, serializer):
        client = serializer.save()
        AuditLog.log(firm_id=self.request.user.firm.id, action='client.create', entity_type='Client',
                     entity_id=str(client.id), actor_user_id=self.request.user.id,
                     new_value={'name': client.name, 'pan': client.pan_masked}, request=self.request)
        log_event('client.create', 'Client', client.id, has_pan=bool(client.pan_hash), has_gstin=bool(client.gstin))

    def update(self, request, *args, **kwargs):
        client = self.get_object()
        # Spec C1: deactivating a client with open tasks needs explicit confirmation
        if client.is_active and str(request.data.get('is_active', '')).lower() in ('false', '0'):
            from apps.tasks.models import Task
            open_tasks = Task.objects.filter(client=client, status__in=['not_started', 'in_process', 'on_hold'])
            if open_tasks.exists() and str(request.data.get('confirm_deactivate', '')).lower() != 'true':
                return Response({
                    'error': f'{client.name} has {open_tasks.count()} open task(s). Confirm to deactivate anyway.',
                    'open_tasks': list(open_tasks.values('id', 'task_number', 'title')[:50]),
                    'requires_confirmation': True,
                }, status=status.HTTP_409_CONFLICT)
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        before = {'name': serializer.instance.name, 'is_active': serializer.instance.is_active,
                  'gstin_set': bool(serializer.instance.gstin), 'pan': serializer.instance.pan_masked}
        client = serializer.save()
        after = {'name': client.name, 'is_active': client.is_active, 'gstin_set': bool(client.gstin), 'pan': client.pan_masked}
        AuditLog.log(firm_id=self.request.user.firm.id, action='client.update', entity_type='Client',
                     entity_id=str(client.id), actor_user_id=self.request.user.id,
                     old_value=before, new_value=after, request=self.request)
        log_event('client.update', 'Client', client.id, changed=[k for k in after if after[k] != before[k]])

    def destroy(self, request, *args, **kwargs):
        client = self.get_object()
        from apps.tasks.models import Task
        task_count = Task.objects.filter(client=client).count()
        if task_count > 0:
            return Response({'error': f'Client has {task_count} associated tasks and cannot be deleted. Deactivate instead.'},
                            status=status.HTTP_400_BAD_REQUEST)
        client_id = client.id
        client.delete()
        AuditLog.log(firm_id=request.user.firm.id, action='client.delete', entity_type='Client',
                     entity_id=str(client_id), actor_user_id=request.user.id, request=request)
        log_event('client.delete', 'Client', client_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Client detail (spec §6.1-7): task counts by FY and status (tasks visible to the reader)."""
        from django.db.models import Count, Q
        from apps.tasks.models import Task
        from apps.tasks import selectors
        client = self.get_object()
        qs = selectors.visible_to(selectors.base_queryset(request.user.firm).filter(client=client), request.user)
        by_fy = list(qs.values('fy__label').annotate(
            total=Count('id'),
            pending=Count('id', filter=Q(status__in=selectors.PENDING)),
            completed=Count('id', filter=Q(status='completed')),
            unbilled=Count('id', filter=Q(status='completed', billing_state='unbilled')),
        ).order_by('-fy__label'))
        data = {'by_fy': by_fy, 'open_tasks': qs.filter(status__in=selectors.PENDING).count(),
                'overdue': selectors.apply_tile(qs, 'overdue', request.user.firm).count()}
        log_event('client.summary', 'Client', client.id, fys=len(by_fy))
        return Response(data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsAdminOrSuperAdmin])
    def reveal_pan(self, request, pk=None):
        """Reveal full PAN: Admin+ and a reason, audit logged (spec §9 S1)."""
        client = self.get_object()
        reason = (request.data.get('reason') or '').strip()
        if len(reason) < 3:
            return Response({'error': 'A valid reason (minimum 3 characters) is required to reveal full PAN.'}, status=status.HTTP_400_BAD_REQUEST)
        unmasked_pan = client.get_pan_decrypted()
        if not unmasked_pan:
            log_event('client.pan_reveal', 'Client', client.id, result='error', level='WARNING',
                      reason='no PAN or decryption failed', has_ciphertext=bool(client.pan_encrypted))
            return Response({'error': 'No PAN on record for this client.'}, status=status.HTTP_404_NOT_FOUND)
        AuditLog.log(firm_id=request.user.firm.id, action='client.pan_revealed', entity_type='Client',
                     entity_id=str(client.id), actor_user_id=request.user.id, new_value={'reason': reason}, request=request)
        log_event('client.pan_reveal', 'Client', client.id)
        return Response({'pan': unmasked_pan, 'name': client.name})

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsAdminOrSuperAdmin])
    def import_spreadsheet(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'Please upload a spreadsheet file.'}, status=status.HTTP_400_BAD_REQUEST)
        from .importer import ClientSpreadsheetImporter
        result = ClientSpreadsheetImporter.import_clients(request.user.firm, file, user=request.user)
        log_event('client.import', 'Client', '', result_keys=sorted(result.keys()) if isinstance(result, dict) else None)
        return Response(result)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated, IsAdminOrSuperAdmin])
    def download_template(self, request):
        from .importer import ClientSpreadsheetImporter
        response = HttpResponse(ClientSpreadsheetImporter.generate_template_csv(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="clients_import_template.csv"'
        return response


class ClientContactViewSet(viewsets.ModelViewSet):
    serializer_class = ClientContactSerializer
    permission_classes = [permissions.IsAuthenticated, IsFirmMember, AdminWriteOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        if not user.firm:
            return ClientContact.objects.none()
        qs = ClientContact.objects.filter(client__firm=user.firm)
        if not (user.is_admin or user.is_superuser):
            qs = qs.filter(client_id__in=staff_client_ids(user))
        client_id = self.request.query_params.get('client_id')
        if client_id:
            qs = qs.filter(client_id=client_id)
        return qs
