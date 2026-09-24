from datetime import timedelta

from django.test import TestCase, Client
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from apps.users.models import User
from apps.properties.models import Property
from apps.bookings.models import Booking, Tenancy


class SeekerPrivacyTests(TestCase):
    """
    Seekers (anyone browsing listings) must never see a tenant's name or
    phone number - only that a property is occupied and until when. See
    templates/bookings/_tenancy_status_badge.html and
    _availability_timeline.html, which only ever read dates/status.
    """

    def setUp(self):
        self.landlord = User.objects.create_user(username='landlord', password='pw', role='LANDLORD')
        self.seeker = User.objects.create_user(username='seeker', password='pw', role='TENANT')
        self.tenant = User.objects.create_user(
            username='secrettenant', password='pw', role='TENANT',
            phone='0799999999', first_name='Confidential', last_name='Person',
        )
        self.property = Property.objects.create(
            landlord=self.landlord, title='Privacy Test Property', location='Mwanza',
            property_type='2BR', monthly_rent=100000, distance_from_center_km=1.0,
        )
        today = timezone.localdate()
        booking = Booking.objects.create(
            property=self.property, tenant=self.tenant,
            move_in_date=today - timedelta(days=10), move_out_date=today + timedelta(days=170),
            status='CONFIRMED',
        )
        Tenancy.objects.create(
            booking=booking, property=self.property, tenant=self.tenant,
            start_date=booking.move_in_date, end_date=booking.move_out_date,
            duration_months=6, status='active',
        )
        self.client = Client()
        self.client.login(username='seeker', password='pw')

    def test_listing_page_never_leaks_tenant_details(self):
        response = self.client.get(reverse('properties:list'))
        body = response.content.decode()
        self.assertIn('Available from', body)  # the occupancy badge did render
        self.assertNotIn('secrettenant', body)
        self.assertNotIn('0799999999', body)
        self.assertNotIn('Confidential', body)

    def test_detail_page_never_leaks_tenant_details(self):
        response = self.client.get(reverse('properties:detail', kwargs={'pk': self.property.pk}))
        body = response.content.decode()
        self.assertNotIn('secrettenant', body)
        self.assertNotIn('0799999999', body)
        self.assertNotIn('Confidential', body)


class ListingQueryCountTests(TestCase):
    """The occupancy badge on the listing page must not cause N+1 queries -
    see Property.get_current_tenancy()'s prefetch-aware branch."""

    def setUp(self):
        self.landlord = User.objects.create_user(username='landlord', password='pw', role='LANDLORD')
        self.tenant = User.objects.create_user(username='tenant', password='pw', role='TENANT')
        self.seeker = User.objects.create_user(username='seeker2', password='pw', role='TENANT')
        self.client = Client()
        self.client.login(username='seeker2', password='pw')

        today = timezone.localdate()
        for i in range(6):
            prop = Property.objects.create(
                landlord=self.landlord, title=f'QC Property {i}', location='Mwanza',
                property_type='2BR', monthly_rent=100000, distance_from_center_km=1.0,
            )
            if i % 2 == 0:
                booking = Booking.objects.create(
                    property=prop, tenant=self.tenant,
                    move_in_date=today - timedelta(days=10), move_out_date=today + timedelta(days=170),
                    status='CONFIRMED',
                )
                Tenancy.objects.create(
                    booking=booking, property=prop, tenant=self.tenant,
                    start_date=booking.move_in_date, end_date=booking.move_out_date,
                    duration_months=6, status='active',
                )

    def test_query_count_does_not_scale_with_property_count(self):
        with CaptureQueriesContext(connection) as ctx_small:
            self.client.get(reverse('properties:list'))
        baseline = len(ctx_small.captured_queries)

        today = timezone.localdate()
        for i in range(6, 18):
            prop = Property.objects.create(
                landlord=self.landlord, title=f'QC Property {i}', location='Mwanza',
                property_type='2BR', monthly_rent=100000, distance_from_center_km=1.0,
            )
            if i % 2 == 0:
                booking = Booking.objects.create(
                    property=prop, tenant=self.tenant,
                    move_in_date=today - timedelta(days=10), move_out_date=today + timedelta(days=170),
                    status='CONFIRMED',
                )
                Tenancy.objects.create(
                    booking=booking, property=prop, tenant=self.tenant,
                    start_date=booking.move_in_date, end_date=booking.move_out_date,
                    duration_months=6, status='active',
                )

        with CaptureQueriesContext(connection) as ctx_large:
            self.client.get(reverse('properties:list'))

        self.assertEqual(baseline, len(ctx_large.captured_queries))


class PublicBrowsingTests(TestCase):
    """Anyone, including visitors without an account, can browse listings
    and property detail pages; booking still requires sign-in."""

    def setUp(self):
        self.landlord = User.objects.create_user(
            username='pub_landlord', password='pw', role='LANDLORD',
            email='landlord@example.com', phone='0711223344',
        )
        self.tenant = User.objects.create_user(username='pub_tenant', password='pw', role='TENANT')
        self.other_landlord = User.objects.create_user(username='pub_landlord2', password='pw', role='LANDLORD')
        self.property = Property.objects.create(
            landlord=self.landlord, title='Public Browsing Property', location='Mwanza',
            property_type='2BR', monthly_rent=150000, distance_from_center_km=1.0,
        )
        self.delisted_property = Property.objects.create(
            landlord=self.landlord, title='Delisted Property', location='Mwanza',
            property_type='1BR', monthly_rent=100000, distance_from_center_km=1.0,
            is_available=False,
        )
        self.anon = Client()

    def test_anonymous_gets_200_on_listing(self):
        self.assertEqual(self.anon.get(reverse('properties:list')).status_code, 200)

    def test_anonymous_gets_200_on_filtered_listing(self):
        response = self.anon.get(reverse('properties:list'), {'available_now': '1', 'q': 'Public'})
        self.assertEqual(response.status_code, 200)

    def test_anonymous_gets_200_on_detail(self):
        response = self.anon.get(reverse('properties:detail', kwargs={'pk': self.property.pk}))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_detail_shows_sign_in_to_book_not_contact_info(self):
        response = self.anon.get(reverse('properties:detail', kwargs={'pk': self.property.pk}))
        body = response.content.decode()
        self.assertIn('Sign in to Book', body)
        self.assertNotIn('0711223344', body)
        self.assertNotIn('landlord@example.com', body)

    def test_signed_in_tenant_sees_booking_form_and_contact_details(self):
        client = Client()
        client.login(username='pub_tenant', password='pw')
        response = client.get(reverse('properties:detail', kwargs={'pk': self.property.pk}))
        body = response.content.decode()
        self.assertIn('Book This Property', body)
        self.assertIn('0711223344', body)
        self.assertIn('landlord@example.com', body)

    def test_landlord_sees_no_booking_button(self):
        client = Client()
        client.login(username='pub_landlord2', password='pw')  # a landlord, not this property's owner
        response = client.get(reverse('properties:detail', kwargs={'pk': self.property.pk}))
        body = response.content.decode()
        self.assertIn('Booking is for student accounts', body)
        self.assertNotIn('class="book-btn"', body)

    def test_delisted_property_shows_no_booking_option_to_anyone(self):
        for client, label in [(self.anon, 'anonymous'), (None, 'tenant')]:
            c = client or Client()
            if client is None:
                c.login(username='pub_tenant', password='pw')
            response = c.get(reverse('properties:detail', kwargs={'pk': self.delisted_property.pk}))
            body = response.content.decode()
            self.assertNotIn('class="book-btn"', body, f'booking option leaked for {label}')
            self.assertIn('Not Active', body)

    def test_listing_query_count_same_for_anonymous_and_signed_in(self):
        tenant_client = Client()
        tenant_client.login(username='pub_tenant', password='pw')

        with CaptureQueriesContext(connection) as anon_ctx:
            self.anon.get(reverse('properties:list'))
        with CaptureQueriesContext(connection) as auth_ctx:
            tenant_client.get(reverse('properties:list'))

        # Signed-in adds exactly 2 queries (session lookup + loading the
        # user, both from AuthenticationMiddleware, verified empirically -
        # not assumed) on top of the anonymous baseline; the property-
        # listing work itself must be identical either way.
        self.assertEqual(len(anon_ctx.captured_queries) + 2, len(auth_ctx.captured_queries))
