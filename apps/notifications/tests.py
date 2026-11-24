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


class ReminderTests(TestCase):
    """Daily rent / contract / review reminders - each sent exactly once."""

    def setUp(self):
        from datetime import date, timedelta
        from apps.properties.models import Property
        from apps.bookings.models import Booking, Tenancy
        from apps.payments.models import Payment
        self.today = date(2026, 6, 10)
        self.landlord = User.objects.create_user(username='rem_landlord', password='pw', role='LANDLORD', is_verified=True)
        self.tenant = User.objects.create_user(username='rem_tenant', password='pw', role='TENANT')
        self.prop = Property.objects.create(landlord=self.landlord, title='Reminder Home', location='Ilemela',
                                            property_type='1BR', monthly_rent=100000, distance_from_center_km=1)
        self.booking = Booking.objects.create(property=self.prop, tenant=self.tenant, status='CONFIRMED',
                                              move_in_date=self.today + timedelta(days=2),
                                              move_out_date=self.today + timedelta(days=92))
        self.payment = Payment.objects.create(booking=self.booking, amount=300000, status='PENDING',
                                              due_date=self.today + timedelta(days=2))
        self.Tenancy, self.Booking, self.timedelta = Tenancy, Booking, timedelta

    def _run(self, offset_days=0):
        from apps.notifications.reminders import send_due_reminders
        return send_due_reminders(today=self.today + self.timedelta(days=offset_days))

    def kinds(self, user):
        return list(Notification.objects.filter(user=user).order_by('created_at').values_list('kind', flat=True))

    def test_rent_due_soon_then_today_then_overdue_weekly_each_once(self):
        self._run(); self._run()
        self.assertEqual(self.kinds(self.tenant), ['rent_due_soon'])
        self.assertIn('TZS 300,000', Notification.objects.get(user=self.tenant).body)
        self._run(2)
        self.assertEqual(self.kinds(self.tenant)[-1], 'rent_due_today')
        for day in (3, 4, 5, 9, 10):   # 1..8 days late: one overdue round, then a second from day 8
            self._run(day)
        self.assertEqual(self.kinds(self.tenant).count('rent_overdue'), 2)
        self.assertEqual(self.kinds(self.landlord).count('rent_overdue'), 2)

    def test_paid_or_cancelled_rent_gets_no_reminder(self):
        self.payment.status = 'TENANT_PAID'
        self.payment.save()
        self._run(); self._run(5)
        self.assertEqual(self.kinds(self.tenant), [])

    def test_contract_ending_notices_at_30_and_7_days(self):
        t = self.Tenancy.objects.create(booking=self.booking, property=self.prop, tenant=self.tenant,
                                        start_date=self.today - self.timedelta(days=60),
                                        end_date=self.today + self.timedelta(days=40), duration_months=3)
        self.payment.status = 'COMPLETED'
        self.payment.save()
        self._run()            # 40 days left - nothing yet
        self._run(10); self._run(11)   # 30, 29 days left - one notice
        self._run(35)          # 5 days left (missed day 33) - still gets the 7-day one
        self.assertEqual(self.kinds(self.tenant), ['contract_ending', 'contract_ending'])
        t.renewal_requested = True
        t.save()
        Notification.objects.all().delete()
        self._run(36)
        self.assertEqual(self.kinds(self.tenant), [])

    def test_review_invite_after_moving_out(self):
        self.payment.status = 'COMPLETED'
        self.payment.save()
        self.Tenancy.objects.create(booking=self.booking, property=self.prop, tenant=self.tenant,
                                    start_date=self.today - self.timedelta(days=90),
                                    end_date=self.today - self.timedelta(days=1), duration_months=3)
        self._run(); self._run()
        self.assertEqual(self.kinds(self.tenant), ['review_invite'])

    def test_daily_job_command_sends_reminders(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('update_tenancy_statuses', stdout=out)
        self.assertIn('Reminders sent', out.getvalue())
