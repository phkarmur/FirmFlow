from celery import shared_task
from django.conf import settings
from apps.common.logging import log_event


@shared_task
def daily_backup():
    """Celery beat 01:30. Does nothing unless BACKUP_DAILY is on."""
    if not settings.BACKUP_DAILY:
        log_event('backup.daily', 'System', '', result='skipped', reason='BACKUP_DAILY is off')
        return 'skipped'
    from apps.common.backup import create_backup
    try:
        return str(create_backup())
    except Exception as exc:
        log_event('backup.daily', 'System', '', result='error', level='ERROR', error=str(exc)[:500])
        raise
