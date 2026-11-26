"""
Phase B1 tests: notifications, attachments, members, move tasks, profile.
Run: python manage.py test apps.tasks.tests_phase_b1
"""
import io
import tempfile
import zipfile
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from apps.notifications.models import Notification, NotificationPreference
from apps.tasks.models import Task, TaskAttachment, TaskMember
from apps.tasks.services.task_service import TaskService
from apps.tasks.tests_phase_a import PhaseABase

K = Notification.Kind


class NotificationEventTests(PhaseABase):
    def kinds(self, user):
        return list(Notification.objects.filter(user=user).values_list('kind', flat=True))

    def test_assign_on_create(self):
        self.assertIn(K.TASK_ASSIGNED, self.kinds(self.staff))

    def test_reassign_notifies_old_new_and_leader(self):
        self.task.leader_user = self.superadmin
        self.task.save()
        Notification.objects.all().delete()
        TaskService.reassign_task(self.task, 'assigned', self.other, self.admin, reason='leave')
        self.assertIn(K.TASK_ASSIGNED, self.kinds(self.other))
        self.assertIn(K.TASK_REASSIGNED, self.kinds(self.staff))
        self.assertIn(K.TASK_REASSIGNED, self.kinds(self.superadmin))
        self.assertEqual(self.kinds(self.admin), [])          # actor gets nothing

    def test_comment_notifies_roles_not_author(self):
        self.task.leader_user = self.other
        self.task.save()
        Notification.objects.all().delete()
        TaskService.add_comment(self.task, self.staff, 'Uploaded the data')
        self.assertIn(K.COMMENT_POSTED, self.kinds(self.other))
        self.assertEqual(self.kinds(self.staff), [])

    def test_issue_raise_and_resolve(self):
        from apps.services.models import PendingIssueLabel
        label = PendingIssueLabel.objects.create(firm=self.firm, name='Docs pending')
        self.task.leader_user = self.other
        self.task.save()
        issue = TaskService.raise_issue(self.task, self.admin, label.id, detail='bank stmt')
        self.assertIn(K.ISSUE_RAISED, self.kinds(self.staff))
        self.assertIn(K.ISSUE_RAISED, self.kinds(self.other))
        TaskService.resolve_issue(self.task, issue, self.staff)
        self.assertIn(K.ISSUE_RESOLVED, self.kinds(self.admin))

    def test_delete_notifies_all_roles(self):
        TaskService.soft_delete(self.task, self.admin, 'duplicate')
        self.assertIn(K.TASK_DELETED, self.kinds(self.staff))

    def test_email_sent_after_commit_and_preference_respected(self):
        with self.captureOnCommitCallbacks(execute=True):
            TaskService.reassign_task(self.task, 'assigned', self.other, self.admin, reason='leave')
        to = [m.to[0] for m in mail.outbox]
        self.assertIn(self.other.email, to)
        mail.outbox.clear()
        NotificationPreference.objects.update_or_create(user=self.staff, defaults={'email_enabled': False})
        with self.captureOnCommitCallbacks(execute=True):
            TaskService.reassign_task(self.task, 'assigned', self.staff, self.admin, reason='back')
        self.assertNotIn(self.staff.email, [m.to[0] for m in mail.outbox])
        self.assertTrue(Notification.objects.filter(user=self.staff, kind=K.TASK_ASSIGNED).exists())  # in-app always

    def test_due_reminder_one_summary_per_user_and_no_repeat(self):
        from apps.notifications.tasks import send_due_reminders
        Task.objects.filter(id=self.task.id).update(due_date=timezone.localdate())
        send_due_reminders()
        send_due_reminders()
        self.assertEqual(Notification.objects.filter(user=self.staff, kind=K.DUE_TODAY).count(), 1)


@override_settings(PRIVATE_MEDIA_ROOT=tempfile.mkdtemp())
class AttachmentTests(PhaseABase):
    def upload(self, user, name, data, **extra):
        f = io.BytesIO(data)
        f.name = name
        return self.api(user).post(f'/api/v1/tasks/{self.task.id}/upload_attachment/', {'file': f, **extra})

    def test_pdf_upload_download_delete(self):
        res = self.upload(self.staff, 'gst.pdf', b'%PDF-1.4 test')
        self.assertEqual(res.status_code, 201, res.data)
        url = res.data['download_url']
        dl = self.api(self.staff).get(url)
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(b''.join(dl.streaming_content), b'%PDF-1.4 test')
        self.assertEqual(dl['X-Content-Type-Options'], 'nosniff')
        att = TaskAttachment.objects.get()
        self.assertNotIn('gst', att.file.name)                       # random storage name
        self.assertEqual(self.api(self.other).get(url).status_code, 404)  # no role -> cannot even see the task
        res = self.api(self.staff).post(f'/api/v1/tasks/{self.task.id}/delete_attachment/', {'attachment_id': str(att.id)})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.api(self.staff).get(url).status_code, 404)

    def test_renamed_exe_rejected(self):
        res = self.upload(self.staff, 'invoice.pdf', b'MZ\x90\x00\x03\x00\x00\x00 exe')
        self.assertEqual(res.status_code, 400)

    def test_extension_not_allowed(self):
        self.assertEqual(self.upload(self.staff, 'run.exe', b'MZ').status_code, 400)

    def test_xlsx_detected_by_structure(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('[Content_Types].xml', '<x/>')
            z.writestr('xl/workbook.xml', '<x/>')
        self.assertEqual(self.upload(self.staff, 'data.xlsx', buf.getvalue()).status_code, 201)
        self.assertEqual(self.upload(self.staff, 'data.docx', buf.getvalue()).status_code, 400)

    def test_duplicate_warning_then_confirm(self):
        self.assertEqual(self.upload(self.staff, 'a.txt', b'hello').status_code, 201)
        res = self.upload(self.staff, 'b.txt', b'hello')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(self.upload(self.staff, 'b.txt', b'hello', confirm_duplicate='true').status_code, 201)

    def test_size_limit(self):
        self.firm.max_upload_mb = 1
        self.firm.save()
        self.assertEqual(self.upload(self.staff, 'big.txt', b'a' * (1024 * 1024 + 1)).status_code, 400)


class MemberAndMoveTests(PhaseABase):
    def test_leader_adds_and_removes_member(self):
        self.task.leader_user = self.admin
        self.task.save()
        res = self.api(self.admin).post(f'/api/v1/tasks/{self.task.id}/add_member/', {'user_id': str(self.other.id)})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data['members']), 1)
        self.assertEqual(self.api(self.staff).post(f'/api/v1/tasks/{self.task.id}/remove_member/',
                                                   {'user_id': str(self.other.id)}).status_code, 403)
        res = self.api(self.admin).post(f'/api/v1/tasks/{self.task.id}/remove_member/', {'user_id': str(self.other.id)})
        self.assertEqual(res.data['members'], [])

    def test_move_tasks_preview_then_commit_then_deactivate(self):
        url = f'/api/v1/accounts/users/{self.staff.id}/move_tasks/'
        prev = self.api(self.admin).post(url, {'preview': True}, format='json')
        self.assertEqual(prev.data['counts']['assigned'], 1)
        self.task.refresh_from_db()
        self.assertEqual(self.task.assigned_user, self.staff)            # preview changes nothing
        self.assertEqual(self.api(self.admin).patch(f'/api/v1/accounts/users/{self.staff.id}/', {'is_active': False},
                                                    format='json').status_code, 400)
        res = self.api(self.admin).post(url, {'to_user_id': str(self.other.id), 'reason': 'left firm'}, format='json')
        self.assertEqual(res.data['moved']['assigned'], 1)
        self.task.refresh_from_db()
        self.assertEqual(self.task.assigned_user, self.other)
        self.assertEqual(self.api(self.admin).patch(f'/api/v1/accounts/users/{self.staff.id}/', {'is_active': False},
                                                    format='json').status_code, 200)


class ProfileTests(PhaseABase):
    def test_profile_and_password(self):
        res = self.api(self.staff).patch('/api/v1/auth/profile/', {'phone': '99999', 'notifications': {'email_enabled': False}}, format='json')
        self.assertEqual(res.data['phone'], '99999')
        self.assertFalse(res.data['notifications']['email_enabled'])
        self.staff.set_password('OldPass@12345')
        self.staff.save()
        bad = self.api(self.staff).post('/api/v1/auth/change_password/', {'current_password': 'x', 'new_password': 'NewPass@12345'})
        self.assertEqual(bad.status_code, 400)
        ok = self.api(self.staff).post('/api/v1/auth/change_password/', {'current_password': 'OldPass@12345', 'new_password': 'NewPass@12345xyz'})
        self.assertEqual(ok.status_code, 200, ok.data)


class NotificationAccessTests(PhaseABase):
    def test_reassigned_away_notification_cannot_open(self):
        TaskService.reassign_task(self.task, 'assigned', self.other, self.admin, reason='leave')
        rows = self.api(self.staff).get('/api/v1/notifications/').data['results']
        away = [r for r in rows if r['kind'] == K.TASK_REASSIGNED][0]
        self.assertFalse(away['can_open'])                     # staff has no role now -> no 404 click
        rows = self.api(self.other).get('/api/v1/notifications/').data['results']
        self.assertTrue([r for r in rows if r['kind'] == K.TASK_ASSIGNED][0]['can_open'])
