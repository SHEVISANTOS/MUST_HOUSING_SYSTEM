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
