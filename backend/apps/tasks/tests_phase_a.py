"""
Phase A regression tests: one test per confirmed bug from the review.
Run: python manage.py test apps.tasks.tests_phase_a
"""
from datetime import date, datetime, timedelta, timezone as dt_tz
from unittest import mock
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from apps.accounts.models import Firm, Branch, User
from apps.clients.models import Client
from apps.services.models import ServiceCategory, Service, TaskType, TaskTypeTodoTemplate, Milestone
from apps.periods.generator import generate_financial_years_for_firm, find_period
from apps.periods.models import FinancialYear, Period
from apps.tasks.models import Task, TaskTimeLog
from apps.tasks.services.task_service import TaskService
from apps.tasks.services.due_dates import calculate_due_date
from apps.clients.validators import validate_gstin_format, gstin_check_char


class PhaseABase(TestCase):
    def setUp(self):
        self.firm = Firm.objects.create(name='Firm A', allow_pickup=True)
        self.branch = Branch.objects.create(firm=self.firm, name='HQ', code='HQ', is_default=True)
        self.superadmin = User.objects.create_user(email='sa@a.com', full_name='Super A', firm=self.firm, system_role='superadmin')
        self.admin = User.objects.create_user(email='ad@a.com', full_name='Admin A', firm=self.firm, system_role='admin')
        self.staff = User.objects.create_user(email='st@a.com', full_name='Staff A', firm=self.firm, system_role='staff')
        self.other = User.objects.create_user(email='ot@a.com', full_name='Other B', firm=self.firm, system_role='staff')
        generate_financial_years_for_firm(self.firm, start_calendar_year=timezone.localdate().year - 2)
        cat = ServiceCategory.objects.create(firm=self.firm, name='Tax')
        svc = Service.objects.create(category=cat, name='GST')
        self.tt = TaskType.objects.create(service=svc, name='GSTR-3B', code='3B', period_kind='month',
                                          default_due_rule={'kind': 'fixed_day_after_period_end', 'day': 20})
        TaskTypeTodoTemplate.objects.create(task_type=self.tt, text='Mandatory', is_mandatory=True)
        self.client_obj = Client.objects.create(firm=self.firm, name='Acme')
        self.period = Period.objects.filter(fy__firm=self.firm, kind='month').order_by('-start_date')[5]
        self.task = TaskService.create_task(self.firm, self.branch, self.client_obj, self.tt, self.admin,
                                            period=self.period, assigned_user=self.staff)

    def api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c


class PermissionTests(PhaseABase):
    def test_staff_patch_cannot_change_status_billing_or_roles(self):
        res = self.api(self.staff).patch(f'/api/v1/tasks/{self.task.id}/',
                                         {'status': 'completed', 'billing_state': 'billed', 'version': 1}, format='json')
        self.assertEqual(res.status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'not_started')
        self.assertEqual(self.task.billing_state, 'unbilled')

    def test_assigned_staff_cannot_edit_fields_but_leader_can(self):
        res = self.api(self.staff).patch(f'/api/v1/tasks/{self.task.id}/', {'priority': 'high', 'version': 1}, format='json')
        self.assertEqual(res.status_code, 403)
        self.task.leader_user = self.other
        self.task.save()
        res = self.api(self.other).patch(f'/api/v1/tasks/{self.task.id}/', {'priority': 'high', 'version': 1}, format='json')
        self.assertEqual(res.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.priority, 'high')
        self.assertEqual(self.task.version, 2)  # version increases on every write

    def test_patch_requires_version(self):
        res = self.api(self.admin).patch(f'/api/v1/tasks/{self.task.id}/', {'priority': 'high'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_member_cannot_reassign(self):
        self.task.members.create(user=self.other)
        res = self.api(self.other).post(f'/api/v1/tasks/{self.task.id}/reassign/',
                                        {'field': 'assigned', 'new_user_id': str(self.other.id), 'reason': 'mine'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_bad_reassign_field_is_400_not_500(self):
        res = self.api(self.admin).post(f'/api/v1/tasks/{self.task.id}/reassign/',
                                        {'field': 'firm', 'new_user_id': str(self.other.id), 'reason': 'xyz'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_deleted_task_cannot_be_restored(self):
        TaskService.soft_delete(self.task, self.admin, 'duplicate')
        res = self.api(self.admin).post(f'/api/v1/tasks/{self.task.id}/change_status/', {'status': 'in_process'}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.api(self.staff).post(f'/api/v1/tasks/{self.task.id}/change_status/?show_deleted=true',
                                        {'status': 'in_process'}, format='json')
        self.assertEqual(res.status_code, 404)

    def test_no_role_staff_cannot_see_task(self):
        res = self.api(self.other).get(f'/api/v1/tasks/{self.task.id}/')
        self.assertEqual(res.status_code, 404)

    def test_staff_cannot_write_clients_or_service_tree(self):
        self.assertEqual(self.api(self.staff).post('/api/v1/clients/', {'name': 'X'}, format='json').status_code, 403)
        self.assertEqual(self.api(self.staff).post('/api/v1/services/categories/', {'name': 'Y'}, format='json').status_code, 403)

    def test_staff_sees_only_clients_of_own_tasks(self):
        Client.objects.create(firm=self.firm, name='Hidden Co')
        names = [c['name'] for c in self.api(self.staff).get('/api/v1/clients/').data['results']]
        self.assertEqual(names, ['Acme'])

    def test_admin_cannot_create_superadmin(self):
        res = self.api(self.admin).post('/api/v1/accounts/users/', {'email': 'x@a.com', 'full_name': 'X',
                                                                    'system_role': 'superadmin'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_users_cannot_be_hard_deleted(self):
        res = self.api(self.superadmin).delete(f'/api/v1/accounts/users/{self.other.id}/')
        self.assertEqual(res.status_code, 405)

    def test_staff_cannot_read_other_users_time_logs(self):
        res = self.api(self.staff).get(f'/api/v1/reports/timelogs/?user_id={self.other.id}')
        self.assertEqual(res.status_code, 403)

    def test_time_log_viewset_create_is_disabled(self):
        res = self.api(self.staff).post('/api/v1/tasks/time-logs/', {'task': str(self.task.id), 'minutes': 5}, format='json')
        self.assertEqual(res.status_code, 405)

    def test_cannot_complete_with_open_mandatory_todo_via_status_action(self):
        res = self.api(self.staff).post(f'/api/v1/tasks/{self.task.id}/change_status/', {'status': 'completed'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('completion_blocked', res.data)


class ListAndDashboardTests(PhaseABase):
    def test_comma_status_filter_works(self):
        res = self.api(self.admin).get('/api/v1/tasks/?status=in_process,not_started&page_size=6')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['count'], 1)

    def test_every_tile_count_equals_list_count(self):
        stats = self.api(self.admin).get('/api/v1/reports/dashboard/office/').data
        from apps.tasks.selectors import TILE_KEYS
        for key in TILE_KEYS:
            res = self.api(self.admin).get(f'/api/v1/tasks/?tile={key}')
            self.assertEqual(res.status_code, 200, key)
            self.assertEqual(stats[key], res.data['count'], key)

    def test_search_by_full_pan(self):
        self.client_obj.set_pan('AABCA1234F')
        self.client_obj.save()
        res = self.api(self.admin).get('/api/v1/tasks/?search=aabca1234f')
        self.assertEqual(res.data['count'], 1)

    def test_periods_newest_first(self):
        res = self.api(self.admin).get('/api/v1/periods/periods/')
        self.assertGreaterEqual(res.data['results'][0]['start_date'], str(timezone.localdate().year - 1))


class DateAndRuleTests(PhaseABase):
    def test_log_time_today_at_0130_ist_is_accepted(self):
        fake = datetime(2026, 11, 9, 20, 0, tzinfo=dt_tz.utc)   # 01:30 IST on 10 Nov
        with mock.patch('django.utils.timezone.now', return_value=fake):
            TaskService.log_time(self.task, self.staff, date(2026, 11, 10), 30)
        self.assertEqual(TaskTimeLog.objects.count(), 1)

    def test_day_total_cannot_exceed_24h(self):
        today = timezone.localdate()
        TaskService.log_time(self.task, self.staff, today, 1000)
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            TaskService.log_time(self.task, self.staff, today, 500)

    def test_itr_due_date_from_fy_not_today(self):
        fy = FinancialYear.objects.get(firm=self.firm, label=f'{timezone.localdate().year - 2}-{str(timezone.localdate().year - 1)[-2:]}')
        due, _ = calculate_due_date({'kind': 'fixed_date', 'month': 7, 'day': 31}, fy=fy, today=timezone.localdate())
        self.assertEqual(due, date(fy.end_date.year, 7, 31))

    def test_tds_quarter_due_dates(self):
        rule = {'kind': 'per_period_sequence', 'dates': {'1': '07-31', '2': '10-31', '3': '01-31', '4': '05-31'}}
        fy = FinancialYear.objects.filter(firm=self.firm).order_by('start_date').first()
        quarters = {p.sequence: p for p in Period.objects.filter(fy=fy, kind='quarter')}
        y = fy.start_date.year
        self.assertEqual(calculate_due_date(rule, period=quarters[1])[0], date(y, 7, 31))
        self.assertEqual(calculate_due_date(rule, period=quarters[3])[0], date(y + 1, 1, 31))
        self.assertEqual(calculate_due_date(rule, period=quarters[4])[0], date(y + 1, 5, 31))

    def test_day_31_is_not_cut_to_28(self):
        p = Period.objects.filter(fy__firm=self.firm, kind='month', start_date__month=6).first()   # June -> July 31
        self.assertEqual(calculate_due_date({'kind': 'fixed_day_after_period_end', 'day': 31}, period=p)[0].day, 31)

    def test_fy_exists_for_next_year(self):
        nxt = timezone.localdate() + timedelta(days=370)
        self.assertTrue(FinancialYear.objects.filter(firm=self.firm, start_date__lte=nxt, end_date__gte=nxt).exists())

    def test_find_previous_period(self):
        today = date(2026, 11, 15)
        prev = find_period(self.firm, 'month', today, -1)
        self.assertEqual((prev.start_date.year, prev.start_date.month), (2026, 10))


class ValidatorTests(TestCase):
    def test_gstin_checksum(self):
        self.assertEqual(gstin_check_char('27AAPFU0939F1Z'), 'V')
        validate_gstin_format('27AAPFU0939F1ZV')
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_gstin_format('27AAPFU0939F1ZA')


class TaskCreatePermissionTests(PhaseABase):
    """Firm setting staff_can_create_task + per-user override User.can_create_tasks."""
    def _create(self, user):
        return self.api(user).post('/api/v1/tasks/', {
            'client': str(self.client_obj.id), 'task_type': str(self.tt.id),
            'period': str(Period.objects.filter(fy__firm=self.firm, kind='month').order_by('-start_date')[8].id),
        }, format='json')

    def test_matrix(self):
        self.firm.staff_can_create_task = False
        self.firm.save()
        self.assertEqual(self._create(self.staff).status_code, 403)          # firm off, no override
        self.staff.can_create_tasks = True
        self.staff.save()
        self.assertEqual(self._create(self.staff).status_code, 201)          # per-user allow wins
        self.firm.staff_can_create_task = True
        self.firm.save()
        self.other.can_create_tasks = False
        self.other.save()
        self.assertEqual(self._create(self.other).status_code, 403)          # per-user block wins

    def test_admin_can_set_override_and_me_reports_it(self):
        res = self.api(self.admin).patch(f'/api/v1/accounts/users/{self.staff.id}/', {'can_create_tasks': True}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['effective_can_create_tasks'])
        self.staff.refresh_from_db()   # force_authenticate keeps the in-memory object; a real request loads it fresh
        me = self.api(self.staff).get('/api/v1/auth/me/').data
        self.assertTrue(me['user']['effective_can_create_tasks'])
        res = self.api(self.admin).patch(f'/api/v1/accounts/users/{self.staff.id}/', {'can_create_tasks': None}, format='json')
        self.assertIsNone(res.data['can_create_tasks'])

    def test_staff_cannot_set_override(self):
        res = self.api(self.staff).patch(f'/api/v1/accounts/users/{self.staff.id}/', {'can_create_tasks': True}, format='json')
        self.assertEqual(res.status_code, 403)


class FirmSettingsTests(PhaseABase):
    def test_validation_and_superadmin_only(self):
        self.assertEqual(self.api(self.admin).patch('/api/v1/accounts/firm/', {'allow_pickup': False}, format='json').status_code, 403)
        self.assertEqual(self.api(self.superadmin).patch('/api/v1/accounts/firm/', {'long_due_days': 0}, format='json').status_code, 400)
        self.assertEqual(self.api(self.superadmin).patch('/api/v1/accounts/firm/', {'timezone': 'Mars/Base'}, format='json').status_code, 400)
        res = self.api(self.superadmin).patch('/api/v1/accounts/firm/', {'staff_can_create_task': True, 'long_due_days': 45}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['has_tasks'])

    def test_fy_start_month_locked_after_tasks(self):
        res = self.api(self.superadmin).patch('/api/v1/accounts/firm/', {'fy_start_month': 1}, format='json')
        self.assertEqual(res.status_code, 400)


class ComplianceCalendarTests(PhaseABase):
    def setUp(self):
        super().setUp()
        from apps.services.compliance import ensure_default_events
        ensure_default_events(self.firm)

    def _states_on(self, day):
        from apps.services.compliance import next_due_date, due_state
        out = []
        for d in range(day - 3, day + 2):
            today = date(2026, 11, d)
            due = next_due_date(7, [], today)
            out.append(due_state(due, today, 2)[0])
        return out

    def test_tds_7th_orange_on_5th_6th_red_on_7th(self):
        # 4th, 5th, 6th, 7th, 8th of the month
        self.assertEqual(self._states_on(7), ['normal', 'due_soon', 'due_soon', 'due_today', 'normal'])

    def test_day_31_in_30_day_month(self):
        from apps.services.compliance import next_due_date
        self.assertEqual(next_due_date(31, [9], date(2026, 9, 1)), date(2026, 9, 30))

    def test_staff_read_admin_write(self):
        self.assertEqual(self.api(self.staff).get('/api/v1/services/compliance-calendar/?active=true').status_code, 200)
        self.assertEqual(self.api(self.staff).post('/api/v1/services/compliance-calendar/', {}, format='json').status_code, 403)
        res = self.api(self.admin).post('/api/v1/services/compliance-calendar/', {
            'code': 'pt', 'title': 'Professional Tax', 'due_day': 30, 'due_months': [6]}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['code'], 'PT')
        self.assertEqual(res.data['due_text'], '30th Jun')
        rid = res.data['id']
        res = self.api(self.admin).patch(f'/api/v1/services/compliance-calendar/{rid}/', {'is_active': False}, format='json')
        self.assertFalse(res.data['is_active'])
        codes = [r['code'] for r in self.api(self.staff).get('/api/v1/services/compliance-calendar/?active=true').data]
        self.assertNotIn('PT', codes)
        self.assertEqual(self.api(self.admin).delete(f'/api/v1/services/compliance-calendar/{rid}/').status_code, 204)

    def test_bad_values_rejected(self):
        res = self.api(self.admin).post('/api/v1/services/compliance-calendar/', {
            'code': 'X', 'title': 'X', 'due_day': 32, 'due_months': [13]}, format='json')
        self.assertEqual(res.status_code, 400)


class FirmLogoTests(PhaseABase):
    def _png(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (40, 20), 'green').save(buf, 'PNG')
        buf.name = 'logo.png'
        buf.seek(0)
        return buf

    def test_upload_and_remove(self):
        import tempfile
        from django.test import override_settings
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            self.assertEqual(self.api(self.admin).post('/api/v1/accounts/firm/logo/', {'logo': self._png()}).status_code, 403)
            res = self.api(self.superadmin).post('/api/v1/accounts/firm/logo/', {'logo': self._png()})
            self.assertEqual(res.status_code, 200, res.data)
            self.assertTrue(res.data['logo_url'].startswith('/media/firm_logos/'))
            self.assertNotIn('logo.png', res.data['logo_url'])          # random name, not the upload name
            res = self.api(self.superadmin).delete('/api/v1/accounts/firm/logo/')
            self.assertIsNone(res.data['logo_url'])

    def test_fake_image_rejected(self):
        import io
        fake = io.BytesIO(b'MZ\x90\x00 this is an exe renamed to png')
        fake.name = 'evil.png'
        res = self.api(self.superadmin).post('/api/v1/accounts/firm/logo/', {'logo': fake})
        self.assertEqual(res.status_code, 400)
