from django.test import TestCase
from datetime import date
from apps.accounts.models import Firm, Branch, User
from apps.clients.models import Client
from apps.services.models import ServiceCategory, Service, TaskType
from apps.periods.models import FinancialYear, Period
from apps.bulk.models import BulkBatch, BulkBatchRun, BulkBatchRunItem
from apps.bulk.services import BulkBatchService
from apps.tasks.models import Task

class BulkBatchIdempotencyTests(TestCase):
    def setUp(self):
        self.firm = Firm.objects.create(name='Batch Practice Firm')
        self.branch = Branch.objects.create(firm=self.firm, name='HQ', code='HQ', is_default=True)
        self.admin = User.objects.create_user(email='batchadmin@firm.com', full_name='Admin Batch', firm=self.firm, system_role=User.Role.ADMIN)

        # Clients: 1 active, 1 inactive, 1 blocked
        self.client_active = Client.objects.create(firm=self.firm, name='Active Client Ltd', is_active=True)
        self.client_inactive = Client.objects.create(firm=self.firm, name='Inactive Client LLP', is_active=False)
        self.client_blocked = Client.objects.create(firm=self.firm, name='Blocked Fees Client', is_active=True, is_blocked_for_new_tasks=True)

        cat = ServiceCategory.objects.create(firm=self.firm, name='GST')
        svc = Service.objects.create(category=cat, name='Returns')
        self.task_type = TaskType.objects.create(service=svc, name='GSTR-3B', period_kind=TaskType.PeriodKind.MONTH)

        self.fy = FinancialYear.objects.create(firm=self.firm, label='2026-27', start_date=date(2026, 4, 1), end_date=date(2027, 3, 31))
        self.period = Period.objects.create(fy=self.fy, kind=Period.Kind.MONTH, label='May 2026', start_date=date(2026, 5, 1), end_date=date(2026, 5, 31), sequence=2)

        self.batch = BulkBatch.objects.create(
            firm=self.firm,
            branch=self.branch,
            name='Monthly GSTR-3B Batch',
            task_type=self.task_type,
            client_selection='all',
            created_by=self.admin
        )

    def test_preview_classifies_active_inactive_and_blocked(self):
        run = BulkBatchService.preview_batch_run(self.batch, self.fy, self.period, user=self.admin)
        self.assertEqual(run.status, BulkBatchRun.Status.PREVIEW)
        self.assertEqual(run.created_count, 1) # Only 1 active client will be created
        self.assertEqual(run.skipped_count, 2) # Inactive + Blocked skipped

        item_active = run.items.get(client=self.client_active)
        self.assertEqual(item_active.outcome, BulkBatchRunItem.Outcome.CREATED)

        item_inactive = run.items.get(client=self.client_inactive)
        self.assertEqual(item_inactive.outcome, BulkBatchRunItem.Outcome.SKIPPED_INACTIVE)

        item_blocked = run.items.get(client=self.client_blocked)
        self.assertEqual(item_blocked.outcome, BulkBatchRunItem.Outcome.SKIPPED_BLOCKED)

    def test_commit_creates_task_and_is_strictly_idempotent(self):
        # Run 1: Preview & Commit
        preview1 = BulkBatchService.preview_batch_run(self.batch, self.fy, self.period, user=self.admin)
        committed1 = BulkBatchService.commit_batch_run(preview1, user=self.admin)
        self.assertEqual(committed1.status, BulkBatchRun.Status.COMMITTED)
        self.assertEqual(committed1.created_count, 1)

        task_count = Task.objects.filter(client=self.client_active, task_type=self.task_type, period=self.period).count()
        self.assertEqual(task_count, 1)

        # Run 2: Running same batch for same period a second time (§5.5 B2 Idempotency)
        preview2 = BulkBatchService.preview_batch_run(self.batch, self.fy, self.period, user=self.admin)
        self.assertEqual(preview2.created_count, 0) # 0 to create
        self.assertEqual(preview2.skipped_count, 3) # All 3 skipped (1 duplicate, 1 inactive, 1 blocked)

        item_duplicate = preview2.items.get(client=self.client_active)
        self.assertEqual(item_duplicate.outcome, BulkBatchRunItem.Outcome.SKIPPED_DUPLICATE)

        committed2 = BulkBatchService.commit_batch_run(preview2, user=self.admin)
        self.assertEqual(committed2.created_count, 0)
        # Total tasks must remain exactly 1!
        self.assertEqual(Task.objects.filter(client=self.client_active, task_type=self.task_type, period=self.period).count(), 1)

    def test_bulk_batch_custom_client_selection(self):
        batch_custom = BulkBatch.objects.create(
            firm=self.firm,
            branch=self.branch,
            name='Specific Clients Batch',
            task_type=self.task_type,
            client_selection=f"list:[{self.client_active.id}]",
            created_by=self.admin
        )
        run = BulkBatchService.preview_batch_run(batch_custom, self.fy, self.period, user=self.admin)
        self.assertEqual(run.items.count(), 1)
        self.assertEqual(run.items.first().client, self.client_active)

    def test_bulk_batch_api_endpoints(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.admin)

        # 1. Preview action
        res_prev = client.post(f'/api/v1/bulk/batches/{self.batch.id}/preview/', {
            'fy_id': str(self.fy.id),
            'period_id': str(self.period.id)
        })
        self.assertEqual(res_prev.status_code, 201)
        run_id = res_prev.data['id']
        self.assertEqual(res_prev.data['status'], 'preview')

        # 2. Commit action
        res_com = client.post(f'/api/v1/bulk/batches/{self.batch.id}/commit/', {
            'run_id': run_id
        })
        self.assertEqual(res_com.status_code, 200)
        self.assertEqual(res_com.data['status'], 'committed')
