from django.test import TestCase, Client
from django.urls import reverse

from apps.users.models import User
from .models import Notification


class NotificationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='notif_user', password='pw', role='TENANT')

    def test_notify_creates_unread_notification(self):
        n = Notification.notify(self.user, 'account_verified', 'Hello', link='/somewhere/')
        self.assertEqual(n.user, self.user)
        self.assertIsNone(n.read_at)
        self.assertEqual(n.icon, '🎉')


class NotificationInboxTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='inbox_user', password='pw', role='TENANT')
        self.other = User.objects.create_user(username='other_user', password='pw', role='TENANT')
        self.client = Client()
        self.client.login(username='inbox_user', password='pw')

    def test_inbox_shows_own_notifications_only(self):
        Notification.notify(self.user, 'account_verified', 'Yours')
        Notification.notify(self.other, 'account_verified', 'Not yours')

        response = self.client.get(reverse('notifications:inbox'))
        body = response.content.decode()
        self.assertIn('Yours', body)
        self.assertNotIn('Not yours', body)

    def test_viewing_inbox_marks_notifications_read(self):
        n = Notification.notify(self.user, 'account_verified', 'Hello')
        self.assertIsNone(n.read_at)

        self.client.get(reverse('notifications:inbox'))

        n.refresh_from_db()
        self.assertIsNotNone(n.read_at)

    def test_unread_badge_appears_in_base_template(self):
        Notification.notify(self.user, 'account_verified', 'Hello')
        response = self.client.get(reverse('core:dashboard'))
        self.assertIn('<span class="bell-badge">', response.content.decode())

    def test_no_badge_when_nothing_unread(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertNotIn('<span class="bell-badge">', response.content.decode())
