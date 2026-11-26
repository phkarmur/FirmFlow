"""Phase B2 tests: bulk actions, export, new reports, audit log, service tree, batches, client summary."""
from apps.tasks.models import Task
from apps.tasks.services.task_service import TaskService
from apps.tasks.tests_phase_a import PhaseABase
from apps.periods.models import Period


class BulkAndExportTests(PhaseABase):
    def setUp(self):
        super().setUp()
        p2 = Period.objects.filter(fy__firm=self.firm, kind='month').order_by('-start_date')[6]
        self.t2 = TaskService.create_task(self.firm, self.branch, self.client_obj, self.tt, self.admin, period=p2, assigned_user=self.staff)

    def test_bulk_assign_priority_due_delete(self):
        url = '/api/v1/tasks/bulk_action/'
        ids = [str(self.task.id), str(self.t2.id)]
        self.assertEqual(self.api(self.staff).post(url, {'ids': ids, 'action': 'priority', 'value': 'high'}, format='json').status_code, 403)
        res = self.api(self.admin).post(url, {'ids': ids, 'action': 'assign', 'value': str(self.other.id), 'reason': 'leave'}, format='json')
        self.assertEqual(res.data['done'], 2, res.data)
        res = self.api(self.admin).post(url, {'ids': ids, 'action': 'priority', 'value': 'high'}, format='json')
        self.assertEqual(res.data['done'], 2)
        res = self.api(self.admin).post(url, {'ids': ids, 'action': 'due_date', 'value': '2030-01-31', 'reason': 'ext'}, format='json')
        self.assertEqual(res.data['done'], 2)
        self.assertEqual(Task.objects.filter(priority='high', assigned_user=self.other, due_date='2030-01-31').count(), 2)
        res = self.api(self.admin).post(url, {'ids': ids, 'action': 'delete', 'reason': 'dup'}, format='json')
        self.assertEqual(res.data['done'], 2)

    def test_export_csv_and_xlsx_respect_visibility(self):
        res = self.api(self.admin).get('/api/v1/tasks/export/?format_type=csv')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content.decode().count('\n'), 3)        # header + 2 rows
        res = self.api(self.other).get('/api/v1/tasks/export/?format_type=csv')
        self.assertEqual(res.content.decode().count('\n'), 1)        # no role -> only header
        res = self.api(self.admin).get('/api/v1/tasks/export/?format_type=xlsx')
        self.assertTrue(res.content.startswith(b'PK'))


class NewReportTests(PhaseABase):
    def test_reports_run(self):
        for url in ['/api/v1/reports/service-staff/', '/api/v1/reports/issues/', '/api/v1/reports/performers/?metric=hours',
                    '/api/v1/reports/audit-log/', '/api/v1/reports/clients/', '/api/v1/reports/timelogs/']:
            res = self.api(self.admin).get(url)
            self.assertEqual(res.status_code, 200, url)
        grid = self.api(self.admin).get('/api/v1/reports/service-staff/').data
        self.assertEqual(grid['grid'][grid['services'][0]['id']][str(self.staff.id)], 1)
        audit = self.api(self.admin).get('/api/v1/reports/audit-log/?action=task.create').data
        self.assertGreaterEqual(audit['count'], 1)
        self.assertEqual(self.api(self.staff).get('/api/v1/reports/audit-log/').status_code, 403)
        # "Who" filter: options list, filter by one person, system entries, bad id
        self.assertIn('actors', audit)
        self.assertNotIn('Details', str(audit.get('results', [])[:1]))
        for opt in audit['actors']:
            res = self.api(self.admin).get(f"/api/v1/reports/audit-log/?actor={opt['id']}").data
            self.assertGreaterEqual(res['count'], 1, opt)
        self.assertEqual(self.api(self.admin).get('/api/v1/reports/audit-log/?actor=not-a-uuid').status_code, 400)


class ServiceTreeTests(PhaseABase):
    def test_due_rule_validation_and_reorder(self):
        url = f'/api/v1/services/task-types/{self.tt.id}/'
        bad = self.api(self.admin).patch(url, {'default_due_rule': {'kind': 'fixed_date', 'month': 13, 'day': 1}}, format='json')
        self.assertEqual(bad.status_code, 400)
        ok = self.api(self.admin).patch(url, {'default_due_rule': {'kind': 'fixed_date', 'month': 7, 'day': 31}}, format='json')
        self.assertEqual(ok.status_code, 200, ok.data)
        from apps.services.models import Milestone
        a = Milestone.objects.create(task_type=self.tt, name='A', sort_order=1)
        b = Milestone.objects.create(task_type=self.tt, name='B', sort_order=2)
        res = self.api(self.admin).post(f'{url}reorder_milestones/', {'ids': [str(b.id), str(a.id)]}, format='json')
        self.assertEqual([m['name'] for m in res.data['milestones']], ['B', 'A'])
        self.assertEqual(self.api(self.staff).post(f'{url}reorder_milestones/', {'ids': []}, format='json').status_code, 403)


class BatchAndClientTests(PhaseABase):
    def test_batch_flow_and_next_run(self):
        res = self.api(self.admin).post('/api/v1/bulk/batches/', {
            'name': '3B monthly', 'task_type': str(self.tt.id), 'client_selection': 'all',
            'schedule': {'day_of_month': 1, 'period_offset': -1}}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIsNotNone(res.data['next_run_date'])
        bid = res.data['id']
        period = Period.objects.filter(fy__firm=self.firm, kind='month').order_by('-start_date')[7]
        prev = self.api(self.admin).post(f'/api/v1/bulk/batches/{bid}/preview/', {'period_id': str(period.id)}, format='json')
        self.assertEqual(prev.data['created_count'], 1)
        com = self.api(self.admin).post(f'/api/v1/bulk/batches/{bid}/commit/', {'run_id': prev.data['id']}, format='json')
        self.assertEqual(com.data['created_count'], 1)
        det = self.api(self.admin).get(f'/api/v1/bulk/batches/{bid}/run_detail/?run_id={prev.data["id"]}')
        self.assertEqual(det.data['items'][0]['outcome'], 'created')

    def test_client_summary(self):
        res = self.api(self.admin).get(f'/api/v1/clients/{self.client_obj.id}/summary/')
        self.assertEqual(res.data['open_tasks'], 1)
