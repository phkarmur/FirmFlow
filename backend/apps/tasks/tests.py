import io
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta, date
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.models import Firm, Branch, User
from apps.clients.models import Client
from apps.services.models import ServiceCategory, Service, TaskType, Milestone, TaskTypeTodoTemplate, PendingIssueLabel
from apps.periods.models import FinancialYear, Period
from apps.tasks.models import Task, TaskMember, TaskIssue, TaskMilestoneProgress, TaskAssignmentLog, TaskTimeLog, TaskComment
from apps.tasks.services.task_service import TaskService
from apps.tasks.importer import TaskSpreadsheetImporter
from apps.notifications.models import Notification

class TaskServiceLifecycleTests(TestCase):
    def setUp(self):
        self.firm = Firm.objects.create(name='Test CA Firm', allow_pickup=True, staff_can_create_task=False)
        self.branch = Branch.objects.create(firm=self.firm, name='HQ', code='HQ', is_default=True)
        self.admin = User.objects.create_user(email='admin@test.com', full_name='Admin User', firm=self.firm, system_role=User.Role.ADMIN)
        self.staff1 = User.objects.create_user(email='staff1@test.com', full_name='Staff One', firm=self.firm, system_role=User.Role.STAFF)
        self.staff2 = User.objects.create_user(email='staff2@test.com', full_name='Staff Two', firm=self.firm, system_role=User.Role.STAFF)

        self.client = Client.objects.create(firm=self.firm, name='Acme Ltd')
        self.client.set_pan('AABCA1234F')
        self.client.save()

        self.cat = ServiceCategory.objects.create(firm=self.firm, name='Taxation')
        self.svc = Service.objects.create(category=self.cat, name='GST')
        self.task_type = TaskType.objects.create(service=self.svc, name='GSTR-3B', code='GSTR3B', allow_out_of_order_milestones=False)

        # Milestone 1 & Terminal Milestone 2
        self.ms1 = Milestone.objects.create(
            task_type=self.task_type,
            name='Books Reconciled',
            sort_order=1,
            auto_resolve_issue_labels=['Bank statement pending']
        )
        self.ms2 = Milestone.objects.create(
            task_type=self.task_type,
            name='Filed on Portal',
            sort_order=2,
            is_terminal=True
        )

        # Mandatory Todo
        self.todo_tmpl = TaskTypeTodoTemplate.objects.create(
            task_type=self.task_type,
            text='Download 2B',
            is_mandatory=True,
            sort_order=1
        )

        self.label = PendingIssueLabel.objects.create(
            firm=self.firm,
            name='Bank statement pending',
            blocks_completion=True
        )

        # Phase A: tasks that require an FY need a current FY to exist
        from apps.periods.generator import generate_financial_years_for_firm
        generate_financial_years_for_firm(self.firm, start_calendar_year=timezone.localdate().year - 1)

        # Phase A: task actions need a task role. staff1 is the task LEADER in these tests
        # (the assigned user stays empty so the pickup tests still work).
        self.task = TaskService.create_task(
            firm=self.firm,
            branch=self.branch,
            client=self.client,
            task_type=self.task_type,
            creator=self.admin,
            leader_user=self.staff1,
            due_date=timezone.now().date() + timedelta(days=5)
        )

    def test_task_creation_populates_milestones_and_todos(self):
        self.assertTrue(self.task.task_number.startswith('FF-'))
        self.assertEqual(self.task.status, Task.Status.NOT_STARTED)
        self.assertEqual(self.task.milestone_progress.count(), 2)
        self.assertEqual(self.task.todos.count(), 1)
        self.assertTrue(self.task.todos.first().is_mandatory)

    def test_unassigned_pickup(self):
        self.assertIsNone(self.task.assigned_user)
        TaskService.pickup_task(self.task, self.staff1)
        self.task.refresh_from_db()
        self.assertEqual(self.task.assigned_user, self.staff1)
        log = self.task.assignment_logs.filter(trigger=TaskAssignmentLog.Trigger.PICKUP).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_user, self.staff1)

    def test_pickup_already_assigned_task_blocked(self):
        self.task.assigned_user = self.staff1
        self.task.save()

        # Staff 2 attempts to steal task assigned to Staff 1
        with self.assertRaises(ValidationError) as cm:
            TaskService.pickup_task(self.task, self.staff2)
        self.assertIn('already assigned', str(cm.exception.detail))

    def test_first_milestone_tick_moves_to_in_process_and_autoresolves_issue(self):
        issue = TaskIssue.objects.create(
            task=self.task,
            label=self.label,
            detail='Awaiting HDFC statement',
            raised_by=self.staff1
        )
        self.assertEqual(issue.status, TaskIssue.Status.OPEN)

        prog1 = self.task.milestone_progress.get(milestone=self.ms1)
        TaskService.tick_milestone(self.task, prog1, user=self.staff1)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROCESS)

        issue.refresh_from_db()
        self.assertEqual(issue.status, TaskIssue.Status.RESOLVED)

    def test_completion_blocked_if_mandatory_todo_open(self):
        with self.assertRaises(ValidationError) as cm:
            TaskService.update_status(self.task, Task.Status.COMPLETED, changed_by=self.admin)
        self.assertIn('completion_blocked', cm.exception.detail)

    def test_comment_mention_auto_adds_collaborator_and_notifies(self):
        self.assertFalse(self.task.members.filter(user=self.staff2).exists())
        TaskService.add_comment(
            task=self.task,
            user=self.staff1,
            body="Hey @staff2@test.com please verify the ITC mismatch",
            mentions=[]
        )
        # Auto-enrolled as TaskMember
        self.assertTrue(self.task.members.filter(user=self.staff2).exists())

        # Notification emitted
        notif = Notification.objects.filter(user=self.staff2, kind=Notification.Kind.MENTIONED).first()
        self.assertIsNotNone(notif)
        self.assertIn(self.task.task_number, notif.title)

    def test_comment_by_assigned_user_moves_task_to_in_process(self):
        self.task.assigned_user = self.staff1
        self.task.status = Task.Status.NOT_STARTED
        self.task.save()

        TaskService.add_comment(
            task=self.task,
            user=self.staff1,
            body="Starting work on books reconciliation"
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROCESS)

    def test_duplicate_mention_handled_cleanly(self):
        TaskService.add_comment(
            task=self.task,
            user=self.staff1,
            body="Checking @Staff Two and again @Staff Two",
            mentions=[str(self.staff2.id)]
        )
        # Should only have 1 TaskMember entry
        self.assertEqual(self.task.members.filter(user=self.staff2).count(), 1)

    def test_on_hold_requires_reason(self):
        with self.assertRaises(ValidationError):
            TaskService.update_status(self.task, Task.Status.ON_HOLD, changed_by=self.admin, on_hold_reason='')
        # With valid reason
        TaskService.update_status(self.task, Task.Status.ON_HOLD, changed_by=self.admin, on_hold_reason='Waiting for OTP')
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.ON_HOLD)
        self.assertEqual(self.task.on_hold_reason, 'Waiting for OTP')

    def test_out_of_order_milestones_blocked(self):
        prog2 = self.task.milestone_progress.get(milestone=self.ms2)
        with self.assertRaises(ValidationError) as cm:
            TaskService.tick_milestone(self.task, prog2, user=self.staff1)
        self.assertIn('milestone', cm.exception.detail)

    def test_reopen_completed_task_restricted_to_admin(self):
        # Complete all prerequisites
        todo = self.task.todos.first()
        todo.is_done = True
        todo.save()

        prog1 = self.task.milestone_progress.get(milestone=self.ms1)
        TaskService.tick_milestone(self.task, prog1, user=self.admin)
        prog2 = self.task.milestone_progress.get(milestone=self.ms2)
        TaskService.tick_milestone(self.task, prog2, user=self.admin)

        TaskService.update_status(self.task, Task.Status.COMPLETED, changed_by=self.admin)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.COMPLETED)

        # Staff attempts to reopen -> Blocked!
        with self.assertRaises(PermissionDenied):
            TaskService.update_status(self.task, Task.Status.IN_PROCESS, changed_by=self.staff1)

        # Admin reopens -> Allowed!
        TaskService.update_status(self.task, Task.Status.IN_PROCESS, changed_by=self.admin, reason='Revised filing needed')
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROCESS)
        self.assertIsNone(self.task.completed_at)

    def test_future_work_date_time_log_rejected(self):
        tomorrow = timezone.now().date() + timedelta(days=1)
        with self.assertRaises(ValidationError):
            TaskService.log_time(self.task, self.staff1, work_date=tomorrow, minutes=60)

    def test_invalid_minutes_time_log_rejected(self):
        today = timezone.now().date()
        with self.assertRaises(ValidationError):
            TaskService.log_time(self.task, self.staff1, work_date=today, minutes=0)
        with self.assertRaises(ValidationError):
            TaskService.log_time(self.task, self.staff1, work_date=today, minutes=2000)

    def test_first_time_log_moves_not_started_to_in_process(self):
        today = timezone.now().date()
        self.assertEqual(self.task.status, Task.Status.NOT_STARTED)
        TaskService.log_time(self.task, self.staff1, work_date=today, minutes=45, note='Initial data entry')
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROCESS)

    def test_time_log_24h_window_creator_allowed_within_24h(self):
        today = timezone.now().date()
        tlog = TaskService.log_time(self.task, self.staff1, work_date=today, minutes=60, note='Drafting return')

        client = APIClient()
        client.force_authenticate(user=self.staff1)

        # Update within 24h succeeds
        res = client.patch(f'/api/v1/tasks/time-logs/{tlog.id}/', {'minutes': 90, 'note': 'Updated notes'})
        self.assertEqual(res.status_code, 200)
        tlog.refresh_from_db()
        self.assertEqual(tlog.minutes, 90)

    def test_time_log_24h_window_creator_blocked_after_24h(self):
        today = timezone.now().date()
        tlog = TaskService.log_time(self.task, self.staff1, work_date=today, minutes=60, note='Old entry')

        # Backdate created_at to 2 days ago
        TaskTimeLog.objects.filter(id=tlog.id).update(created_at=timezone.now() - timedelta(days=2))

        client = APIClient()
        client.force_authenticate(user=self.staff1)

        # Staff edit after 24 hours -> 403 Forbidden!
        res_staff = client.patch(f'/api/v1/tasks/time-logs/{tlog.id}/', {'minutes': 120})
        self.assertEqual(res_staff.status_code, 403)
        self.assertIn('expired', res_staff.data['error'])

        # Admin override after 24 hours -> 200 OK!
        client.force_authenticate(user=self.admin)
        res_admin = client.patch(f'/api/v1/tasks/time-logs/{tlog.id}/', {'minutes': 120})
        self.assertEqual(res_admin.status_code, 200)
        tlog.refresh_from_db()
        self.assertEqual(tlog.minutes, 120)

    def test_staff_task_creation_firm_permission(self):
        client = APIClient()

        # 1. Firm has staff_can_create_task = False
        self.firm.staff_can_create_task = False
        self.firm.save()

        client.force_authenticate(user=self.staff1)
        res_blocked = client.post('/api/v1/tasks/', {
            'client': str(self.client.id),
            'task_type': str(self.task_type.id),
        })
        self.assertEqual(res_blocked.status_code, 403)

        # 2. Firm has staff_can_create_task = True
        self.firm.staff_can_create_task = True
        self.firm.save()

        res_allowed = client.post('/api/v1/tasks/', {
            'client': str(self.client.id),
            'task_type': str(self.task_type.id),
        })
        self.assertEqual(res_allowed.status_code, 201)

    def test_soft_delete_requires_admin_and_reason(self):
        client = APIClient()

        # Staff cannot delete task
        client.force_authenticate(user=self.staff1)
        res_staff = client.delete(f'/api/v1/tasks/{self.task.id}/', data={'reason': 'No longer needed'})
        self.assertEqual(res_staff.status_code, 403)

        # Admin delete without reason fails (400)
        client.force_authenticate(user=self.admin)
        res_no_reason = client.delete(f'/api/v1/tasks/{self.task.id}/', data={'reason': ''})
        self.assertEqual(res_no_reason.status_code, 400)

        # Admin delete with reason succeeds
        res_ok = client.delete(f'/api/v1/tasks/{self.task.id}/', data={'reason': 'Client cancelled registration'})
        self.assertEqual(res_ok.status_code, 200)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.DELETED)
        self.assertEqual(self.task.delete_reason, 'Client cancelled registration')
        self.assertEqual(self.task.deleted_by, self.admin)

        # Soft-deleted task is excluded from standard list query
        res_list = client.get('/api/v1/tasks/')
        task_ids = [t['id'] for t in res_list.data['results']]
        self.assertNotIn(str(self.task.id), task_ids)

    def test_task_sequence_counter_atomic(self):
        t1 = TaskService.create_task(self.firm, self.branch, self.client, self.task_type, self.admin, due_date=timezone.now().date())
        t2 = TaskService.create_task(self.firm, self.branch, self.client, self.task_type, self.admin, due_date=timezone.now().date())
        self.assertNotEqual(t1.task_number, t2.task_number)
        num1 = int(t1.task_number.split('-')[-1])
        num2 = int(t2.task_number.split('-')[-1])
        self.assertEqual(num2, num1 + 1)

    def test_optimistic_concurrency_locking(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        # Send stale version number (e.g. 99 instead of 1)
        response = client.patch(
            f'/api/v1/tasks/{self.task.id}/',
            data={'priority': 'high', 'version': 99},
            format='json'
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn('Conflict', response.data['error'])

    def test_task_create_api_endpoint_with_null_due_date_and_auto_fy(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        payload = {
            'client': str(self.client.id),
            'task_type': str(self.task_type.id),
            'period': None,
            'assigned_user': None,
            'due_date': None,
            'priority': 'normal'
        }
        response = client.post('/api/v1/tasks/', data=payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['task_number'].startswith('FF-'))
        self.assertIsNotNone(response.data['due_date'])
        self.assertEqual(response.data['status'], 'not_started')

    def test_task_spreadsheet_importer_valid_and_invalid(self):
        csv_content = """Client PAN,Task Type Code,Due Date,Priority,Assignee Email,Notes
AABCA1234F,GSTR3B,2026-12-20,high,staff1@test.com,Imported return
UNKNOWNPAN,GSTR3B,2026-12-20,normal,,Non-existent client
AABCA1234F,INVALID_TYPE,2026-12-20,normal,,Bad task type
"""
        file = SimpleUploadedFile("tasks.csv", csv_content.encode('utf-8'), content_type="text/csv")
        result = TaskSpreadsheetImporter.import_tasks(self.firm, file, user=self.admin)

        self.assertEqual(result['imported_count'], 1)
        self.assertEqual(len(result['errors']), 2)
        # Verify created task
        created_task = Task.objects.get(client=self.client, priority='high')
        self.assertEqual(created_task.assigned_user, self.staff1)

    def test_bulk_shift_due_date(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        new_date = str(timezone.now().date() + timedelta(days=20))
        res = client.post('/api/v1/tasks/bulk_shift_due_date/', {
            'task_type_id': str(self.task_type.id),
            'new_due_date': new_date,
            'reason': 'Statutory notification 12/2026'
        })
        self.assertEqual(res.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(str(self.task.due_date), new_date)
