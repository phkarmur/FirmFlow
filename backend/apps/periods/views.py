from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from apps.common.dates import firm_today
from .generator import find_period
from .models import FinancialYear, Period
from .serializers import FinancialYearSerializer, PeriodSerializer
from apps.accounts.permissions import IsFirmMember

class FinancialYearViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FinancialYearSerializer
    permission_classes = [permissions.IsAuthenticated, IsFirmMember]

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return FinancialYear.objects.none()
        return FinancialYear.objects.filter(firm=firm).prefetch_related('periods')


class PeriodViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PeriodSerializer
    permission_classes = [permissions.IsAuthenticated, IsFirmMember]

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return Period.objects.none()
        qs = Period.objects.filter(fy__firm=firm)
        fy_id = self.request.query_params.get('fy_id')
        kind = self.request.query_params.get('kind')
        if fy_id:
            qs = qs.filter(fy_id=fy_id)
        if kind:
            qs = qs.filter(kind=kind)
        # Newest first is what users pick most; ?order=asc keeps the old order
        if self.request.query_params.get('order') != 'asc':
            qs = qs.order_by('-start_date', 'sequence')
        return qs

    @action(detail=False, methods=['get'])
    def suggest(self, request):
        """
        Suggest FY + period for a task type (spec §6.1 create task: auto-suggest).
        ?task_type=<id>&offset=-1  (default -1 = previous period, e.g. GSTR-3B for last month)
        """
        from apps.services.models import TaskType
        firm = request.user.firm
        tt = TaskType.objects.filter(id=request.query_params.get('task_type'), service__category__firm=firm).first()
        if tt is None:
            raise ValidationError({'task_type': 'Task type not found.'})
        try:
            offset = int(request.query_params.get('offset', -1))
        except ValueError:
            raise ValidationError({'offset': 'Offset must be a number.'})
        today = firm_today(firm)
        kind = tt.period_kind if tt.period_kind != 'none' else None
        period = find_period(firm, kind, today, offset) if kind else None
        if period is not None:
            fy = period.fy
        else:
            year_period = find_period(firm, 'year', today, 0)
            fy = year_period.fy if year_period else None
        return Response({
            'period': PeriodSerializer(period).data if period else None,
            'fy': {'id': str(fy.id), 'label': fy.label} if fy else None,
            'period_kind': tt.period_kind, 'offset': offset,
        })
