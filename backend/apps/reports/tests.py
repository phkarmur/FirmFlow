from django.test import TestCase
from datetime import timedelta, date
from django.utils import timezone
from rest_framework.test import APIClient
from apps.accounts.models import Firm, Branch, User
from apps.clients.models import Client
from apps.services.models import ServiceCategory, Service, TaskType, PendingIssueLabel
from apps.tasks.models import Task, TaskIssue, TaskTimeLog

class ReportsAccuracyTests(TestCase):
    def setUp(self):
        self.firm = Firm.objects.create(name='Reporting CA Firm', long_due_days=30)
        self.branch = Branch.objects.create(firm=self.firm, name='HQ', code='HQ', is_default=True)
        self.admin = User.objects.create_user(email='reportadmin@firm.com', full_name='Admin User', firm=self.firm, system_role=User.Role.ADMIN)
        self.staff = User.objects.create_user(email='staff@firm.com', full_name='Staff User', firm=self.firm, system_role=User.Role.STAFF)
        self.inactive_staff = User.objects.create_user(email='left@firm.com', full_name='Former Staff', firm=self.firm, is_active=False, system_role=User.Role.STAFF)

        self.client = Client.objects.create(firm=self.firm, name='Acme Client')
        self.client.set_pan('AABCA1234F')
        self.client.save()

        cat = ServiceCategory.objects.create(firm=self.firm, name='Audit')
        svc = Service.objects.create(category=cat, name='Internal')
        self.task_type = TaskType.objects.create(service=svc, name='Monthly Review', code='REV')

        today = timezone.now().date()
        # Task 1: Overdue
        self.t1 = Task.objects.create(
            firm=self.firm, branch=self.branch, client=self.client, task_type=self.task_type,
            task_type_name_snapshot='Monthly Review', task_number='FF-2026-000001',
            title='Task Overdue', due_date=today - timedelta(days=2), status=Task.Status.IN_PROCESS,
            assigned_user=self.staff
        )
        # Task 2: Due Today
        self.t2 = Task.objects.create(
            firm=self.firm, branch=self.branch, client=self.client, task_type=self.task_type,
            task_type_name_snapshot='Monthly Review', task_number='FF-2026-000002',
            title='Task Due Today', due_date=today, status=Task.Status.NOT_STARTED,
            assigned_user=self.staff
        )
        # Task 3: Unassigned in Pool
        self.t3 = Task.objects.create(
            firm=self.firm, branch=self.branch, client=self.client, task_type=self.task_type,
            task_type_name_snapshot='Monthly Review', task_number='FF-2026-000003',
            title='Task In Pool', due_date=today + timedelta(days=5), status=Task.Status.NOT_STARTED,
            assigned_user=None
        )
        # Task 4: Completed
        self.t4 = Task.objects.create(
            firm=self.firm, branch=self.branch, client=self.client, task_type=self.task_type,
            task_type_name_snapshot='Monthly Review', task_number='FF-2026-000004',
            title='Task Completed', due_date=today - timedelta(days=5), status=Task.Status.COMPLETED,
            completed_at=timezone.now(), assigned_user=self.staff
        )
        # Task 5: Assigned to inactive staff
        self.t5 = Task.objects.create(
            firm=self.firm, branch=self.branch, client=self.client, task_type=self.task_type,
            task_type_name_snapshot='Monthly Review', task_number='FF-2026-000005',
            title='Orphaned Task', due_date=today + timedelta(days=2), status=Task.Status.IN_PROCESS,
            assigned_user=self.inactive_staff
        )
        # Task 6: Soft-deleted task
        self.t6 = Task.objects.create(
            firm=self.firm, branch=self.branch, client=self.client, task_type=self.task_type,
            task_type_name_snapshot='Monthly Review', task_number='FF-2026-000006',
            title='Deleted Task', due_date=today, status=Task.Status.DELETED,
            deleted_at=timezone.now(), deleted_by=self.admin, delete_reason='Duplicate entry'
        )

        # Log some time
        TaskTimeLog.objects.create(
            task=self.t1,
            user=self.staff,
            work_date=today,
            minutes=120,
            note='Audit fieldwork'
        )

    def test_office_dashboard_counts_match_exact_lists(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        # 1. Fetch Dashboard Tile Counts
        res_stats = client.get('/api/v1/reports/dashboard/office/')
        self.assertEqual(res_stats.status_code, 200)
        stats = res_stats.data

        # 2. Check Overdue tile matches list
        res_overdue = client.get('/api/v1/tasks/?date_filter=overdue')
        self.assertEqual(stats['overdue'], res_overdue.data['count'])

        # 3. Check Due Today tile matches list
        res_due_today = client.get('/api/v1/tasks/?date_filter=due_today')
        self.assertEqual(stats['due_today'], res_due_today.data['count'])

        # 4. Check Unassigned Pool tile matches list
        res_pool = client.get('/api/v1/tasks/?unassigned=true')
        self.assertEqual(stats['unassigned_pool'], res_pool.data['count'])

        # 5. Check Completed tile matches list
        res_completed = client.get('/api/v1/tasks/?status=completed')
        self.assertEqual(stats['completed'], res_completed.data['count'])

    def test_my_dashboard_counts(self):
        client = APIClient()
        client.force_authenticate(user=self.staff)

        res = client.get('/api/v1/reports/dashboard/my/')
        self.assertEqual(res.status_code, 200)
        # Staff has t1 (in_process, overdue), t2 (not_started, due_today), t4 (completed)
        self.assertEqual(res.data['my_pending'], 2)
        self.assertEqual(res.data['my_due_today'], 1)
        self.assertEqual(res.data['my_overdue'], 1)
        self.assertEqual(res.data['my_completed_this_month'], 1)

    def test_employee_workload_report_grid_and_csv(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        # JSON response
        res = client.get('/api/v1/reports/employees/')
        self.assertEqual(res.status_code, 200)

        staff_row = next((r for r in res.data if r['user_id'] == self.staff.id), None)
        self.assertIsNotNone(staff_row)
        self.assertEqual(staff_row['pending'], 2)
        self.assertEqual(staff_row['overdue'], 1)
        self.assertEqual(staff_row['due_today'], 1)

        # CSV export
        res_csv = client.get('/api/v1/reports/employees/?export=csv')
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv['Content-Type'], 'text/csv')
        self.assertIn('Staff Name', str(res_csv.content))

    def test_timelog_report_aggregation(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        res = client.get('/api/v1/reports/timelogs/')
        self.assertEqual(res.status_code, 200)
        # Phase B2: list reports are paged -> {'count', 'results', ...}
        self.assertTrue(len(res.data['results']) >= 1)

    def test_inactive_staff_tasks_report(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        res = client.get('/api/v1/reports/inactive-staff-tasks/')
        self.assertEqual(res.status_code, 200)
        # t5 is assigned to inactive staff
        found = next((t for t in res.data['results'] if t['task_number'] == self.t5.task_number), None)
        self.assertIsNotNone(found)

    def test_client_wise_report(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        res = client.get('/api/v1/reports/clients/')
        self.assertEqual(res.status_code, 200)
        client_row = next((r for r in res.data['results'] if r['client_name'] == self.client.name), None)
        self.assertIsNotNone(client_row)
        self.assertTrue(client_row['total_tasks'] >= 4)

    def test_task_type_breakdown_report(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        res = client.get('/api/v1/reports/task-types/')
        self.assertEqual(res.status_code, 200)
        tt_row = next((r for r in res.data if r['code'] == self.task_type.code), None)
        self.assertIsNotNone(tt_row)
        self.assertTrue(tt_row['total'] >= 4)

    def test_deleted_tasks_report(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        res = client.get('/api/v1/reports/deleted/')
        self.assertEqual(res.status_code, 200)
        deleted_row = next((r for r in res.data['results'] if r['task_number'] == self.t6.task_number), None)
        self.assertIsNotNone(deleted_row)
        self.assertEqual(deleted_row['delete_reason'], 'Duplicate entry')

    def test_task_activity_report(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        res = client.get('/api/v1/reports/activity/')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['created_count'] >= 5)
        self.assertTrue(res.data['completed_count'] >= 1)
        self.assertTrue(res.data['deleted_count'] >= 1)
