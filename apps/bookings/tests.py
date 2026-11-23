import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from apps.users.models import User
from apps.properties.models import Property
from apps.bookings.models import Booking, Tenancy, TerminationRequest
from apps.bookings.services import sync_tenancy_statuses
from apps.payments.models import Payment
from apps.notifications.models import Notification

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
        response = client.get(reverse('bookings:request_termination', kwargs={'tenancy_id': self.tenancy.id}))
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


class BookingNotificationTests(TenancyTestBase):
    """Each booking lifecycle action should leave an in-app Notification for
    whoever needs to see it - see apps.notifications.models.Notification."""

    def test_create_booking_notifies_landlord(self):
        client = Client()
        client.login(username='tenant1', password='pw')
        move_in = timezone.localdate() + timedelta(days=10)
        client.post(reverse('bookings:create_booking', kwargs={'property_id': self.property.id}), {
            'move_in_date': move_in.isoformat(), 'months': 3,
        })
        n = Notification.objects.get(user=self.landlord, kind='booking_request')
        self.assertIn('tenant1', n.body)
        self.assertFalse(n.read_at)

    def test_approve_booking_notifies_tenant(self):
        booking = Booking.objects.create(
            property=self.property, tenant=self.tenant,
            move_in_date=timezone.localdate(), move_out_date=timezone.localdate() + timedelta(days=90),
            status='PENDING',
        )
        client = Client()
        client.login(username='landlord1', password='pw')
        client.post(reverse('bookings:approve_booking', kwargs={'booking_id': booking.id}))
        self.assertTrue(Notification.objects.filter(user=self.tenant, kind='booking_approved').exists())

    def test_reject_booking_notifies_tenant(self):
        booking = Booking.objects.create(
            property=self.property, tenant=self.tenant,
            move_in_date=timezone.localdate(), move_out_date=timezone.localdate() + timedelta(days=90),
            status='PENDING',
        )
        client = Client()
        client.login(username='landlord1', password='pw')
        client.post(reverse('bookings:reject_booking', kwargs={'booking_id': booking.id}))
        self.assertTrue(Notification.objects.filter(user=self.tenant, kind='booking_declined').exists())


class ViewBookingTests(TenancyTestBase):
    """The booking detail page's template was missing entirely - every
    'View Details' click 500'd."""

    def setUp(self):
        super().setUp()
        self.booking = Booking.objects.create(
            property=self.property, tenant=self.tenant,
            move_in_date=timezone.localdate(), move_out_date=timezone.localdate() + timedelta(days=90),
            status='CANCELLED', decline_reason='Dates no longer available',
        )
        self.url = reverse('bookings:view_booking', kwargs={'booking_id': self.booking.id})

    def test_landlord_sees_booking(self):
        client = Client()
        client.login(username='landlord1', password='pw')
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dates no longer available')
        self.assertContains(response, 'tenant1')

    def test_tenant_sees_booking(self):
        client = Client()
        client.login(username='tenant1', password='pw')
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Property')

    def test_unrelated_user_is_redirected(self):
        client = Client()
        client.login(username='tenant2', password='pw')
        response = client.get(self.url)
        self.assertRedirects(response, reverse('core:dashboard'), fetch_redirect_response=False)


class ContractVerificationTests(TenancyTestBase):
    """Contract PDFs are verifiable two independent ways (signed QR token,
    typed confirmation code); neither can be forged or swapped between docs."""

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.tenancy = self.make_tenancy(today - timedelta(days=10), today + timedelta(days=170))

    def _qr(self):
        from apps.bookings.verification import make_contract_token
        return make_contract_token(self.tenancy)

    def _code(self):
        from apps.bookings.verification import confirmation_code
        return confirmation_code(self.tenancy)

    def _get(self, url):
        return Client().get(url)

    def test_qr_round_trip_records_terms(self):
        from apps.bookings.verification import read_contract_token
        data = read_contract_token(self._qr())
        self.assertEqual(data['id'], self.tenancy.id)
        self.assertEqual((data['start'], data['end']), (self.tenancy.start_date, self.tenancy.end_date))
        self.assertEqual(data['rent'], self.property.monthly_rent)

    def test_genuine_qr_shows_active_contract(self):
        response = self._get(reverse('verify_document', kwargs={'token': self._qr()}))
        self.assertContains(response, 'Genuine contract')
        self.assertContains(response, self._code())

    def test_altered_qr_is_rejected(self):
        body, mac = self._qr().rsplit('.', 1)
        parts = body.split('.')
        parts[2] = parts[2][:-1] + ('a' if parts[2][-1] != 'a' else 'b')  # end date
        for tok in ('.'.join(parts) + '.' + mac, body + '.' + 'A' * 22):
            response = self._get(reverse('verify_document', kwargs={'token': tok}))
            self.assertEqual(response.status_code, 404)

    def test_codes_cannot_cross_document_types(self):
        from apps.payments.verification import read_token
        from apps.bookings.verification import read_contract_token
        self.assertIsNone(read_token(self._qr()))
        self.assertIsNone(read_contract_token('c' + self._qr()[1:].replace('.', '-', 1)))

    def test_typed_code_and_forgiving_variants(self):
        code = self._code()
        variants = [code, code.lower(), code.replace('-', ''), code.replace('-', ' '),
                    code.translate(str.maketrans('OIB', '018'))]
        for variant in variants:
            response = self._get(reverse('verify_by_code') + '?code=' + variant)
            self.assertEqual(response.status_code, 200, variant)
            self.assertContains(response, 'Genuine contract')

    def test_wrong_or_borrowed_code_is_rejected(self):
        code = self._code()
        other = self.make_tenancy(timezone.localdate() + timedelta(days=400), timezone.localdate() + timedelta(days=500))
        borrowed = code.replace(f'C{self.tenancy.id}-', f'C{other.id}-')
        last = code[-1]
        mistyped = code[:-1] + ('A' if last != 'A' else 'C')
        for bad in (borrowed, mistyped, 'VHF-C1-AAAA-BBBB-CC', 'nonsense'):
            response = self._get(reverse('verify_by_code') + '?code=' + bad)
            self.assertEqual(response.status_code, 404, bad)
            self.assertContains(response, 'Not a valid', status_code=404)

    def test_code_entry_page_renders_empty_form(self):
        response = self._get(reverse('verify_by_code'))
        self.assertContains(response, 'Enter the confirmation code')

    def test_terminated_contract_is_flagged_not_valid(self):
        self.tenancy.status = 'terminated'
        self.tenancy.terminated_at = timezone.now()
        self.tenancy.save()
        self.assertContains(self._get(reverse('verify_by_code') + '?code=' + self._code()), 'terminated')

    def test_dates_and_rent_changed_after_printing_are_flagged(self):
        token = self._qr()
        self.tenancy.end_date += timedelta(days=60)
        self.tenancy.save()
        self.property.monthly_rent = 999999
        self.property.save()
        response = self._get(reverse('verify_document', kwargs={'token': token}))
        self.assertContains(response, 'Dates changed since this document was printed')
        self.assertContains(response, 'Rent changed since this document was printed')

    def test_deleted_contract_is_reported(self):
        token = self._qr()
        self.tenancy.delete()
        self.assertContains(self._get(reverse('verify_document', kwargs={'token': token})),
                            'no longer exists', status_code=404)

    def test_no_private_details_shown(self):
        response = self._get(reverse('verify_by_code') + '?code=' + self._code())
        for private in ('t1@example.com', 'l1@example.com', 'tenant1', 'landlord1'):
            self.assertNotContains(response, private)

    def test_contract_pdf_downloads(self):
        client = Client()
        client.login(username='tenant1', password='pw')
        response = client.get(reverse('bookings:download_contract_pdf', kwargs={'tenancy_id': self.tenancy.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')


class TerminationAgreementTests(TenancyTestBase):
    """Early termination needs both parties: request (with reason) ->
    the other party agrees (terminated) or disagrees (continues)."""

    REASON = 'Relocating to Dodoma for a new job next month'

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.tenancy = self.make_tenancy(today - timedelta(days=10), today + timedelta(days=170), status='active')
        self.tenant_client = Client()
        self.tenant_client.login(username='tenant1', password='pw')
        self.landlord_client = Client()
        self.landlord_client.login(username='landlord1', password='pw')

    def _request(self, client, reason=REASON):
        return client.post(reverse('bookings:request_termination', kwargs={'tenancy_id': self.tenancy.id}),
                           {'reason': reason})

    def _respond(self, client, tr, action, note=''):
        return client.post(reverse('bookings:respond_termination', kwargs={'request_id': tr.id}),
                           {'action': action, 'note': note})

    def _status(self):
        self.tenancy.refresh_from_db()
        return self.tenancy.status

    def test_tenant_request_does_not_end_contract_and_notifies_landlord(self):
        self._request(self.tenant_client)
        tr = TerminationRequest.objects.get(tenancy=self.tenancy)
        self.assertEqual((tr.status, tr.requested_by, tr.reason), ('pending', self.tenant, self.REASON))
        self.assertEqual(self._status(), 'active')
        self.assertTrue(Notification.objects.filter(user=self.landlord, kind='termination_requested').exists())

    def test_reason_is_required(self):
        self._request(self.tenant_client, reason='bye')
        self.assertFalse(TerminationRequest.objects.exists())

    def test_landlord_sees_reason_and_choices_tenant_sees_waiting(self):
        self._request(self.tenant_client)
        body = self.landlord_client.get(reverse('bookings:landlord_occupancy')).content.decode()
        self.assertIn(self.REASON, body)
        self.assertIn('Agree', body)
        self.assertIn('Disagree', body)
        body = self.tenant_client.get(reverse('bookings:my_contract')).content.decode()
        self.assertIn('You asked to end this contract early', body)
        self.assertIn('Withdraw request', body)
        self.assertNotIn('value="agree"', body)  # requester can't approve their own request

    def test_landlord_agrees_contract_terminates(self):
        self._request(self.tenant_client)
        tr = TerminationRequest.objects.get()
        self._respond(self.landlord_client, tr, 'agree')
        tr.refresh_from_db()
        self.assertEqual(tr.status, 'agreed')
        self.assertEqual(self._status(), 'terminated')
        self.assertIn(self.REASON, self.tenancy.termination_reason)
        self.tenancy.booking.refresh_from_db()
        self.assertEqual(self.tenancy.booking.status, 'CANCELLED')
        self.assertTrue(Notification.objects.filter(user=self.tenant, kind='termination_agreed').exists())

    def test_landlord_disagrees_contract_continues_with_reply(self):
        self._request(self.tenant_client)
        tr = TerminationRequest.objects.get()
        self._respond(self.landlord_client, tr, 'decline', note='Please give 30 days notice per our agreement')
        tr.refresh_from_db()
        self.assertEqual((tr.status, tr.response_note), ('declined', 'Please give 30 days notice per our agreement'))
        self.assertEqual(self._status(), 'active')
        self.assertTrue(Notification.objects.filter(user=self.tenant, kind='termination_declined').exists())
        self.assertContains(self.tenant_client.get(reverse('bookings:my_contract')), 'Please give 30 days notice')

    def test_landlord_can_request_and_tenant_agrees(self):
        self._request(self.landlord_client, reason='Property is being sold at the end of the month')
        tr = TerminationRequest.objects.get()
        self.assertTrue(Notification.objects.filter(user=self.tenant, kind='termination_requested').exists())
        self.assertEqual(self._status(), 'active')
        self._respond(self.tenant_client, tr, 'agree')
        self.assertEqual(self._status(), 'terminated')
        self.assertTrue(Notification.objects.filter(user=self.landlord, kind='termination_agreed').exists())

    def test_requester_cannot_answer_own_request(self):
        self._request(self.landlord_client)
        tr = TerminationRequest.objects.get()
        self.assertEqual(self._respond(self.landlord_client, tr, 'agree').status_code, 404)
        self.assertEqual(self._status(), 'active')

    def test_outsiders_cannot_request_or_answer(self):
        outsider = Client()
        outsider.login(username='landlord2', password='pw')
        self.assertEqual(self._request(outsider).status_code, 404)
        self._request(self.tenant_client)
        tr = TerminationRequest.objects.get()
        self.assertEqual(self._respond(outsider, tr, 'agree').status_code, 404)
        self.assertEqual(self._status(), 'active')

    def test_only_one_open_request_at_a_time(self):
        self._request(self.tenant_client)
        self._request(self.landlord_client, reason='Another request while one is open')
        self.assertEqual(TerminationRequest.objects.filter(status='pending').count(), 1)
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            TerminationRequest.objects.create(tenancy=self.tenancy, requested_by=self.landlord, reason='x' * 20)

    def test_answering_twice_does_not_change_outcome(self):
        self._request(self.tenant_client)
        tr = TerminationRequest.objects.get()
        self._respond(self.landlord_client, tr, 'decline')
        self._respond(self.landlord_client, tr, 'agree')
        tr.refresh_from_db()
        self.assertEqual(tr.status, 'declined')
        self.assertEqual(self._status(), 'active')

    def test_requester_can_withdraw_others_cannot(self):
        self._request(self.tenant_client)
        tr = TerminationRequest.objects.get()
        url = reverse('bookings:withdraw_termination', kwargs={'request_id': tr.id})
        self.assertEqual(self.landlord_client.post(url).status_code, 404)
        self.tenant_client.post(url)
        tr.refresh_from_db()
        self.assertEqual(tr.status, 'withdrawn')
        self.assertTrue(Notification.objects.filter(user=self.landlord, kind='termination_withdrawn').exists())
        self._request(self.tenant_client)  # a fresh request is allowed after withdrawing
        self.assertEqual(TerminationRequest.objects.filter(status='pending').count(), 1)

    def test_answer_requires_post(self):
        self._request(self.tenant_client)
        tr = TerminationRequest.objects.get()
        response = self.landlord_client.get(reverse('bookings:respond_termination', kwargs={'request_id': tr.id}))
        self.assertEqual(response.status_code, 405)

    def test_cannot_request_on_ended_contract(self):
        self.tenancy.status = 'terminated'
        self.tenancy.save()
        self._request(self.tenant_client)
        self.assertFalse(TerminationRequest.objects.exists())

    def test_landlord_dashboard_shows_pending_request(self):
        self._request(self.tenant_client)
        body = self.landlord_client.get(reverse('core:dashboard')).content.decode()
        self.assertIn('Termination request', body)

    def test_verification_page_shows_mutual_agreement_trail(self):
        from apps.bookings.verification import confirmation_code
        self._request(self.tenant_client)
        self._respond(self.landlord_client, TerminationRequest.objects.get(), 'agree')
        response = Client().get(reverse('verify_by_code') + '?code=' + confirmation_code(self.tenancy))
        self.assertContains(response, 'ended early by agreement of both tenant and landlord')
        self.assertContains(response, 'Termination agreed by')


class NextTenantNoticeTests(TenancyTestBase):
    """A current tenant hears when someone wants (or has booked) their home
    for after their contract, so they can renew or talk to the landlord."""

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.tenancy = self.make_tenancy(today - timedelta(days=150), today + timedelta(days=20), status='ending_soon')
        self.after_end = self.tenancy.end_date + timedelta(days=5)
        self.seeker = Client()
        self.seeker.login(username='tenant2', password='pw')
        self.current = Client()
        self.current.login(username='tenant1', password='pw')
        self.landlord_client = Client()
        self.landlord_client.login(username='landlord1', password='pw')

    def _book(self, client, move_in, months=3):
        return client.post(reverse('bookings:create_booking', kwargs={'property_id': self.property.id}),
                           {'move_in_date': move_in.isoformat(), 'months': months})

    def _notes(self, user, kind):
        return Notification.objects.filter(user=user, kind=kind)

    def test_request_after_contract_notifies_current_tenant_without_naming_seeker(self):
        self._book(self.seeker, self.after_end)
        note = self._notes(self.tenant, 'booking_interest').get()
        self.assertIn(self.property.title, note.body)
        self.assertNotIn('tenant2', note.body)

    def test_no_notice_when_contract_already_over(self):
        self.tenancy.end_date = timezone.localdate() - timedelta(days=1)
        self.tenancy.save()
        self._book(self.seeker, timezone.localdate() + timedelta(days=10))
        self.assertFalse(self._notes(self.tenant, 'booking_interest').exists())

    def test_no_notice_to_yourself(self):
        self._book(self.current, self.after_end)
        self.assertFalse(self._notes(self.tenant, 'booking_interest').exists())

    def test_my_contract_banner_offers_renewal_and_message(self):
        self._book(self.seeker, self.after_end)
        body = self.current.get(reverse('bookings:my_contract')).content.decode()
        self.assertIn('Someone has asked to rent this home', body)
        self.assertIn(reverse('bookings:request_renewal', kwargs={'tenancy_id': self.tenancy.id}), body)
        self.assertIn(reverse('messaging:start_conversation', kwargs={'property_id': self.property.id}), body)
        self.assertNotIn('tenant2', body)

    def test_approval_tells_current_tenant_renewal_is_ruled_out(self):
        self._book(self.seeker, self.after_end)
        booking = Booking.objects.get(tenant=self.other_tenant)
        self.landlord_client.post(reverse('bookings:approve_booking', kwargs={'booking_id': booking.id}))
        self.assertTrue(self._notes(self.tenant, 'property_booked_next').exists())
        body = self.current.get(reverse('bookings:my_contract')).content.decode()
        self.assertIn('This home is booked by another tenant', body)

    def test_landlord_warned_when_current_tenant_wants_to_renew(self):
        self.tenancy.renewal_requested = True
        self.tenancy.save()
        self._book(self.seeker, self.after_end)
        body = self.landlord_client.get(reverse('bookings:landlord_bookings')).content.decode()
        self.assertIn('The current tenant has asked to renew', body)

    def test_renewal_request_and_answers_are_notified(self):
        self.current.get(reverse('bookings:request_renewal', kwargs={'tenancy_id': self.tenancy.id}))
        self.assertTrue(self._notes(self.landlord, 'renewal_requested').exists())
        self.landlord_client.get(reverse('bookings:decline_renewal', kwargs={'tenancy_id': self.tenancy.id}))
        self.assertTrue(self._notes(self.tenant, 'renewal_declined').exists())
        self.current.get(reverse('bookings:request_renewal', kwargs={'tenancy_id': self.tenancy.id}))
        self.landlord_client.get(reverse('bookings:approve_renewal', kwargs={'tenancy_id': self.tenancy.id}))
        self.assertTrue(self._notes(self.tenant, 'renewal_approved').exists())

    def test_long_property_title_cannot_break_booking(self):
        self.property.title = 'Spacious family home ' * 9  # ~190 chars, pushes notifications past 255
        self.property.save()
        response = self._book(self.seeker, self.after_end)
        self.assertEqual(response.status_code, 302)
        note = self._notes(self.tenant, 'booking_interest').get()
        self.assertLessEqual(len(note.body), 255)
