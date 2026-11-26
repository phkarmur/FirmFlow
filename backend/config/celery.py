import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('firmflow')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Celery Beat Periodic Tasks
app.conf.beat_schedule = {
    'send-daily-digest-every-morning': {
        'task': 'apps.notifications.tasks.send_daily_digest',
        'schedule': crontab(hour=7, minute=0), # 07:00 AM local firm time
    },
    'send-due-reminders-daily': {
        'task': 'apps.notifications.tasks.send_due_reminders',
        'schedule': crontab(hour=8, minute=0),  # 08:00 firm time
    },
    'run-scheduled-bulk-batches': {
        'task': 'apps.bulk.tasks.process_scheduled_batches',
        'schedule': crontab(hour=1, minute=0), # 01:00 AM
    },
    'ensure-financial-years-daily': {
        'task': 'apps.periods.tasks.ensure_financial_years_all_firms',
        'schedule': crontab(hour=0, minute=30),  # 00:30 firm time
    },
    'daily-backup': {
        'task': 'apps.common.tasks.daily_backup',
        'schedule': crontab(hour=1, minute=30),  # only works when BACKUP_DAILY=true
    },
    'cleanup-stale-notifications': {
        'task': 'apps.notifications.tasks.purge_old_notifications',
        'schedule': crontab(hour=3, minute=0, day_of_week=0), # Weekly
    },
}
