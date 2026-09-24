import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase, Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from apps.users.models import User
from apps.properties.models import Property
from apps.bookings.models import Booking, Tenancy
from apps.bookings.services import sync_tenancy_statuses
from apps.payments.models import Payment

class BookingApprovalTests(TestCase):
    def setUp(self):
        self.client = Client()
        # 1. Create Landlord
        self.landlord = User.objects.create_user(
            username='landlord', password='testpassword', role='LANDLORD'
        )
        
        # 2. Create Tenant
        self.tenant = User.objects.create_user(
            username='tenant', password='testpassword', role='TENANT'
        )
        
        # 3. Create Property
        self.property = Property.objects.create(
            landlord=self.landlord,
            title='Nice Bedsitter',
            location='Iyunga',
            property_type='BEDSITTER',
            monthly_rent=100000,
            distance_from_center_km=1.2
        )
        
        # 4. Create Booking for 3 months stay
        self.move_in = timezone.now().date()
        # 3 months in the future:
        self.move_out = self.move_in + timedelta(days=90)
        
        self.booking = Booking.objects.create(
            property=self.property,
            tenant=self.tenant,
            move_in_date=self.move_in,
            move_out_date=self.move_out,
            status='PENDING'
        )

    def test_approve_booking_creates_correct_payment(self):
        """
        Test that when a landlord approves a booking:
        1. Booking status becomes CONFIRMED.
        2. A Payment object is created for the tenant.
        3. The Payment amount is calculated correctly (monthly_rent * duration).
        4. The payment doesn't cause a FieldError due to 'landlord' key.
        """
        # Log in landlord
        self.client.login(username='landlord', password='testpassword')
        
        # Call the approve endpoint
        response = self.client.post(reverse('bookings:approve_booking', kwargs={'booking_id': self.booking.id}))
        
        # Should redirect to landlord bookings page
        self.assertRedirects(response, reverse('bookings:landlord_bookings'))
        
        # Reload booking from DB
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'CONFIRMED')
        
        # Check if payment was created
        payment_exists = Payment.objects.filter(booking=self.booking).exists()
        self.assertTrue(payment_exists)
        
        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.tenant, self.tenant)
        self.assertEqual(payment.status, 'PENDING')
        
        # Calculate expected amount based on stay duration (90 days = 3 months stay)
        move_in = self.booking.move_in_date
        move_out = self.booking.move_out_date
        months_diff = (move_out.year - move_in.year) * 12 + (move_out.month - move_in.month)
        if months_diff <= 0:
            months_diff = 1
        expected_amount = self.property.monthly_rent * months_diff

        self.assertEqual(payment.amount, expected_amount)


class TenancyTestBase(TestCase):
    """Shared landlord/tenant/property fixtures for the Tenancy test classes below."""

    def setUp(self):
        self.landlord = User.objects.create_user(username='landlord1', password='pw', role='LANDLORD', email='l1@example.com')
        self.tenant = User.objects.create_user(username='tenant1', password='pw', role='TENANT', email='t1@example.com')
        self.other_landlord = User.objects.create_user(username='landlord2', password='pw', role='LANDLORD', email='l2@example.com')
        self.other_tenant = User.objects.create_user(username='tenant2', password='pw', role='TENANT', email='t2@example.com')
        self.property = Property.objects.create(
            landlord=self.landlord, title='Test Property', location='Mwanza',
            property_type='2BR', monthly_rent=100000, distance_from_center_km=1.0,
        )

    def make_tenancy(self, start_date, end_date, duration_months=6, status=None, property=None, tenant=None):
        """Creates an approved Booking + its Tenancy directly (bypassing the
        approval view) for tests that only care about the Tenancy itself."""
        property = property or self.property
        tenant = tenant or self.tenant
        booking = Booking.objects.create(
            property=property, tenant=tenant, move_in_date=start_date,
            move_out_date=end_date, status='CONFIRMED',
        )
        tenancy = Tenancy.objects.create(
            booking=booking, property=property, tenant=tenant,
            start_date=start_date, end_date=end_date, duration_months=duration_months,
            status=status or ('active' if start_date <= timezone.localdate() <= end_date else 'upcoming'),
        )
        return tenancy


class TenancyProgressTests(TenancyTestBase):
    """Progress/days-remaining calculations at the 5 required boundaries,
    plus the spec's own worked example (6 months from 1 Jan)."""

    def _at(self, tenancy, today):
        """Evaluate tenancy's computed properties as of a specific 'today'."""
        import apps.bookings.models as tenancy_models
        original = tenancy_models.timezone.localdate
        tenancy_models.timezone.localdate = lambda: today
        try:
            return {
                'display_status': tenancy.display_status,
                'days_total': tenancy.days_total,
                'days_elapsed': tenancy.days_elapsed,
                'days_remaining': tenancy.days_remaining,
                'progress_percent': tenancy.progress_percent,
                'current_month_number': tenancy.current_month_number,
            }
        finally:
            tenancy_models.timezone.localdate = original

    def test_worked_example_6_months_from_1_jan(self):
        """A 6-month tenancy from 1 Jan shows Month 2 of 6 and 149 (~150) days remaining on 1 Feb."""
        tenancy = Tenancy(
            property=self.property, tenant=self.tenant, duration_months=6,
            start_date=datetime.date(2027, 1, 1), end_date=datetime.date(2027, 6, 30),
        )
        result = self._at(tenancy, datetime.date(2027, 2, 1))
        self.assertEqual(result['current_month_number'], 2)
        self.assertEqual(result['days_remaining'], 149)

    def test_before_start(self):
        tenancy = Tenancy(
            property=self.property, tenant=self.tenant, duration_months=6,
            start_date=datetime.date(2027, 1, 1), end_date=datetime.date(2027, 6, 30),
        )
        result = self._at(tenancy, datetime.date(2026, 12, 1))
        self.assertEqual(result['display_status'], 'upcoming')
        self.assertEqual(result['days_elapsed'], 0)
        self.assertEqual(result['progress_percent'], 0)

    def test_day_1(self):
        tenancy = Tenancy(
            property=self.property, tenant=self.tenant, duration_months=6,
            start_date=datetime.date(2027, 1, 1), end_date=datetime.date(2027, 6, 30),
        )
        result = self._at(tenancy, datetime.date(2027, 1, 1))
        self.assertEqual(result['display_status'], 'active')
        self.assertEqual(result['days_elapsed'], 1)
        self.assertEqual(result['current_month_number'], 1)

    def test_middle(self):
        tenancy = Tenancy(
            property=self.property, tenant=self.tenant, duration_months=6,
            start_date=datetime.date(2027, 1, 1), end_date=datetime.date(2027, 6, 30),
        )
        result = self._at(tenancy, datetime.date(2027, 4, 1))
        self.assertEqual(result['display_status'], 'active')
        self.assertEqual(result['current_month_number'], 4)

    def test_last_day(self):
        tenancy = Tenancy(
            property=self.property, tenant=self.tenant, duration_months=6,
            start_date=datetime.date(2027, 1, 1), end_date=datetime.date(2027, 6, 30),
        )
        result = self._at(tenancy, datetime.date(2027, 6, 30))
        self.assertEqual(result['days_remaining'], 0)
        self.assertEqual(result['progress_percent'], 100)
        # within ENDING_SOON_DAYS of its own end date
        self.assertEqual(result['display_status'], 'ending_soon')

    def test_after_end(self):
        tenancy = Tenancy(
            property=self.property, tenant=self.tenant, duration_months=6,
            start_date=datetime.date(2027, 1, 1), end_date=datetime.date(2027, 6, 30),
        )
        result = self._at(tenancy, datetime.date(2027, 7, 1))
        self.assertEqual(result['display_status'], 'ended')
        self.assertEqual(result['days_remaining'], 0)
        self.assertEqual(result['progress_percent'], 100)


class OverlapRejectionTests(TenancyTestBase):
    def test_approval_rejects_overlapping_tenancy(self):
        today = timezone.localdate()
        self.make_tenancy(today, today + timedelta(days=180))

        conflicting_booking = Booking.objects.create(
            property=self.property, tenant=self.other_tenant,
            move_in_date=today + timedelta(days=30), move_out_date=today + timedelta(days=210),
            status='PENDING',
        )
        client = Client()
        client.login(username='landlord1', password='pw')
        client.post(reverse('bookings:approve_booking', kwargs={'booking_id': conflicting_booking.id}))

        conflicting_booking.refresh_from_db()
        self.assertEqual(conflicting_booking.status, 'PENDING')  # rejected, not approved
        self.assertFalse(Tenancy.objects.filter(booking=conflicting_booking).exists())

    def test_approval_succeeds_for_non_overlapping_dates(self):
        today = timezone.localdate()
        existing = self.make_tenancy(today, today + timedelta(days=180))

        next_booking = Booking.objects.create(
            property=self.property, tenant=self.other_tenant,
            move_in_date=existing.available_from, move_out_date=existing.available_from + timedelta(days=180),
            status='PENDING',
        )
        client = Client()
        client.login(username='landlord1', password='pw')
        client.post(reverse('bookings:approve_booking', kwargs={'booking_id': next_booking.id}))

        next_booking.refresh_from_db()
        self.assertEqual(next_booking.status, 'CONFIRMED')
        self.assertTrue(Tenancy.objects.filter(booking=next_booking).exists())

    def test_booking_form_rejects_move_in_inside_existing_tenancy(self):
        today = timezone.localdate()
        tenancy = self.make_tenancy(today, today + timedelta(days=180))

        client = Client()
        client.login(username='tenant2', password='pw')
        response = client.post(
            reverse('bookings:create_booking', kwargs={'property_id': self.property.id}),
            {
                'move_in_date': (tenancy.start_date + timedelta(days=30)).isoformat(),
                'move_out_date': (tenancy.start_date + timedelta(days=200)).isoformat(),
            },
            follow=True,
        )
        self.assertFalse(Booking.objects.filter(property=self.property, tenant=self.other_tenant).exists())
        messages = [str(m) for m in response.context[-1]['messages']]
        self.assertIn('occupied until', messages[-1])

    def test_booking_form_accepts_move_in_after_existing_tenancy_ends(self):
        today = timezone.localdate()
        tenancy = self.make_tenancy(today, today + timedelta(days=180))

        client = Client()
        client.login(username='tenant2', password='pw')
        client.post(
            reverse('bookings:create_booking', kwargs={'property_id': self.property.id}),
            {
                'move_in_date': tenancy.available_from.isoformat(),
                'move_out_date': (tenancy.available_from + timedelta(days=180)).isoformat(),
            },
        )
        self.assertTrue(Booking.objects.filter(property=self.property, tenant=self.other_tenant).exists())


class CancellationSignalTests(TenancyTestBase):
    def test_cancelling_booking_terminates_tenancy_and_frees_property(self):
        """
        There's no dedicated tenant-facing "cancel an approved booking" view
        in this codebase (only reject_booking for still-PENDING bookings,
        and terminate_tenancy for the landlord) - the signal is what has to
        catch this regardless of call site, so this test exercises it the
        way any such path (existing or future) would: an instance-level
        .save() with status='CANCELLED'. See apps/bookings/signals.py.
        """
        today = timezone.localdate()
        tenancy = self.make_tenancy(today - timedelta(days=10), today + timedelta(days=170))
        self.assertTrue(Property.objects.get(pk=self.property.pk).is_occupied_now)

        booking = tenancy.booking
        booking.status = 'CANCELLED'
        booking.save()  # instance.save(), not .update() - required for post_save to fire

        tenancy.refresh_from_db()
        self.assertEqual(tenancy.status, 'terminated')
        self.assertIsNotNone(tenancy.terminated_at)
        self.assertFalse(Property.objects.get(pk=self.property.pk).is_occupied_now)


class RenewalFlowTests(TenancyTestBase):
    def test_approve_renewal_creates_new_booking_payment_and_tenancy(self):
        today = timezone.localdate()
        old_tenancy = self.make_tenancy(today - timedelta(days=170), today + timedelta(days=10), status='active')
        old_tenancy.renewal_requested = True
        old_tenancy.save()

        client = Client()
        client.login(username='landlord1', password='pw')
        client.post(reverse('bookings:approve_renewal', kwargs={'tenancy_id': old_tenancy.id}))

        old_tenancy.refresh_from_db()
        self.assertEqual(old_tenancy.status, 'renewed')
        self.assertFalse(old_tenancy.renewal_requested)

        new_tenancy = Tenancy.objects.exclude(id=old_tenancy.id).get(property=self.property)
        self.assertEqual(new_tenancy.start_date, old_tenancy.end_date + timedelta(days=1))
        self.assertEqual(new_tenancy.duration_months, old_tenancy.duration_months)
        self.assertEqual(new_tenancy.booking.status, 'CONFIRMED')

        payment = Payment.objects.get(booking=new_tenancy.booking)
        self.assertEqual(payment.amount, self.property.monthly_rent * old_tenancy.duration_months)
        self.assertEqual(payment.status, 'PENDING')

    def test_decline_renewal_resets_flag_without_side_effects(self):
        today = timezone.localdate()
        tenancy = self.make_tenancy(today - timedelta(days=10), today + timedelta(days=170), status='active')
        tenancy.renewal_requested = True
        tenancy.save()

        client = Client()
        client.login(username='landlord1', password='pw')
        client.post(reverse('bookings:decline_renewal', kwargs={'tenancy_id': tenancy.id}))

        tenancy.refresh_from_db()
        self.assertFalse(tenancy.renewal_requested)
        self.assertEqual(tenancy.status, 'active')
        self.assertEqual(Tenancy.objects.filter(property=self.property).count(), 1)


class SyncTenancyStatusesTests(TenancyTestBase):
    def test_upcoming_to_active(self):
        today = timezone.localdate()
        tenancy = self.make_tenancy(today - timedelta(days=1), today + timedelta(days=180), status='upcoming')
        sync_tenancy_statuses()
        tenancy.refresh_from_db()
        self.assertEqual(tenancy.status, 'active')

    def test_active_to_ending_soon(self):
        today = timezone.localdate()
        tenancy = self.make_tenancy(today - timedelta(days=170), today + timedelta(days=10), status='active')
        sync_tenancy_statuses()
        tenancy.refresh_from_db()
        self.assertEqual(tenancy.status, 'ending_soon')

    def test_ended_marks_booking_completed(self):
        today = timezone.localdate()
        tenancy = self.make_tenancy(today - timedelta(days=200), today - timedelta(days=5), status='active')
        result = sync_tenancy_statuses()
        tenancy.refresh_from_db()
        self.assertEqual(tenancy.status, 'ended')
        self.assertEqual(tenancy.booking.status, 'COMPLETED')
        self.assertEqual(result['bookings_completed'], 1)


class CronEndpointTests(TenancyTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('bookings:cron_update_tenancy_statuses')

    def test_no_header_unauthorized(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    @override_settings(CRON_SECRET='right-secret')
    def test_wrong_secret_unauthorized(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION='Bearer wrong-secret')
        self.assertEqual(response.status_code, 401)

    def test_secret_unset_fails_closed(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION='Bearer anything')
        self.assertEqual(response.status_code, 401)

    @override_settings(CRON_SECRET='right-secret')
    def test_correct_secret_ok(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION='Bearer right-secret')
        self.assertEqual(response.status_code, 200)

    @override_settings(CRON_SECRET='right-secret')
    def test_post_not_allowed(self):
        response = self.client.post(self.url, HTTP_AUTHORIZATION='Bearer right-secret')
        self.assertEqual(response.status_code, 405)


class AccessControlTests(TenancyTestBase):
    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.tenancy = self.make_tenancy(today - timedelta(days=10), today + timedelta(days=170), status='active')

    def test_unrelated_tenant_cannot_give_notice(self):
        client = Client()
        client.login(username='tenant2', password='pw')  # not the tenant on self.tenancy
        response = client.get(reverse('bookings:give_notice', kwargs={'tenancy_id': self.tenancy.id}))
        self.assertEqual(response.status_code, 404)

    def test_unrelated_user_cannot_download_contract_pdf(self):
        client = Client()
        client.login(username='tenant2', password='pw')  # neither tenant nor landlord on this tenancy
        response = client.get(reverse('bookings:download_contract_pdf', kwargs={'tenancy_id': self.tenancy.id}))
        self.assertEqual(response.status_code, 404)

    def test_unrelated_landlord_cannot_terminate(self):
        client = Client()
        client.login(username='landlord2', password='pw')  # not this property's landlord
        response = client.get(reverse('bookings:terminate_tenancy', kwargs={'tenancy_id': self.tenancy.id}))
        self.assertEqual(response.status_code, 404)

    def test_unrelated_landlord_cannot_approve_renewal(self):
        self.tenancy.renewal_requested = True
        self.tenancy.save()
        client = Client()
        client.login(username='landlord2', password='pw')
        response = client.get(reverse('bookings:approve_renewal', kwargs={'tenancy_id': self.tenancy.id}))
        self.assertEqual(response.status_code, 404)

    def test_my_contract_never_shows_another_tenants_property(self):
        """tenant2 has no tenancy of their own - their My Contract page must
        not surface tenant1's contract with self.property."""
        client = Client()
        client.login(username='tenant2', password='pw')
        response = client.get(reverse('bookings:my_contract'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.property.title)


class CreateBookingAccessTests(TenancyTestBase):
    """Booking requires sign-in; a signed-in non-tenant gets a friendly
    redirect, never a 403/500. See apps.bookings.views.create_booking."""

    def setUp(self):
        super().setUp()
        self.booking_url = reverse('bookings:create_booking', kwargs={'property_id': self.property.id})

    def test_anonymous_get_redirects_to_login_with_next(self):
        response = Client().get(self.booking_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('users:login'), response.url)
        self.assertIn(self.booking_url, response.url)

    def test_anonymous_post_redirects_to_login_with_next_not_500_or_403(self):
        response = Client().post(self.booking_url, {
            'move_in_date': '2027-01-01', 'move_out_date': '2027-06-01',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('users:login'), response.url)
        self.assertIn(self.booking_url, response.url)

    def test_signed_in_landlord_gets_friendly_message_not_error_page(self):
        client = Client()
        client.login(username='landlord1', password='pw')
        response = client.post(self.booking_url, {
            'move_in_date': '2027-01-01', 'move_out_date': '2027-06-01',
        }, follow=True)
        self.assertEqual(response.status_code, 200)  # not 403/500
        self.assertRedirects(
            response, reverse('properties:detail', kwargs={'pk': self.property.id})
        )
        messages = [str(m) for m in response.context[-1]['messages']]
        self.assertTrue(any('tenant' in m.lower() for m in messages))
        self.assertFalse(Booking.objects.filter(property=self.property, tenant=self.landlord).exists())
