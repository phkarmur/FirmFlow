import io
from django.test import TestCase
from rest_framework.test import APIClient
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.models import Firm, User
from apps.clients.models import Client
from apps.clients.importer import ClientSpreadsheetImporter
from apps.common.models import AuditLog
from apps.tasks.models import Task
from apps.services.models import ServiceCategory, Service, TaskType

class ClientSecurityAndImporterTests(TestCase):
    def setUp(self):
        self.firm = Firm.objects.create(name='Audit Practice Firm')
        self.superadmin = User.objects.create_user(email='boss@firm.com', full_name='Boss Partner', firm=self.firm, system_role=User.Role.SUPERADMIN)
        self.admin = User.objects.create_user(email='partner@firm.com', full_name='Partner User', firm=self.firm, system_role=User.Role.ADMIN)
        self.staff = User.objects.create_user(email='staff@firm.com', full_name='Staff User', firm=self.firm, system_role=User.Role.STAFF)

        self.client_obj = Client.objects.create(
            firm=self.firm,
            name='Alpha Infotech Pvt Ltd',
            client_type=Client.ClientType.COMPANY,
            gstin='27AABCA1234F1Z9'
        )
        self.client_obj.set_pan('AABCA1234F')
        self.client_obj.save()

    def test_pan_stored_encrypted_and_displayed_masked(self):
        self.client_obj.refresh_from_db()
        # PAN in database is NOT plain text!
        self.assertNotEqual(self.client_obj.pan_encrypted, 'AABCA1234F')
        # Masked representation matches spec
        self.assertEqual(self.client_obj.pan_masked, 'XXXXX1234X')
        # Decrypted PAN matches original
        self.assertEqual(self.client_obj.get_pan_decrypted(), 'AABCA1234F')

    def test_reveal_pan_requires_admin_and_reason_and_audit_logged(self):
        client = APIClient()

        # 1. Staff cannot reveal PAN (403)
        client.force_authenticate(user=self.staff)
        res_staff = client.post(f'/api/v1/clients/{self.client_obj.id}/reveal_pan/', {'reason': 'Checking IT portal'})
        self.assertEqual(res_staff.status_code, 403)

        # 2. Admin without reason fails (400)
        client.force_authenticate(user=self.admin)
        res_no_reason = client.post(f'/api/v1/clients/{self.client_obj.id}/reveal_pan/', {'reason': ''})
        self.assertEqual(res_no_reason.status_code, 400)

        # 3. Admin with valid reason succeeds and logs audit entry
        res_ok = client.post(f'/api/v1/clients/{self.client_obj.id}/reveal_pan/', {'reason': 'Annual ROC Verification'})
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.data['pan'], 'AABCA1234F')

        # Check AuditLog entry
        audit = AuditLog.objects.filter(action='client.pan_revealed', entity_id=str(self.client_obj.id)).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.new_value['reason'], 'Annual ROC Verification')

    def test_client_with_tasks_cannot_be_hard_deleted(self):
        cat = ServiceCategory.objects.create(firm=self.firm, name='Audit')
        svc = Service.objects.create(category=cat, name='Statutory')
        tt = TaskType.objects.create(service=svc, name='Audit Task')
        branch = self.firm.branches.create(name='HQ', code='HQ')

        Task.objects.create(
            firm=self.firm,
            branch=branch,
            client=self.client_obj,
            task_type=tt,
            task_type_name_snapshot=tt.name,
            task_number='FF-2026-999999',
            title='Test Task',
            due_date='2026-12-31'
        )

        client = APIClient()
        client.force_authenticate(user=self.admin)
        res = client.delete(f'/api/v1/clients/{self.client_obj.id}/')
        self.assertEqual(res.status_code, 400)
        self.assertIn('cannot be deleted', res.data['error'])

    def test_client_spreadsheet_importer_creates_valid_clients(self):
        csv_content = """Client Name,Client Type,PAN,GSTIN,Email,Phone,Contact Person,State Code
Zenith Retail LLP,llp,AACCS1111K,24AACCS1111K1ZT,info@zenith.com,9898098980,Sunil Joshi,24
Kavita Singh,individual,AQZPS8888D,,kavita@test.com,9876543210,Kavita Singh,07
Invalid PAN Client,company,INVALIDPAN,,test@test.com,,,
"""
        file = SimpleUploadedFile("clients.csv", csv_content.encode('utf-8'), content_type="text/csv")
        result = ClientSpreadsheetImporter.import_clients(self.firm, file, user=self.admin)

        self.assertEqual(result['imported_count'], 2)
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('Invalid PAN', result['errors'][0]['error'])

        # Verify Zenith Retail LLP created with encrypted PAN
        zenith = Client.objects.get(firm=self.firm, name='Zenith Retail LLP')
        self.assertEqual(zenith.get_pan_decrypted(), 'AACCS1111K')
        self.assertEqual(zenith.pan_masked, 'XXXXX1111X')
        self.assertEqual(zenith.contacts.count(), 1)

    def test_client_create_duplicate_pan_in_same_firm_fails(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        # Attempt to create client with same PAN as self.client_obj ('AABCA1234F')
        res = client.post('/api/v1/clients/', {
            'name': 'Duplicate PAN Client',
            'client_type': 'company',
            'pan': 'AABCA1234F'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('already exists', str(res.data))

    def test_client_create_same_pan_different_firm_allowed(self):
        other_firm = Firm.objects.create(name='Other Audit Firm')
        other_admin = User.objects.create_user(email='partner@other.com', firm=other_firm, system_role=User.Role.ADMIN)

        client = APIClient()
        client.force_authenticate(user=other_admin)

        # Other firm can register client with same PAN
        res = client.post('/api/v1/clients/', {
            'name': 'Branch Office in Other Firm',
            'client_type': 'company',
            'pan': 'AABCA1234F'
        })
        self.assertEqual(res.status_code, 201)

    def test_client_contacts_and_groups(self):
        from apps.clients.models import ClientContact, ClientGroup

        group = ClientGroup.objects.create(firm=self.firm, name='Shah Conglomerate')
        self.client_obj.client_group = group
        self.client_obj.save()
        self.assertEqual(self.client_obj.client_group.name, 'Shah Conglomerate')

        contact = ClientContact.objects.create(
            client=self.client_obj,
            name='Rajesh Shah',
            role=ClientContact.Role.OWNER,
            email='rajesh@alpha.com',
            phone='9820098200',
            is_primary=True
        )
        self.assertEqual(self.client_obj.contacts.count(), 1)
        self.assertTrue(contact.is_primary)

    def test_client_search_and_filtering(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        # Search by client name
        res = client.get('/api/v1/clients/?search=Alpha')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data['results']), 1)

        # Search by masked pan fragment
        res_pan = client.get('/api/v1/clients/?search=1234')
        self.assertEqual(res_pan.status_code, 200)
        self.assertEqual(len(res_pan.data['results']), 1)

    def test_client_spreadsheet_importer_handles_missing_name(self):
        csv_content = """Client Name,Client Type,PAN,GSTIN
,company,BBBBB2222K,
"""
        file = SimpleUploadedFile("clients.csv", csv_content.encode('utf-8'), content_type="text/csv")
        result = ClientSpreadsheetImporter.import_clients(self.firm, file, user=self.admin)
        self.assertEqual(result['imported_count'], 0)
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('client name', result['errors'][0]['error'].lower())
