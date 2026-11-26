from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ServiceCategory, Service, TaskType, TaskTypeTodoTemplate, Milestone, PendingIssueLabel, ComplianceEvent
from .serializers import (
    ServiceCategorySerializer, ServiceSerializer, TaskTypeSerializer,
    TaskTypeTodoTemplateSerializer, MilestoneSerializer, PendingIssueLabelSerializer,
    ComplianceEventSerializer,
)
from django.db.models import ProtectedError
from apps.accounts.permissions import IsFirmMember, IsAdminOrSuperAdmin, IsAdminOrReadOnly
from apps.common.logging import log_event


class SafeDestroyMixin:
    """Deleting a tree node that tasks still use returns 400 with a clear message, not 500."""
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        try:
            response = super().destroy(request, *args, **kwargs)
        except ProtectedError:
            log_event('service_tree.delete', type(obj).__name__, obj.pk, result='error', level='WARNING',
                      reason='in use by tasks')
            return Response({'error': f'"{obj}" is used by existing tasks. Deactivate it instead of deleting.'},
                            status=status.HTTP_400_BAD_REQUEST)
        log_event('service_tree.delete', type(obj).__name__, obj.pk)
        return response

class ServiceCategoryViewSet(SafeDestroyMixin, viewsets.ModelViewSet):
    serializer_class = ServiceCategorySerializer
    permission_classes = [permissions.IsAuthenticated, IsFirmMember, IsAdminOrReadOnly]

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return ServiceCategory.objects.none()
        return ServiceCategory.objects.filter(firm=firm).prefetch_related('services__task_types__milestones')

    def perform_create(self, serializer):
        serializer.save(firm=self.request.user.firm)


class ServiceViewSet(SafeDestroyMixin, viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated, IsFirmMember, IsAdminOrReadOnly]

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return Service.objects.none()
        return Service.objects.filter(category__firm=firm).prefetch_related('task_types__milestones')


class TaskTypeViewSet(SafeDestroyMixin, viewsets.ModelViewSet):
    serializer_class = TaskTypeSerializer
    permission_classes = [permissions.IsAuthenticated, IsFirmMember, IsAdminOrReadOnly]

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return TaskType.objects.none()
        return TaskType.objects.filter(service__category__firm=firm).prefetch_related('milestones', 'todo_templates')

    def perform_update(self, serializer):
        instance = serializer.instance
        # Spec §3.2: block deactivating a task type that an active batch uses
        if instance.is_active and serializer.validated_data.get('is_active') is False:
            from apps.bulk.models import BulkBatch
            if BulkBatch.objects.filter(task_type=instance, is_active=True).exists():
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'is_active': 'An active recurring batch uses this task type. Deactivate the batch first.'})
        serializer.save()
        log_event('task_type.update', 'TaskType', instance.id, fields=sorted(serializer.validated_data.keys()))

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsAdminOrSuperAdmin])
    def reorder_milestones(self, request, pk=None):
        """Body: {ids: [milestone ids in the new order]}. New order applies to NEW tasks only."""
        tt = self.get_object()
        ids = request.data.get('ids') or []
        existing = {str(m.id): m for m in tt.milestones.all()}
        if sorted(map(str, ids)) != sorted(existing):
            return Response({'error': 'Send every milestone of this task type exactly once.'}, status=status.HTTP_400_BAD_REQUEST)
        for pos, mid in enumerate(ids, start=1):
            m = existing[str(mid)]
            if m.sort_order != pos:
                m.sort_order = pos
                m.save(update_fields=['sort_order', 'updated_at'])
        log_event('task_type.reorder_milestones', 'TaskType', tt.id, order=[existing[str(i)].name for i in ids])
        fresh = self.get_queryset().get(pk=tt.pk)   # re-read: the prefetched milestones are stale
        return Response(TaskTypeSerializer(fresh, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsAdminOrSuperAdmin])
    def reorder_todos(self, request, pk=None):
        """Body: {ids: [todo template ids in the new order]}."""
        tt = self.get_object()
        ids = request.data.get('ids') or []
        existing = {str(t.id): t for t in tt.todo_templates.all()}
        if sorted(map(str, ids)) != sorted(existing):
            return Response({'error': 'Send every checklist item exactly once.'}, status=status.HTTP_400_BAD_REQUEST)
        for pos, tid in enumerate(ids, start=1):
            t = existing[str(tid)]
            if t.sort_order != pos:
                t.sort_order = pos
                t.save(update_fields=['sort_order', 'updated_at'])
        log_event('task_type.reorder_todos', 'TaskType', tt.id, count=len(ids))
        fresh = self.get_queryset().get(pk=tt.pk)
        return Response(TaskTypeSerializer(fresh, context={'request': request}).data)

    @action(detail=False, methods=['get'])
    def flat_list(self, request):
        """Returns simplified flat list of task types for quick dropdown selections."""
        qs = self.get_queryset().filter(is_active=True).select_related('service__category')
        data = [
            {
                'id': t.id,
                'name': t.name,
                'full_name': f"{t.service.category.name} → {t.service.name} → {t.name}",
                'code': t.code,
                'recurrence': t.recurrence,
                'period_kind': t.period_kind,
                'default_due_rule': t.default_due_rule,
                'uses_assessment_year': t.uses_assessment_year,
            }
            for t in qs
        ]
        return Response(data)


class TaskTypeTodoTemplateViewSet(SafeDestroyMixin, viewsets.ModelViewSet):
    serializer_class = TaskTypeTodoTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return TaskTypeTodoTemplate.objects.none()
        return TaskTypeTodoTemplate.objects.filter(task_type__service__category__firm=firm)


class MilestoneViewSet(SafeDestroyMixin, viewsets.ModelViewSet):
    serializer_class = MilestoneSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return Milestone.objects.none()
        return Milestone.objects.filter(task_type__service__category__firm=firm)


class PendingIssueLabelViewSet(SafeDestroyMixin, viewsets.ModelViewSet):
    serializer_class = PendingIssueLabelSerializer
    permission_classes = [permissions.IsAuthenticated, IsFirmMember, IsAdminOrReadOnly]

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return PendingIssueLabel.objects.none()
        qs = PendingIssueLabel.objects.filter(firm=firm)
        if self.request.query_params.get('include_inactive') != 'true':
            qs = qs.filter(is_active=True)
        return qs

    def perform_create(self, serializer):
        serializer.save(firm=self.request.user.firm)


class ComplianceEventViewSet(SafeDestroyMixin, viewsets.ModelViewSet):
    """
    Dashboard compliance calendar. Read: every firm member (dashboard).
    Add / edit / remove / enable / disable: Admin+ (Settings page).
    ?active=true -> only enabled rows, sorted by next due date (dashboard order).
    """
    serializer_class = ComplianceEventSerializer
    permission_classes = [permissions.IsAuthenticated, IsFirmMember, IsAdminOrReadOnly]
    pagination_class = None

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return ComplianceEvent.objects.none()
        qs = ComplianceEvent.objects.filter(firm=firm).select_related('firm')
        if self.request.query_params.get('active') == 'true':
            qs = qs.filter(is_active=True)
        return qs

    def get_serializer_context(self):
        from apps.common.dates import firm_today
        ctx = super().get_serializer_context()
        if self.request.user.firm:
            ctx['today'] = firm_today(self.request.user.firm)
        return ctx

    def list(self, request, *args, **kwargs):
        data = self.get_serializer(self.get_queryset(), many=True).data
        if request.query_params.get('active') == 'true':
            data = sorted(data, key=lambda r: (str(r['next_due_date'] or '9999'), r['sort_order']))
        counts = {}
        for r in data:
            counts[r['state']] = counts.get(r['state'], 0) + 1
        log_event('compliance_calendar.list', 'Firm', getattr(request.user.firm, 'id', ''),
                  rows=len(data), today=self.get_serializer_context().get('today'), states=counts)
        return Response(data)

    def perform_create(self, serializer):
        obj = serializer.save(firm=self.request.user.firm)
        log_event('compliance_calendar.create', 'ComplianceEvent', obj.id, code=obj.code,
                  due_day=obj.due_day, due_months=obj.due_months)

    def perform_update(self, serializer):
        obj = serializer.save()
        log_event('compliance_calendar.update', 'ComplianceEvent', obj.id, code=obj.code,
                  fields=sorted(serializer.validated_data.keys()), is_active=obj.is_active)
