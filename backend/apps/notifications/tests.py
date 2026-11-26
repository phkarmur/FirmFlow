from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import Firm, User
from apps.notifications.models import Notification

class NotificationTests(TestCase):
    def setUp(self):
        self.firm = Firm.objects.create(name='Notif CA Firm')
        self.user1 = User.objects.create_user(email='u1@notif.com', firm=self.firm, system_role=User.Role.STAFF)
        self.user2 = User.objects.create_user(email='u2@notif.com', firm=self.firm, system_role=User.Role.STAFF)

        # Create 3 notifications for user1, 1 for user2
        self.n1 = Notification.objects.create(
            firm=self.firm,
            user=self.user1,
            kind=Notification.Kind.MENTIONED,
            title='You were mentioned on FF-2026-000001',
            body='Please review the purchase register',
            is_read=False
        )
        self.n2 = Notification.objects.create(
            firm=self.firm,
            user=self.user1,
            kind=Notification.Kind.TASK_ASSIGNED,
            title='Task assigned: GSTR-3B',
            body='Assigned by Admin',
            is_read=False
        )
        self.n3 = Notification.objects.create(
            firm=self.firm,
            user=self.user1,
            kind=Notification.Kind.DUE_TODAY,
            title='Task Due Today',
            body='Filing deadline is 6 PM',
            is_read=True
        )

        self.n_other = Notification.objects.create(
            firm=self.firm,
            user=self.user2,
            kind=Notification.Kind.TASK_ASSIGNED,
            title='User 2 Private Notification',
            is_read=False
        )

    def test_unread_count_and_user_isolation(self):
        client = APIClient()
        client.force_authenticate(user=self.user1)

        # Unread count should be 2 for user1 (n1, n2)
        res = client.get('/api/v1/notifications/unread_count/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['unread_count'], 2)

        # User1 notification list should only contain user1's 3 notifications
        res_list = client.get('/api/v1/notifications/')
        self.assertEqual(res_list.status_code, 200)
        ids = [n['id'] for n in res_list.data['results']]
        self.assertIn(str(self.n1.id), ids)
        self.assertIn(str(self.n2.id), ids)
        self.assertIn(str(self.n3.id), ids)
        self.assertNotIn(str(self.n_other.id), ids)

    def test_mark_single_notification_read(self):
        client = APIClient()
        client.force_authenticate(user=self.user1)

        res = client.post(f'/api/v1/notifications/{self.n1.id}/mark_read/')
        self.assertEqual(res.status_code, 200)
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.is_read)
        self.assertIsNotNone(self.n1.read_at)

        # Unread count decrements to 1
        res_count = client.get('/api/v1/notifications/unread_count/')
        self.assertEqual(res_count.data['unread_count'], 1)

    def test_mark_all_read(self):
        client = APIClient()
        client.force_authenticate(user=self.user1)

        res = client.post('/api/v1/notifications/mark_all_read/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Notification.objects.filter(user=self.user1, is_read=False).count(), 0)

        # user2 unread notification is untouched
        self.n_other.refresh_from_db()
        self.assertFalse(self.n_other.is_read)
