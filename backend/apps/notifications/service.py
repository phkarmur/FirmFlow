"""
Notification service (spec §7).

notify() writes one in-app Notification per recipient (in-app is always on) and,
when the user's preference allows it, sends an e-mail AFTER the database commit.

E-mail delivery:
  settings.NOTIFY_EMAIL_ASYNC = True  -> Celery task (needs worker + Redis; Docker)
  settings.NOTIFY_EMAIL_ASYNC = False -> sent in the web process after commit (local dev)
Every attempt writes a 'notify.send' log line with ok / fail.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from apps.common.logging import log_event
from .models import Notification, NotificationPreference

K = Notification.Kind


def _email_enabled(user):
    pref = NotificationPreference.objects.filter(user=user).only('email_enabled').first()
    return True if pref is None else bool(pref.email_enabled)   # default on (spec §7.2)


def notify(kind, recipients, title, body='', task=None, actor=None, firm=None, link='', email=True):
    """
    kind: Notification.Kind value. recipients: iterable of User or None (duplicates are fine).
    The actor never receives a notification about their own action. Inactive users are skipped.
    Returns the list of created Notification objects.
    """
    firm = firm or getattr(task, 'firm', None)
    seen, created = set(), []
    for user in recipients:
        if user is None or user.id in seen:
            continue
        seen.add(user.id)
        if actor is not None and user.id == actor.id:
            continue
        if not user.is_active:
            continue
        want_email = bool(email and user.email and _email_enabled(user))
        n = Notification.objects.create(
            firm=firm or user.firm, user=user, kind=kind, task=task, title=title[:255], body=body[:2000],
            link=link[:255], channels_sent={'in_app': True, 'email': 'pending' if want_email else False},
        )
        created.append(n)
        log_event('notify.send', 'Notification', n.id, channel='in_app', kind=kind, user_id=user.id,
                  task_id=getattr(task, 'id', None))
    to_email = [n.id for n in created if n.channels_sent.get('email') == 'pending']
    if to_email:
        transaction.on_commit(lambda ids=to_email: _dispatch_emails(ids))
    return created


def _dispatch_emails(notification_ids):
    if getattr(settings, 'NOTIFY_EMAIL_ASYNC', False):
        try:
            from .tasks import send_notification_emails
            send_notification_emails.delay([str(i) for i in notification_ids])
            log_event('notify.queue', 'Notification', '', count=len(notification_ids))
            return
        except Exception as exc:  # noqa: BLE001 - broker down: fall back to sending now
            log_event('notify.queue', 'Notification', '', result='error', level='WARNING',
                      error=str(exc), fallback='sync')
    send_emails_now(notification_ids)


def task_link(task):
    base = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
    return f"{base}/tasks?taskId={task.id}" if task else base


def send_emails_now(notification_ids):
    sent = failed = 0
    for n in Notification.objects.filter(id__in=notification_ids).select_related('user', 'task', 'firm'):
        link = task_link(n.task) if n.task else (getattr(settings, 'FRONTEND_URL', '').rstrip('/') + n.link if n.link else '')
        lines = [n.title, '']
        if n.body:
            lines += [n.body, '']
        if n.task:
            lines.append(f'Task: {n.task.task_number} - {n.task.title}')
        if link:
            lines.append(f'Open: {link}')
        lines += ['', f'— {n.firm.name} (FirmFlow). Change e-mail settings on your Profile page.']
        try:
            send_mail(subject=f'[{n.firm.name}] {n.title}'[:200], message='\n'.join(lines),
                      from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[n.user.email], fail_silently=False)
            n.channels_sent = {**n.channels_sent, 'email': True}
            sent += 1
            log_event('notify.send', 'Notification', n.id, channel='email', kind=n.kind, user_id=n.user_id)
        except Exception as exc:  # noqa: BLE001 - every failure is logged and kept on the row
            n.channels_sent = {**n.channels_sent, 'email': 'failed'}
            failed += 1
            log_event('notify.send', 'Notification', n.id, channel='email', result='error', level='ERROR',
                      kind=n.kind, user_id=n.user_id, error=str(exc))
        n.save(update_fields=['channels_sent', 'updated_at'])
    return sent, failed


# ---------------------------------------------------------------- task event helpers (spec §7.1)

def roles_of(task):
    """assigned, leader, manager and active members (User objects)."""
    people = [task.assigned_user, task.leader_user, task.manager_user]
    people += [m.user for m in task.members.filter(removed_at__isnull=True).select_related('user')]
    return people


def name(user):
    return user.full_name if user else 'System'
