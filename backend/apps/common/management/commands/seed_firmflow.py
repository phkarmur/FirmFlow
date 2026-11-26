from django.core.management.base import BaseCommand
from django.db import transaction
from apps.accounts.models import Firm, Branch, User, UserBranch
from apps.services.models import (
    ServiceCategory, Service, TaskType, TaskTypeTodoTemplate,
    Milestone, PendingIssueLabel
)
from apps.periods.generator import generate_financial_years_for_firm
from apps.clients.models import Client, ClientGroup, ClientContact

class Command(BaseCommand):
    help = 'Seeds initial FirmFlow starter data per §14 build specification.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Seeding FirmFlow initial practice data...'))

        # 1. Firm & Default Branch
        firm, created = Firm.objects.get_or_create(
            name='Shah & Associates CA Firm',
            defaults={
                'legal_name': 'Shah & Associates Chartered Accountants',
                'fy_start_month': 4,
                'timezone': 'Asia/Kolkata',
                'date_format': 'DD-MM-YYYY',
                'long_due_days': 30,
                'staff_can_create_task': False,
                'staff_can_complete': True,
                'allow_pickup': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created Firm: {firm.name}"))

        branch, _ = Branch.objects.get_or_create(
            firm=firm,
            code='HQ',
            defaults={'name': 'Main Office', 'is_default': True, 'is_active': True}
        )

        # 2. Superadmin & Staff Users
        superadmin, created = User.objects.get_or_create(
            email='admin@shahca.com',
            defaults={
                'full_name': 'CA Rajesh Shah',
                'firm': firm,
                'designation': 'Managing Partner',
                'system_role': User.Role.SUPERADMIN,
                'is_staff': True,
            }
        )
        if created:
            superadmin.set_password('Admin@123456')
            superadmin.save()
            UserBranch.objects.get_or_create(user=superadmin, branch=branch, is_default=True)
            self.stdout.write(self.style.SUCCESS(f"Created Superadmin: {superadmin.email} (Password: Admin@123456)"))

        # Create demo staff users
        staff_1, _ = User.objects.get_or_create(
            email='priya.verma@shahca.com',
            defaults={
                'full_name': 'Priya Verma',
                'firm': firm,
                'designation': 'Article Trainee',
                'system_role': User.Role.STAFF,
            }
        )
        staff_1.set_password('Staff@123456')
        staff_1.save()
        UserBranch.objects.get_or_create(user=staff_1, branch=branch, is_default=True)

        staff_2, _ = User.objects.get_or_create(
            email='amit.kumar@shahca.com',
            defaults={
                'full_name': 'Amit Kumar',
                'firm': firm,
                'designation': 'Senior Tax Associate',
                'system_role': User.Role.ADMIN,
            }
        )
        staff_2.set_password('Staff@123456')
        staff_2.save()
        UserBranch.objects.get_or_create(user=staff_2, branch=branch, is_default=True)

        # 3. Generate Financial Years & Periods (2004 to 2027)
        self.stdout.write(self.style.NOTICE('Generating Financial Years (2004 to current FY + 1)...'))
        generate_financial_years_for_firm(firm, start_calendar_year=2004)

        # 3b. Dashboard compliance calendar starter list (editable on the Settings page)
        from apps.services.compliance import ensure_default_events
        ensure_default_events(firm)

        # 4. Service Tree Starter (§14)
        services_data = [
            {
                'category': 'Taxation',
                'services': [
                    {
                        'name': 'GST',
                        'task_types': [
                            {
                                'name': 'GSTR-3B',
                                'code': 'GSTR3B',
                                'recurrence': TaskType.Recurrence.MONTHLY,
                                'period_kind': TaskType.PeriodKind.MONTH,
                                'default_due_rule': {'kind': 'fixed_day_after_period_end', 'day': 20},
                                'milestones': [
                                    ('Data received from client', False, []),
                                    ('Books reconciled with GSTR-2B', False, ['Bank statement pending']),
                                    ('Return prepared & tax computed', False, []),
                                    ('Partner review & client approval', False, ['Awaiting client confirmation']),
                                    ('Filed on GSTN portal (Challan generated)', True, ['Portal down', 'Login/OTP pending']),
                                ],
                                'todos': [
                                    ('Download GSTR-2B from portal', True),
                                    ('Reconcile purchase register with 2B', True),
                                    ('Check RCM liability on freight/legal', False),
                                    ('Generate payment challan if cash ledger insufficient', True),
                                    ('File via EVC / DSC', True),
                                ]
                            },
                            {
                                'name': 'GSTR-1',
                                'code': 'GSTR1',
                                'recurrence': TaskType.Recurrence.MONTHLY,
                                'period_kind': TaskType.PeriodKind.MONTH,
                                'default_due_rule': {'kind': 'fixed_day_after_period_end', 'day': 11},
                                'milestones': [
                                    ('Sales invoices received', False, []),
                                    ('B2B & B2C summary matched', False, []),
                                    ('Filed on GSTN portal', True, []),
                                ]
                            },
                            {
                                'name': 'GSTR-9 (Annual Return)',
                                'code': 'GSTR9',
                                'recurrence': TaskType.Recurrence.YEARLY,
                                'period_kind': TaskType.PeriodKind.YEAR,
                                'default_due_rule': {'kind': 'fixed_date', 'month': 12, 'day': 31},
                            },
                            {
                                'name': 'GST Registration',
                                'code': 'GSTREG',
                                'recurrence': TaskType.Recurrence.NONE,
                                'period_kind': TaskType.PeriodKind.NONE,
                                'requires_fy': False,
                                'requires_period': False,
                                'default_due_rule': {'kind': 'days_after_creation', 'days': 7},
                            }
                        ]
                    },
                    {
                        'name': 'Income Tax',
                        'task_types': [
                            {
                                'name': 'ITR Individual (Non-Audit)',
                                'code': 'ITR-IND',
                                'recurrence': TaskType.Recurrence.YEARLY,
                                'period_kind': TaskType.PeriodKind.YEAR,
                                'uses_assessment_year': True,
                                'default_due_rule': {'kind': 'fixed_date', 'month': 7, 'day': 31},
                                'milestones': [
                                    ('Form 26AS & AIS/TIS downloaded', False, []),
                                    ('Income computation prepared', False, []),
                                    ('Client confirmation & tax payment', False, []),
                                    ('ITR filed & e-verified', True, []),
                                ]
                            },
                            {
                                'name': 'ITR Audit (Corporate / Non-corporate)',
                                'code': 'ITR-AUDIT',
                                'recurrence': TaskType.Recurrence.YEARLY,
                                'period_kind': TaskType.PeriodKind.YEAR,
                                'uses_assessment_year': True,
                                'default_due_rule': {'kind': 'fixed_date', 'month': 10, 'day': 31},
                            },
                            {
                                'name': 'Tax Audit (3CA/3CB-3CD)',
                                'code': 'TAX-AUDIT',
                                'recurrence': TaskType.Recurrence.YEARLY,
                                'period_kind': TaskType.PeriodKind.YEAR,
                                'uses_assessment_year': True,
                                'default_due_rule': {'kind': 'fixed_date', 'month': 9, 'day': 30},
                            },
                            {
                                'name': 'Advance Tax Computation & Payment',
                                'code': 'ADV-TAX',
                                'recurrence': TaskType.Recurrence.QUARTERLY,
                                'period_kind': TaskType.PeriodKind.QUARTER,
                                'default_due_rule': {'kind': 'per_period_sequence', 'dates': {'1': '06-15', '2': '09-15', '3': '12-15', '4': '03-15'}},
                            }
                        ]
                    },
                    {
                        'name': 'TDS',
                        'task_types': [
                            {
                                'name': 'TDS Return 24Q (Salary)',
                                'code': 'TDS-24Q',
                                'recurrence': TaskType.Recurrence.QUARTERLY,
                                'period_kind': TaskType.PeriodKind.QUARTER,
                                'default_due_rule': {'kind': 'per_period_sequence', 'dates': {'1': '07-31', '2': '10-31', '3': '01-31', '4': '05-31'}},
                            },
                            {
                                'name': 'TDS Return 26Q (Non-Salary)',
                                'code': 'TDS-26Q',
                                'recurrence': TaskType.Recurrence.QUARTERLY,
                                'period_kind': TaskType.PeriodKind.QUARTER,
                                'default_due_rule': {'kind': 'per_period_sequence', 'dates': {'1': '07-31', '2': '10-31', '3': '01-31', '4': '05-31'}},
                            }
                        ]
                    }
                ]
            },
            {
                'category': 'Compliance',
                'services': [
                    {
                        'name': 'ROC / MCA',
                        'task_types': [
                            {
                                'name': 'AOC-4 (Financial Statements)',
                                'code': 'ROC-AOC4',
                                'recurrence': TaskType.Recurrence.YEARLY,
                                'period_kind': TaskType.PeriodKind.YEAR,
                                'default_due_rule': {'kind': 'days_after_creation', 'days': 30},
                            },
                            {
                                'name': 'MGT-7 (Annual Return)',
                                'code': 'ROC-MGT7',
                                'recurrence': TaskType.Recurrence.YEARLY,
                                'period_kind': TaskType.PeriodKind.YEAR,
                                'default_due_rule': {'kind': 'days_after_creation', 'days': 60},
                            },
                            {
                                'name': 'DIR-3 KYC',
                                'code': 'DIR3-KYC',
                                'recurrence': TaskType.Recurrence.YEARLY,
                                'period_kind': TaskType.PeriodKind.YEAR,
                                'default_due_rule': {'kind': 'fixed_date', 'month': 9, 'day': 30},
                            }
                        ]
                    }
                ]
            },
            {
                'category': 'Audit',
                'services': [
                    {
                        'name': 'Statutory Audit',
                        'task_types': [
                            {
                                'name': 'Statutory Financial Audit',
                                'code': 'STAT-AUDIT',
                                'recurrence': TaskType.Recurrence.YEARLY,
                                'period_kind': TaskType.PeriodKind.YEAR,
                                'default_due_rule': {'kind': 'fixed_date', 'month': 9, 'day': 30},
                            }
                        ]
                    }
                ]
            },
            {
                'category': 'Accounting',
                'services': [
                    {
                        'name': 'Bookkeeping & MIS',
                        'task_types': [
                            {
                                'name': 'Monthly Bookkeeping & Bank Reconciliation',
                                'code': 'ACC-MONTHLY',
                                'recurrence': TaskType.Recurrence.MONTHLY,
                                'period_kind': TaskType.PeriodKind.MONTH,
                                'default_due_rule': {'kind': 'fixed_day_after_period_end', 'day': 10},
                            }
                        ]
                    }
                ]
            }
        ]

        for cat_data in services_data:
            cat, _ = ServiceCategory.objects.get_or_create(firm=firm, name=cat_data['category'])
            for s_data in cat_data['services']:
                svc, _ = Service.objects.get_or_create(category=cat, name=s_data['name'])
                for tt_data in s_data['task_types']:
                    tt, _ = TaskType.objects.get_or_create(
                        service=svc,
                        name=tt_data['name'],
                        defaults={
                            'code': tt_data.get('code', ''),
                            'recurrence': tt_data.get('recurrence', TaskType.Recurrence.NONE),
                            'period_kind': tt_data.get('period_kind', TaskType.PeriodKind.MONTH),
                            'requires_fy': tt_data.get('requires_fy', True),
                            'requires_period': tt_data.get('requires_period', True),
                            'uses_assessment_year': tt_data.get('uses_assessment_year', False),
                            'default_due_rule': tt_data.get('default_due_rule', {}),
                        }
                    )
                    # Milestones
                    for idx, ms_item in enumerate(tt_data.get('milestones', []), start=1):
                        ms_name, is_terminal, auto_labels = ms_item
                        Milestone.objects.get_or_create(
                            task_type=tt,
                            name=ms_name,
                            defaults={
                                'sort_order': idx,
                                'is_terminal': is_terminal,
                                'auto_resolve_issue_labels': auto_labels,
                                'can_be_completed_by': ['assigned', 'leader', 'manager']
                            }
                        )
                    # Todos
                    for idx, (todo_text, is_mand) in enumerate(tt_data.get('todos', []), start=1):
                        TaskTypeTodoTemplate.objects.get_or_create(
                            task_type=tt,
                            text=todo_text,
                            defaults={'sort_order': idx, 'is_mandatory': is_mand}
                        )

        # 5. Pending Issue Labels (§14)
        starter_issue_labels = [
            ('Documents pending from client', True, True),
            ('Bank statement pending', True, True),
            ('Login OTP / Credentials not received', True, True),
            ('Fees / Outstanding pending', True, True),
            ('Awaiting client confirmation', True, True),
            ('Awaiting partner review', False, True),
            ('Government portal down', False, False),
        ]
        for label_name, is_client, blocks in starter_issue_labels:
            PendingIssueLabel.objects.get_or_create(
                firm=firm,
                name=label_name,
                defaults={'is_client_side': is_client, 'blocks_completion': blocks}
            )

        # 6. Starter Demo Clients
        demo_clients = [
            {
                'name': 'Apex Technologies Private Limited',
                'type': Client.ClientType.COMPANY,
                'pan': 'AABCA1234F',
                'gstin': '27AABCA1234F1Z9',
                'state_code': '27',
                'contact_name': 'Ramesh Mehra',
                'email': 'accounts@apextechnologies.example.com',
                'phone': '+91 9820012345',
            },
            {
                'name': 'Surat Textile Traders LLP',
                'type': Client.ClientType.LLP,
                'pan': 'AACCS9876K',
                'gstin': '24AACCS9876K1ZP',
                'state_code': '24',
                'contact_name': 'Hasmukh Patel',
                'email': 'hasmukh@surattextiles.example.com',
                'phone': '+91 9898098980',
            },
            {
                'name': 'Ananya Sharma',
                'type': Client.ClientType.INDIVIDUAL,
                'pan': 'AQZPS5544E',
                'gstin': '',
                'state_code': '07',
                'contact_name': 'Ananya Sharma',
                'email': 'ananya.sharma@example.com',
                'phone': '+91 9911002233',
            }
        ]

        for c_data in demo_clients:
            client, _ = Client.objects.get_or_create(
                firm=firm,
                name=c_data['name'],
                defaults={
                    'client_type': c_data['type'],
                    'gstin': c_data['gstin'],
                    'state_code': c_data['state_code'],
                    'email': c_data['email'],
                    'phone': c_data['phone'],
                }
            )
            client.set_pan(c_data['pan'])
            client.save()

            ClientContact.objects.get_or_create(
                client=client,
                name=c_data['contact_name'],
                defaults={
                    'email': c_data['email'],
                    'phone': c_data['phone'],
                    'is_primary': True,
                    'receives_task_emails': True
                }
            )

        self.stdout.write(self.style.SUCCESS('Successfully seeded FirmFlow starter database!'))
