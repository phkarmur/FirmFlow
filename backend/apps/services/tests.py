from django.test import TestCase
from datetime import date
from rest_framework.test import APIClient
from apps.accounts.models import Firm, User
from apps.services.models import (
    ServiceCategory, Service, TaskType, Milestone,
    TaskTypeTodoTemplate, PendingIssueLabel
)
from apps.periods.models import FinancialYear, Period
from apps.tasks.services.task_service import TaskService

class ServicesAndDueDateCalculatorTests(TestCase):
    def setUp(self):
        self.firm = Firm.objects.create(name='Services CA Firm')
        self.admin = User.objects.create_user(email='admin@services.com', firm=self.firm, system_role=User.Role.ADMIN)

        self.cat = ServiceCategory.objects.create(firm=self.firm, name='Taxation')
        self.svc = Service.objects.create(category=self.cat, name='Goods & Services Tax')
        self.task_type = TaskType.objects.create(
            service=self.svc,
            name='GSTR-3B Monthly Return',
            code='GSTR3B',
            period_kind=TaskType.PeriodKind.MONTH
        )

        self.fy = FinancialYear.objects.create(
            firm=self.firm,
            label='2026-27',
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31)
        )
        self.period_apr = Period.objects.create(
            fy=self.fy,
            kind=Period.Kind.MONTH,
            label='Apr 2026',
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
            sequence=1
        )
        self.period_dec = Period.objects.create(
            fy=self.fy,
            kind=Period.Kind.MONTH,
            label='Dec 2026',
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 31),
            sequence=9
        )

    def test_service_tree_hierarchy_and_breadcrumbs(self):
        self.assertEqual(self.task_type.service.category.name, 'Taxation')
        self.assertEqual(self.task_type.service.name, 'Goods & Services Tax')
        self.assertEqual(self.task_type.name, 'GSTR-3B Monthly Return')

        # Test API flat_list action
        client = APIClient()
        client.force_authenticate(user=self.admin)
        res = client.get('/api/v1/services/task-types/flat_list/')
        self.assertEqual(res.status_code, 200)
        found = next((t for t in res.data if str(t['id']) == str(self.task_type.id)), None)
        self.assertIsNotNone(found)
        self.assertIn('Taxation', found['full_name'])
        self.assertIn('GSTR-3B', found['full_name'])

    def test_due_date_calc_fixed_day_after_period_end(self):
        # 20th of the following month
        self.task_type.default_due_rule = {'kind': 'fixed_day_after_period_end', 'day': 20}
        self.task_type.save()

        # April period (ends Apr 30) -> Due May 20
        due_apr = TaskService.calculate_default_due_date(self.task_type, self.period_apr)
        self.assertEqual(due_apr, date(2026, 5, 20))

        # December period (ends Dec 31) -> Rolls over to Jan 20 of next year!
        due_dec = TaskService.calculate_default_due_date(self.task_type, self.period_dec)
        self.assertEqual(due_dec, date(2027, 1, 20))

    def test_due_date_calc_fixed_date_annual(self):
        # E.g. ITR non-audit: July 31
        self.task_type.default_due_rule = {'kind': 'fixed_date', 'month': 7, 'day': 31}
        self.task_type.save()

        # If today is June 1, 2026 -> Due July 31, 2026
        ref1 = date(2026, 6, 1)
        due1 = TaskService.calculate_default_due_date(self.task_type, reference_date=ref1)
        self.assertEqual(due1, date(2026, 7, 31))

        # If today is August 10, 2026 -> Due July 31, 2027 of next year
        ref2 = date(2026, 8, 10)
        due2 = TaskService.calculate_default_due_date(self.task_type, reference_date=ref2)
        self.assertEqual(due2, date(2027, 7, 31))

    def test_due_date_calc_days_after_creation(self):
        self.task_type.default_due_rule = {'kind': 'days_after_creation', 'days': 15}
        self.task_type.save()

        today = date(2026, 6, 1)
        due = TaskService.calculate_default_due_date(self.task_type, reference_date=today)
        self.assertEqual(due, date(2026, 6, 16))

    def test_milestones_and_todo_templates(self):
        m1 = Milestone.objects.create(task_type=self.task_type, name='Preparation', sort_order=1)
        m2 = Milestone.objects.create(task_type=self.task_type, name='Approval', sort_order=2)
        m3 = Milestone.objects.create(task_type=self.task_type, name='Filing', sort_order=3, is_terminal=True)

        self.assertEqual(self.task_type.milestones.count(), 3)
        self.assertTrue(m3.is_terminal)

        todo = TaskTypeTodoTemplate.objects.create(
            task_type=self.task_type,
            text='Verify 2B mismatch on GST portal',
            is_mandatory=True,
            sort_order=1
        )
        self.assertEqual(self.task_type.todo_templates.count(), 1)
        self.assertTrue(todo.is_mandatory)

    def test_pending_issue_labels_flags(self):
        label_client = PendingIssueLabel.objects.create(
            firm=self.firm,
            name='Waiting for client purchase register',
            is_client_side=True,
            blocks_completion=True
        )
        self.assertTrue(label_client.is_client_side)
        self.assertTrue(label_client.blocks_completion)

        label_internal = PendingIssueLabel.objects.create(
            firm=self.firm,
            name='Internal Partner Review Required',
            is_client_side=False,
            blocks_completion=False
        )
        self.assertFalse(label_internal.is_client_side)
        self.assertFalse(label_internal.blocks_completion)
