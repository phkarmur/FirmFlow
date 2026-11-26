from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.conf import settings
from apps.accounts.models import Firm, User
from apps.tasks.models import Task, TaskIssue, TaskTimeLog
from .models import Notification, NotificationPreference
from apps.common.dates import firm_today
from apps.common.logging import log_event

@shared_task
def send_daily_digest():
    """
    §7.3 Daily email digest (07:00 AM firm time) sent to admins:
    Tasks created/completed/deleted yesterday, due today, overdue count,
    issues raised/resolved yesterday, staff with no time log yesterday.
    """
    log_event('job.start', 'Job', 'send_daily_digest')
    sent = failed = 0
    firms = Firm.objects.all()
    for firm in firms:
        today = firm_today(firm)
        yesterday = today - timedelta(days=1)
        # Get admin emails
        admins = User.objects.filter(
            firm=firm,
            system_role__in=[User.Role.SUPERADMIN, User.Role.ADMIN],
            is_active=True
        )
        opted_out = set(NotificationPreference.objects.filter(user__in=admins, digest_enabled=False).values_list('user_id', flat=True))
        recipient_list = [a.email for a in admins if a.email and a.id not in opted_out]
        if not recipient_list:
            continue

        # 1. Tasks yesterday
        tasks_created = Task.objects.filter(firm=firm, created_at__date=yesterday).count()
        tasks_completed = Task.objects.filter(firm=firm, completed_at__date=yesterday).count()
        tasks_deleted = Task.objects.filter(firm=firm, deleted_at__date=yesterday).count()

        # 2. Due today & Overdue
        due_today = Task.objects.filter(firm=firm, due_date=today).exclude(status__in=[Task.Status.COMPLETED, Task.Status.DELETED]).count()
        overdue = Task.objects.filter(firm=firm, due_date__lt=today, status__in=[Task.Status.NOT_STARTED, Task.Status.IN_PROCESS]).count()

        # 3. Issues yesterday
        issues_raised = TaskIssue.objects.filter(task__firm=firm, raised_at__date=yesterday).count()
        issues_resolved = TaskIssue.objects.filter(task__firm=firm, resolved_at__date=yesterday).count()

        # 4. Staff with no time log yesterday
        active_staff = User.objects.filter(firm=firm, is_active=True, system_role=User.Role.STAFF)
        logged_user_ids = set(TaskTimeLog.objects.filter(task__firm=firm, work_date=yesterday).values_list('user_id', flat=True))
        staff_no_time = [s.full_name for s in active_staff if s.id not in logged_user_ids]

        # Build digest body
        body = f"""Good Morning,

Here is your FirmFlow Daily Digest for {firm.name} ({today.strftime('%d-%m-%Y')}):

📋 TASKS SUMMARY:
- Due Today: {due_today}
- Overdue Pending: {overdue}
- Created Yesterday: {tasks_created}
- Completed Yesterday: {tasks_completed}
- Deleted Yesterday: {tasks_deleted}

⚠️ PENDING ISSUES:
- Raised Yesterday: {issues_raised}
- Resolved Yesterday: {issues_resolved}

⏱️ TIME LOGGING:
- Staff without time logs yesterday: {', '.join(staff_no_time) if staff_no_time else 'None (All logged!)'}

Log in to FirmFlow for detailed views and action items.
"""

        try:
            send_mail(
                subject=f"[{firm.name}] Daily Digest - {today.strftime('%d %b %Y')}",
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_list,
                fail_silently=False
            )
            sent += 1
            log_event('digest.send', 'Firm', firm.id, recipients=len(recipient_list), digest_date=today)
        except Exception as exc:  # noqa: BLE001 - must be logged, never hidden
            failed += 1
            log_event('digest.send', 'Firm', firm.id, result='error', level='ERROR',
                      recipients=len(recipient_list), error=str(exc))
    log_event('job.end', 'Job', 'send_daily_digest', sent=sent, failed=failed)


@shared_task
def purge_old_notifications():
    """Hard deletes notifications older than 180 days (§5.11 R1)."""
    cutoff = timezone.now() - timedelta(days=180)
    Notification.objects.filter(created_at__lt=cutoff).delete()


@shared_task
def send_notification_emails(notification_ids):
    """Worker side of notify(): send the queued notification e-mails."""
    from .service import send_emails_now
    sent, failed = send_emails_now(notification_ids)
    log_event('job.end', 'Job', 'send_notification_emails', sent=sent, failed=failed)


@shared_task
def send_due_reminders():
    """
    Daily (spec §7.1 "Task due today / overdue"): ONE summary notification per user,
    not one per task, so a person with 40 overdue tasks gets 1 message, not 40.
    Running it twice on the same day does not send twice.
    """
    from apps.tasks import selectors
    from .service import notify
    log_event('job.start', 'Job', 'send_due_reminders')
    stats = {'due_today': 0, 'overdue': 0, 'skipped_already_sent': 0}
    for firm in Firm.objects.all():
        today = firm_today(firm)
        base = selectors.base_queryset(firm)
        for user in User.objects.filter(firm=firm, is_active=True):
            mine = selectors.role_filter(base, user.id, 'assigned')
            for key, kind, label in (('due_today', Notification.Kind.DUE_TODAY, 'due today'),
                                     ('overdue', Notification.Kind.OVERDUE, 'overdue')):
                count = selectors.apply_tile(mine, key, firm, today).count()
                if not count:
                    continue
                if Notification.objects.filter(user=user, kind=kind, created_at__date=today).exists():
                    stats['skipped_already_sent'] += 1
                    continue
                notify(kind, [user], f'You have {count} task{"s" if count != 1 else ""} {label}',
                       body='Open the task list to see them.', firm=firm,
                       link=f'/tasks?tile={key}&role=assigned')
                stats[key] += 1
    log_event('job.end', 'Job', 'send_due_reminders', **stats)
    return stats
