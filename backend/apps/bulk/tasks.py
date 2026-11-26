import traceback
from celery import shared_task
from .models import BulkBatch, BulkBatchRun
from .services import BulkBatchService
from apps.common.dates import firm_today
from apps.common.logging import log_event
from apps.periods.generator import find_period

DEFAULT_PERIOD_OFFSET = -1   # create tasks for the PREVIOUS period (e.g. GSTR-3B Oct, created in Nov)


def target_period_for(batch, today):
    """
    schedule = {day_of_month: 1, months: [1..12] (optional), period_offset: -1 | 0}
    period_offset -1 (default) = previous period, 0 = current period.
    """
    schedule = batch.schedule or {}
    try:
        offset = int(schedule.get('period_offset', DEFAULT_PERIOD_OFFSET))
    except (TypeError, ValueError):
        offset = DEFAULT_PERIOD_OFFSET
    kind = batch.task_type.period_kind
    if not kind or kind == 'none':
        return None, offset
    return find_period(batch.firm, kind, today, offset), offset


@shared_task
def process_scheduled_batches():
    """Nightly: run recurring batches whose schedule matches today (firm timezone). Spec §5.5 B3."""
    log_event('job.start', 'Job', 'process_scheduled_batches')
    stats = {'checked': 0, 'ran': 0, 'skipped_not_today': 0, 'skipped_no_period': 0,
             'skipped_already_run': 0, 'failed': 0}
    batches = BulkBatch.objects.filter(is_active=True).select_related('firm', 'branch', 'task_type')
    for batch in batches:
        stats['checked'] += 1
        today = firm_today(batch.firm)
        schedule = batch.schedule or {}
        day_of_month = schedule.get('day_of_month')
        months = schedule.get('months') or []
        if not day_of_month:
            stats['skipped_not_today'] += 1      # manual-only batch
            continue
        if today.day != int(day_of_month) or (months and today.month not in [int(m) for m in months]):
            stats['skipped_not_today'] += 1
            continue
        period, offset = target_period_for(batch, today)
        if period is None:
            stats['skipped_no_period'] += 1
            log_event('bulk.scheduled_run', 'BulkBatch', batch.id, result='error', level='WARNING',
                      reason='no target period (generate FYs?)', offset=offset, today=today)
            continue
        if BulkBatchRun.objects.filter(batch=batch, period=period, status=BulkBatchRun.Status.COMMITTED).exists():
            stats['skipped_already_run'] += 1
            continue
        try:
            preview = BulkBatchService.preview_batch_run(batch, period.fy, period)
            run = BulkBatchService.commit_batch_run(preview)
            stats['ran'] += 1
            log_event('bulk.scheduled_run', 'BulkBatch', batch.id, period=period.label, offset=offset,
                      created=run.created_count, skipped=run.skipped_count, errors=run.error_count)
        except Exception as exc:  # noqa: BLE001 - every failure must be logged and raised to admins
            stats['failed'] += 1
            log_event('job.fail', 'BulkBatch', batch.id, result='error', level='ERROR',
                      error=str(exc), traceback=traceback.format_exc()[-2000:])
            BulkBatchService.notify_admins(batch, f'Batch "{batch.name}" failed for {period.label}', str(exc)[:500])
    log_event('job.end', 'Job', 'process_scheduled_batches', **stats)
    return stats
