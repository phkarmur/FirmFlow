from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import Firm, Branch, User, UserBranch
from apps.clients.models import Client
from apps.services.models import ServiceCategory, Service, TaskType
from apps.tasks.models import Task

class AccountsSecurityAndRulesTests(TestCase):
    def setUp(self):
        self.firm = Firm.objects.create(name='Global CA Partners')
        self.branch = Branch.objects.create(firm=self.firm, name='HQ', code='HQ', is_default=True)
        self.branch2 = Branch.objects.create(firm=self.firm, name='Sub-Office', code='SUB', is_default=False)
        self.superadmin = User.objects.create_user(
            email='super@firm.com', password='Password@123',
            full_name='Super Partner', firm=self.firm, system_role=User.Role.SUPERADMIN
        )
        self.admin = User.objects.create_user(
            email='admin@firm.com', password='Password@123',
            full_name='Admin User', firm=self.firm, system_role=User.Role.ADMIN
        )
        self.staff = User.objects.create_user(
            email='staff@firm.com', password='Password@123',
            full_name='Staff Member', firm=self.firm, system_role=User.Role.STAFF, designation='Associate'
        )

        # Another firm for multi-tenancy tests
        self.other_firm = Firm.objects.create(name='Rival CA & Co')
        self.other_user = User.objects.create_user(
            email='other@rival.com', password='Password@123',
            full_name='Other Firm User', firm=self.other_firm, system_role=User.Role.STAFF
        )

        self.client = Client.objects.create(firm=self.firm, name='Demo Client')
        cat = ServiceCategory.objects.create(firm=self.firm, name='Tax')
        svc = Service.objects.create(category=cat, name='GST')
        self.task_type = TaskType.objects.create(service=svc, name='GSTR-3B')

    def test_user_deactivation_blocked_if_open_tasks_assigned(self):
        Task.objects.create(
            firm=self.firm,
            branch=self.branch,
            client=self.client,
            task_type=self.task_type,
            task_type_name_snapshot=self.task_type.name,
            task_number='FF-2026-000101',
            title='Open Task for Staff',
            due_date='2026-12-31',
            assigned_user=self.staff,
            status=Task.Status.IN_PROCESS
        )

        client = APIClient()
        client.force_authenticate(user=self.superadmin)

        # Attempt to deactivate staff member -> Must fail!
        res = client.patch(f'/api/v1/accounts/users/{self.staff.id}/', {'is_active': False})
        self.assertEqual(res.status_code, 400)
        self.assertIn('open assigned tasks', str(res.data))

        # Re-assign or complete task, then deactivation succeeds
        Task.objects.filter(assigned_user=self.staff).update(status=Task.Status.COMPLETED)
        res_ok = client.patch(f'/api/v1/accounts/users/{self.staff.id}/', {'is_active': False})
        self.assertEqual(res_ok.status_code, 200)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)
        self.assertIsNotNone(self.staff.left_on)

    def test_cannot_deactivate_or_demote_last_superadmin(self):
        client = APIClient()
        client.force_authenticate(user=self.superadmin)

        # Attempt to deactivate the only active superadmin -> Must fail!
        res_deact = client.patch(f'/api/v1/accounts/users/{self.superadmin.id}/', {'is_active': False})
        self.assertEqual(res_deact.status_code, 400)
        self.assertIn('last active Superadmin', str(res_deact.data))

        # Attempt to demote to staff -> Must fail!
        res_demote = client.patch(f'/api/v1/accounts/users/{self.superadmin.id}/', {'system_role': 'staff'})
        self.assertEqual(res_demote.status_code, 400)
        self.assertIn('last active Superadmin', str(res_demote.data))

    def test_user_login_success(self):
        client = APIClient()
        res = client.post('/api/v1/auth/login/', {'email': 'admin@firm.com', 'password': 'Password@123'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['user']['email'], 'admin@firm.com')

    def test_user_login_invalid_password(self):
        client = APIClient()
        res = client.post('/api/v1/auth/login/', {'email': 'admin@firm.com', 'password': 'WrongPassword!'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid', res.data['error'])

    def test_user_login_deactivated_user_blocked(self):
        self.staff.is_active = False
        self.staff.save()
        client = APIClient()
        res = client.post('/api/v1/auth/login/', {'email': 'staff@firm.com', 'password': 'Password@123'})
        self.assertEqual(res.status_code, 403)
        self.assertIn('deactivated', res.data['error'])

    def test_user_creation_staff_forbidden_admin_allowed(self):
        client = APIClient()

        # Staff cannot create users
        client.force_authenticate(user=self.staff)
        res_staff = client.post('/api/v1/accounts/users/', {
            'email': 'newguy@firm.com',
            'full_name': 'New Guy',
            'password': 'Password@123',
            'system_role': 'staff',
        })
        self.assertEqual(res_staff.status_code, 403)

        # Admin can create users
        client.force_authenticate(user=self.admin)
        res_admin = client.post('/api/v1/accounts/users/', {
            'email': 'newguy@firm.com',
            'full_name': 'New Guy',
            'password': 'Password@123',
            'system_role': 'staff',
            'designation': 'Trainee'
        })
        self.assertEqual(res_admin.status_code, 201)
        self.assertEqual(res_admin.data['email'], 'newguy@firm.com')
        new_user = User.objects.get(email='newguy@firm.com')
        self.assertEqual(new_user.firm, self.firm)

    def test_mentionable_endpoint_returns_firm_active_staff(self):
        client = APIClient()
        client.force_authenticate(user=self.staff)

        res = client.get('/api/v1/accounts/users/mentionable/')
        self.assertEqual(res.status_code, 200)

        user_ids = [str(u['id']) for u in res.data]
        # Should include firm staff, admin, superadmin
        self.assertIn(str(self.staff.id), user_ids)
        self.assertIn(str(self.admin.id), user_ids)
        self.assertIn(str(self.superadmin.id), user_ids)

        # Should NOT include user from rival firm
        self.assertNotIn(str(self.other_user.id), user_ids)

        # Deactivated user should NOT be in mentionable
        self.staff.is_active = False
        self.staff.save()
        res_deact = client.get('/api/v1/accounts/users/mentionable/')
        deact_ids = [str(u['id']) for u in res_deact.data]
        self.assertNotIn(str(self.staff.id), deact_ids)

    def test_firm_settings_update_permissions(self):
        client = APIClient()

        # Staff cannot update firm settings
        client.force_authenticate(user=self.staff)
        res_staff = client.patch('/api/v1/accounts/firm/', {
            'staff_can_create_task': True
        })
        self.assertEqual(res_staff.status_code, 403)

        # Phase A (spec §2.2): Admin can NOT change firm settings - Superadmin only
        client.force_authenticate(user=self.admin)
        res_admin = client.patch('/api/v1/accounts/firm/', {
            'staff_can_create_task': True,
            'long_due_days': 45
        })
        self.assertEqual(res_admin.status_code, 403)

        # Superadmin can update firm settings
        client.force_authenticate(user=self.superadmin)
        res_admin = client.patch('/api/v1/accounts/firm/', {
            'staff_can_create_task': True,
            'long_due_days': 45
        })
        self.assertEqual(res_admin.status_code, 200)
        self.firm.refresh_from_db()
        self.assertTrue(self.firm.staff_can_create_task)
        self.assertEqual(self.firm.long_due_days, 45)

    def test_user_branch_assignment_and_default(self):
        UserBranch.objects.create(user=self.staff, branch=self.branch, is_default=True)
        UserBranch.objects.create(user=self.staff, branch=self.branch2, is_default=False)

        self.assertEqual(self.staff.user_branches.count(), 2)
        default_ub = UserBranch.objects.get(user=self.staff, is_default=True)
        self.assertEqual(default_ub.branch, self.branch)
