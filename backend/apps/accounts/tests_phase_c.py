"""Phase C tests: login lockout, password reset (e-mail link + admin temporary password), sign out other devices."""
import re
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from apps.accounts.models import Firm, User, AuthThrottle

PW = 'Very-Strong-Pass-2026'


@override_settings(LOGIN_MAX_FAILURES=3, LOGIN_MAX_FAILURES_PER_IP=50, LOGIN_LOCKOUT_MINUTES=15,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', FRONTEND_URL='http://ff.test')
class SecurityTests(TestCase):
    def setUp(self):
        self.firm = Firm.objects.create(name='F')
        self.admin = User.objects.create_user(email='ad@f.com', full_name='Admin', firm=self.firm, system_role='admin', password=PW)
        self.sa = User.objects.create_user(email='sa@f.com', full_name='Super', firm=self.firm, system_role='superadmin', password=PW)
        self.staff = User.objects.create_user(email='st@f.com', full_name='Staff', firm=self.firm, system_role='staff', password=PW)

    def login(self, email, pw, client=None):
        c = client or APIClient()
        return c, c.post('/api/v1/auth/login/', {'email': email, 'password': pw}, format='json')

    def test_lockout_after_failures_and_unknown_email_same_answer(self):
        for _ in range(3):
            self.assertEqual(self.login('st@f.com', 'wrong')[1].status_code, 400)
        _, res = self.login('st@f.com', PW)            # right password, but locked
        self.assertEqual(res.status_code, 429)
        for _ in range(3):
            self.login('nobody@f.com', 'x')
        self.assertEqual(self.login('nobody@f.com', 'x')[1].status_code, 429)
        AuthThrottle.objects.all().delete()             # window passed
        self.assertEqual(self.login('st@f.com', PW)[1].status_code, 200)

    def test_success_clears_failures(self):
        self.login('st@f.com', 'wrong'); self.login('st@f.com', 'wrong')
        self.assertEqual(self.login('st@f.com', PW)[1].status_code, 200)
        self.assertEqual(AuthThrottle.objects.filter(key='st@f.com').count(), 0)

    def test_reset_link_flow(self):
        res = APIClient().post('/api/v1/auth/password_reset/', {'email': 'st@f.com'}, format='json')
        same = APIClient().post('/api/v1/auth/password_reset/', {'email': 'unknown@f.com'}, format='json')
        self.assertEqual(res.data, same.data)           # does not tell if the account exists
        self.assertEqual(len(mail.outbox), 1)
        m = re.search(r'uid=([^&\s]+)&token=(\S+)', mail.outbox[0].body)
        uid, token = m.group(1), m.group(2)
        bad = APIClient().post('/api/v1/auth/password_reset/confirm/', {'uid': uid, 'token': 'x-y', 'new_password': 'Another-Strong-77'}, format='json')
        self.assertEqual(bad.status_code, 400)
        weak = APIClient().post('/api/v1/auth/password_reset/confirm/', {'uid': uid, 'token': token, 'new_password': '123'}, format='json')
        self.assertEqual(weak.status_code, 400)
        ok = APIClient().post('/api/v1/auth/password_reset/confirm/', {'uid': uid, 'token': token, 'new_password': 'Another-Strong-77'}, format='json')
        self.assertEqual(ok.status_code, 200, ok.data)
        again = APIClient().post('/api/v1/auth/password_reset/confirm/', {'uid': uid, 'token': token, 'new_password': 'Third-Strong-888'}, format='json')
        self.assertEqual(again.status_code, 400)        # one-time link
        self.assertEqual(self.login('st@f.com', 'Another-Strong-77')[1].status_code, 200)

    def test_reset_request_throttle(self):
        for _ in range(7):
            APIClient().post('/api/v1/auth/password_reset/', {'email': 'st@f.com'}, format='json')
        self.assertEqual(len(mail.outbox), 5)

    def test_temporary_password_forces_change(self):
        c_admin, _ = self.login('ad@f.com', PW)
        c_staff_old, _ = self.login('st@f.com', PW)
        res = c_admin.post(f'/api/v1/accounts/users/{self.staff.id}/set_temporary_password/')
        self.assertEqual(res.status_code, 200, res.data)
        temp = res.data['temporary_password']
        # old session of the staff user is ended (password hash changed)
        self.assertEqual(c_staff_old.get('/api/v1/auth/me/').status_code, 403)
        # admin cannot reset a superadmin; staff cannot use the action
        self.assertEqual(c_admin.post(f'/api/v1/accounts/users/{self.sa.id}/set_temporary_password/').status_code, 403)
        c_staff, res = self.login('st@f.com', temp)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['user']['must_change_password'])
        self.assertEqual(c_staff.get('/api/v1/tasks/').status_code, 403)
        self.assertEqual(c_staff.get('/api/v1/auth/me/').status_code, 200)
        res = c_staff.post('/api/v1/auth/change_password/', {'current_password': temp, 'new_password': temp}, format='json')
        self.assertEqual(res.status_code, 400)          # must be a new password
        res = c_staff.post('/api/v1/auth/change_password/', {'current_password': temp, 'new_password': 'Own-Strong-Pass-1'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(c_staff.get('/api/v1/tasks/').status_code, 200)

    def test_logout_others(self):
        c1, _ = self.login('st@f.com', PW)
        c2, _ = self.login('st@f.com', PW)
        c3, _ = self.login('ad@f.com', PW)
        res = c1.post('/api/v1/auth/logout_others/')
        self.assertEqual(res.data['sessions_ended'], 1)
        self.assertEqual(c1.get('/api/v1/auth/me/').status_code, 200)
        self.assertEqual(c2.get('/api/v1/auth/me/').status_code, 403)
        self.assertEqual(c3.get('/api/v1/auth/me/').status_code, 200)   # other users are not touched


class AuditLogAppendOnlyTests(TestCase):
    def test_entries_cannot_change_or_go(self):
        from apps.common.models import AuditLog, AuditLogAppendOnly
        import uuid
        a = AuditLog.log(firm_id=uuid.uuid4(), action='x.test', entity_type='T', entity_id='1')
        a.action = 'changed'
        with self.assertRaises(AuditLogAppendOnly):
            a.save()
        with self.assertRaises(AuditLogAppendOnly):
            a.delete()
        with self.assertRaises(AuditLogAppendOnly):
            AuditLog.objects.filter(id=a.id).update(action='y')
        with self.assertRaises(AuditLogAppendOnly):
            AuditLog.objects.filter(id=a.id).delete()
        self.assertEqual(AuditLog.objects.get(id=a.id).action, 'x.test')

    def test_bad_forwarded_ip_is_not_stored(self):
        from django.test import RequestFactory
        from apps.common.models import AuditLog
        import uuid
        req = RequestFactory().get('/', HTTP_X_FORWARDED_FOR='not-an-ip', REMOTE_ADDR='10.0.0.5')
        req.user = type('U', (), {'is_authenticated': False})()
        a = AuditLog.log(firm_id=uuid.uuid4(), action='x.ip', entity_type='T', entity_id='1', request=req)
        self.assertEqual(a.ip, '10.0.0.5')     # header not trusted by default
        with override_settings(TRUST_X_FORWARDED_FOR=True):
            b = AuditLog.log(firm_id=uuid.uuid4(), action='x.ip', entity_type='T', entity_id='1', request=req)
        self.assertIsNone(b.ip)                 # bad value -> no IP instead of a database error


from django.test import TransactionTestCase


class BackupTests(TransactionTestCase):
    # Real commits: SQLite cannot copy a database inside an open transaction
    def test_backup_and_verify(self):
        import tempfile, tarfile, json
        from pathlib import Path
        from apps.common.backup import create_backup, verify_backup
        with tempfile.TemporaryDirectory() as d, override_settings(PRIVATE_MEDIA_ROOT=Path(d) / 'pm', MEDIA_ROOT=Path(d) / 'm'):
            (Path(d) / 'pm' / 'x').mkdir(parents=True)
            (Path(d) / 'pm' / 'x' / 'file.pdf').write_bytes(b'%PDF-1.4 test')
            Firm.objects.create(name='Backup firm')
            path = create_backup(Path(d) / 'b', keep=2)
            with tarfile.open(path) as t:
                names = t.getnames()
                manifest = json.load(t.extractfile('manifest.json'))
            self.assertIn('database.sqlite3', names)
            self.assertIn('private_media/x/file.pdf', names)
            self.assertEqual(manifest['row_counts']['accounts_firm'], 1)
            res = verify_backup(path)
            self.assertTrue(res['ok'], res)
            self.assertEqual(res['attachments'], 1)
            # keep=2 removes older files
            import time; time.sleep(1.1); create_backup(Path(d) / 'b', keep=2); time.sleep(1.1); create_backup(Path(d) / 'b', keep=2)
            self.assertEqual(len(list((Path(d) / 'b').glob('firmflow-*.tar.gz'))), 2)

    def test_verify_rejects_other_files(self):
        import tempfile, tarfile
        from pathlib import Path
        from apps.common.backup import verify_backup, BackupError
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'x.tar.gz'
            with tarfile.open(p, 'w:gz') as t:
                f = Path(d) / 'a.txt'; f.write_text('a'); t.add(str(f), arcname='a.txt')
            with self.assertRaises(BackupError):
                verify_backup(p)
