import io
import csv
from datetime import datetime, date
import openpyxl
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from apps.tasks.models import Task
from apps.tasks.services.task_service import TaskService
from apps.clients.models import Client
from apps.services.models import TaskType
from apps.periods.models import Period, FinancialYear
from apps.accounts.models import User, Firm
from apps.common.models import AuditLog

class TaskSpreadsheetImporter:
    """
    Imports compliance tasks from CSV or XLSX (§5.5 B5).
    Resolves client by PAN or Name, task type by Code or Name, and period by Label.
    """

    @classmethod
    def parse_file(cls, uploaded_file):
        name = uploaded_file.name.lower()
        rows = []
        if name.endswith('.csv'):
            decoded = uploaded_file.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(decoded))
            for r in reader:
                rows.append({k.strip(): (v.strip() if v else '') for k, v in r.items() if k})
        elif name.endswith(('.xlsx', '.xls')):
            wb = openpyxl.load_workbook(uploaded_file, data_only=True)
            sheet = wb.active
            headers = [str(cell.value or '').strip() for cell in sheet[1]]
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not any(row):
                    continue
                row_dict = {}
                for idx, val in enumerate(row):
                    if idx < len(headers) and headers[idx]:
                        row_dict[headers[idx]] = str(val or '').strip()
                rows.append(row_dict)
        else:
            raise ValidationError('File format not supported. Please upload a .csv or .xlsx file.')
        return rows

    @classmethod
    def import_tasks(cls, firm: Firm, uploaded_file, user=None):
        rows = cls.parse_file(uploaded_file)
        created_tasks = []
        errors = []
        branch = firm.branches.filter(is_default=True).first() or firm.branches.first()

        for row_num, row in enumerate(rows, start=2):
            client_ref = row.get('Client PAN') or row.get('Client Name') or row.get('Client')
            task_type_ref = row.get('Task Type Code') or row.get('Task Type') or row.get('Service')
            period_label = row.get('Period') or row.get('Period Label') or ''
            raw_due_date = row.get('Due Date') or row.get('Due') or ''
            priority = (row.get('Priority') or 'normal').lower()
            assignee_email = row.get('Assignee Email') or row.get('Assignee') or ''

            if not client_ref:
                errors.append({'row': row_num, 'error': 'Missing Client PAN or Name.'})
                continue
            if not task_type_ref:
                errors.append({'row': row_num, 'error': 'Missing Task Type code or name.'})
                continue

            # 1. Resolve Client
            client = None
            if len(client_ref) == 10 and client_ref[:5].isalpha():
                from apps.common.crypto import mask_pan
                masked_candidate = mask_pan(client_ref)
                candidates = Client.objects.filter(firm=firm, pan_masked=masked_candidate)
                for c in candidates:
                    if c.get_pan_decrypted() == client_ref.strip().upper():
                        client = c
                        break

            if not client:
                client = Client.objects.filter(firm=firm, pan_masked__iexact=client_ref).first()
            if not client:
                client = Client.objects.filter(firm=firm, name__iexact=client_ref).first()
            if not client:
                errors.append({'row': row_num, 'error': f"Client not found for '{client_ref}'."})
                continue

            # 2. Resolve Task Type
            tt = TaskType.objects.filter(service__category__firm=firm, code__iexact=task_type_ref).first()
            if not tt:
                tt = TaskType.objects.filter(service__category__firm=firm, name__iexact=task_type_ref).first()
            if not tt:
                errors.append({'row': row_num, 'error': f"Task Type not found for '{task_type_ref}'."})
                continue

            # 3. Resolve Period
            period = None
            fy = None
            if period_label:
                period = Period.objects.filter(fy__firm=firm, label__iexact=period_label).first()
                if period:
                    fy = period.fy
            if not fy:
                fy = FinancialYear.objects.filter(firm=firm).order_by('-start_date').first()

            # 4. Parse Due Date
            due_date = None
            if raw_due_date:
                for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
                    try:
                        due_date = datetime.strptime(raw_due_date, fmt).date()
                        break
                    except ValueError:
                        pass

            # 5. Resolve Assignee
            assigned_user = None
            if assignee_email:
                assigned_user = User.objects.filter(firm=firm, email__iexact=assignee_email).first()

            # Create Task
            try:
                task = TaskService.create_task(
                    firm=firm,
                    branch=branch,
                    client=client,
                    task_type=tt,
                    creator=user,
                    fy=fy,
                    period=period,
                    due_date=due_date,
                    priority=priority if priority in ['normal', 'high'] else 'normal',
                    assigned_user=assigned_user,
                    source=Task.Source.IMPORT
                )
                created_tasks.append(task.task_number)
            except Exception as e:
                errors.append({'row': row_num, 'error': str(e)})

        AuditLog.log(
            firm_id=firm.id,
            action='task.bulk_import',
            entity_type='Task',
            entity_id=str(firm.id),
            actor_user_id=user.id if user else None,
            new_value={'imported_count': len(created_tasks), 'error_count': len(errors)}
        )

        return {
            'imported_count': len(created_tasks),
            'tasks': created_tasks,
            'errors': errors,
        }

    @classmethod
    def generate_template_csv(cls):
        """Generates starter template CSV for task import."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Client Name', 'Client PAN', 'Task Type Code', 'Period', 'Due Date', 'Priority', 'Assignee Email'])
        writer.writerow(['Apex Technologies Private Limited', 'AABCA1234F', 'GSTR3B', 'Apr 2026', '2026-05-20', 'normal', 'priya.verma@shahca.com'])
        writer.writerow(['Ananya Sharma', '', 'ITR-IND', 'FY 2025-26', '2026-07-31', 'high', ''])
        return output.getvalue()
