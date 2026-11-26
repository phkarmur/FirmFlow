import uuid
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import BulkBatch, BulkBatchRun
from .serializers import BulkBatchSerializer, BulkBatchRunSerializer
from .services import BulkBatchService
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.periods.models import Period


def _valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


class BulkBatchViewSet(viewsets.ModelViewSet):
    serializer_class = BulkBatchSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get_queryset(self):
        firm = self.request.user.firm
        if not firm:
            return BulkBatch.objects.none()
        return BulkBatch.objects.filter(firm=firm).select_related('task_type', 'firm')

    def perform_create(self, serializer):
        firm = self.request.user.firm
        default_branch = firm.branches.filter(is_default=True).first() or firm.branches.first()
        serializer.save(firm=firm, branch=default_branch, created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def preview(self, request, pk=None):
        """Preview run for a period (spec §5.5 B1). Body: {period_id}."""
        batch = self.get_object()
        period_id = request.data.get('period_id')
        period = None
        if _valid_uuid(period_id):
            period = Period.objects.filter(id=period_id, fy__firm=request.user.firm).select_related('fy').first()
        if period is None:
            return Response({'error': 'Select a valid period.'}, status=status.HTTP_400_BAD_REQUEST)
        kind = batch.task_type.period_kind
        if kind not in ('none', '', None) and kind != period.kind:
            return Response({'error': f'This task type needs a {kind} period, not {period.kind}.'},
                            status=status.HTTP_400_BAD_REQUEST)
        run = BulkBatchService.preview_batch_run(batch, period.fy, period, user=request.user)
        return Response(BulkBatchRunSerializer(run).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def run_detail(self, request, pk=None):
        """One run with its per-client items. ?run_id=<id>"""
        run_id = request.query_params.get('run_id')
        run = BulkBatchRun.objects.filter(id=run_id, batch=self.get_object()).first() if _valid_uuid(run_id) else None
        if run is None:
            return Response({'error': 'Run not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(BulkBatchRunSerializer(run).data)

    @action(detail=True, methods=['post'])
    def commit(self, request, pk=None):
        """Commit a preview run. Body: {run_id}."""
        run_id = request.data.get('run_id')
        run = BulkBatchRun.objects.filter(id=run_id, batch=self.get_object()).first() if _valid_uuid(run_id) else None
        if run is None:
            return Response({'error': 'Preview run not found.'}, status=status.HTTP_404_NOT_FOUND)
        if run.status != BulkBatchRun.Status.PREVIEW:
            return Response({'error': 'Can only commit a run in PREVIEW state.'}, status=status.HTTP_400_BAD_REQUEST)
        committed_run = BulkBatchService.commit_batch_run(run, user=request.user)
        return Response(BulkBatchRunSerializer(committed_run).data)
