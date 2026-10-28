from datetime import timedelta

from django.test import TestCase, Client
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.users.models import User
from apps.properties.models import Property, PropertyImage
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
        self.assertIn('Free from', body)  # the occupancy badge did render
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

    def test_signed_in_tenant_without_confirmed_booking_sees_no_phone(self):
        # Privacy: landlord phone and exact address are only shown once this
        # tenant has an actual CONFIRMED/PAID/COMPLETED booking for this
        # specific property - just being signed in isn't enough, and email
        # is unaffected (the brief only calls out phone + address).
        client = Client()
        client.login(username='pub_tenant', password='pw')
        response = client.get(reverse('properties:detail', kwargs={'pk': self.property.pk}))
        body = response.content.decode()
        self.assertIn('Book This Property', body)
        self.assertNotIn('0711223344', body)
        self.assertIn('landlord@example.com', body)
        self.assertIn('Phone shared once your booking is confirmed', body)

    def test_tenant_with_confirmed_booking_sees_phone_and_exact_map(self):
        self.property.latitude = -2.516
        self.property.longitude = 32.917
        self.property.save()
        Booking.objects.create(
            property=self.property, tenant=self.tenant,
            move_in_date=timezone.localdate(), move_out_date=timezone.localdate() + timedelta(days=90),
            status='CONFIRMED',
        )
        client = Client()
        client.login(username='pub_tenant', password='pw')
        response = client.get(reverse('properties:detail', kwargs={'pk': self.property.pk}))
        body = response.content.decode()
        self.assertIn('0711223344', body)
        self.assertNotIn('approximate', body.lower())
        self.assertIn('-2.516000', body)  # exact coordinate, not rounded to -2.52

    def test_landlord_sees_own_phone_and_exact_map_without_a_booking(self):
        self.property.latitude = -2.516
        self.property.longitude = 32.917
        self.property.save()
        client = Client()
        client.login(username='pub_landlord', password='pw')
        response = client.get(reverse('properties:detail', kwargs={'pk': self.property.pk}))
        body = response.content.decode()
        self.assertIn('0711223344', body)
        self.assertIn('-2.516000', body)

    def test_landlord_sees_no_booking_button(self):
        client = Client()
        client.login(username='pub_landlord2', password='pw')  # a landlord, not this property's owner
        response = client.get(reverse('properties:detail', kwargs={'pk': self.property.pk}))
        body = response.content.decode()
        self.assertIn('Booking is only available for tenant accounts', body)
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

        # Signed-in adds exactly 4 queries on top of the anonymous baseline,
        # verified empirically - not assumed: session lookup + loading the
        # user (both from AuthenticationMiddleware), plus one query each
        # from the saved_property_ids and unread_message_count context
        # processors (apps/properties/context_processors.py and
        # apps/messaging/context_processors.py) - both only hit the DB for
        # authenticated requests, since the sidebar that uses them renders
        # on every page. The property-listing work itself must be
        # identical either way.
        self.assertEqual(len(anon_ctx.captured_queries) + 4, len(auth_ctx.captured_queries))


class PropertyEditPauseTests(TestCase):
    """Landlord-only Edit and Pause actions on their own listings."""

    def setUp(self):
        self.landlord = User.objects.create_user(username='ep_landlord', password='pw', role='LANDLORD')
        self.other_landlord = User.objects.create_user(username='ep_landlord2', password='pw', role='LANDLORD')
        self.tenant = User.objects.create_user(username='ep_tenant', password='pw', role='TENANT')
        self.property = Property.objects.create(
            landlord=self.landlord, title='Editable Property', location='Mwanza',
            property_type='2BR', monthly_rent=150000, distance_from_center_km=1.0,
        )

    def test_owner_can_view_edit_form(self):
        client = Client()
        client.login(username='ep_landlord', password='pw')
        response = client.get(reverse('properties:edit', kwargs={'pk': self.property.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Editable Property', response.content.decode())

    def test_owner_can_submit_edit(self):
        client = Client()
        client.login(username='ep_landlord', password='pw')
        response = client.post(reverse('properties:edit', kwargs={'pk': self.property.pk}), {
            'title': 'Updated Title', 'description': 'Updated description',
            'property_type': '2BR', 'location': 'Mwanza',
            'distance_from_center_km': 1.0, 'monthly_rent': 175000,
            'months_per_payment': 1, 'is_available': 'on',
        })
        self.assertRedirects(response, reverse('properties:detail', kwargs={'pk': self.property.pk}))
        self.property.refresh_from_db()
        self.assertEqual(self.property.title, 'Updated Title')
        self.assertEqual(self.property.monthly_rent, 175000)

    def test_non_owner_landlord_cannot_edit(self):
        client = Client()
        client.login(username='ep_landlord2', password='pw')
        response = client.post(reverse('properties:edit', kwargs={'pk': self.property.pk}), {
            'title': 'Hijacked', 'description': 'x', 'property_type': '2BR',
            'location': 'Mwanza', 'distance_from_center_km': 1.0, 'monthly_rent': 1,
            'months_per_payment': 1,
        })
        self.assertRedirects(response, reverse('properties:my_properties'))
        self.property.refresh_from_db()
        self.assertEqual(self.property.title, 'Editable Property')

    def test_tenant_cannot_edit(self):
        client = Client()
        client.login(username='ep_tenant', password='pw')
        response = client.get(reverse('properties:edit', kwargs={'pk': self.property.pk}))
        self.assertEqual(response.status_code, 302)
        self.property.refresh_from_db()
        self.assertEqual(self.property.title, 'Editable Property')

    def test_owner_can_pause_and_reactivate(self):
        client = Client()
        client.login(username='ep_landlord', password='pw')

        response = client.post(reverse('properties:pause', kwargs={'pk': self.property.pk}))
        self.assertRedirects(response, reverse('properties:my_properties'))
        self.property.refresh_from_db()
        self.assertEqual(self.property.status, 'paused')
        self.assertFalse(self.property.is_available)

        response = client.post(reverse('properties:pause', kwargs={'pk': self.property.pk}))
        self.assertRedirects(response, reverse('properties:my_properties'))
        self.property.refresh_from_db()
        self.assertEqual(self.property.status, 'live')
        self.assertTrue(self.property.is_available)

    def test_paused_property_excluded_from_public_listing(self):
        self.property.status = 'paused'
        self.property.is_available = False
        self.property.save()

        response = Client().get(reverse('properties:list'))
        self.assertNotIn('Editable Property', response.content.decode())

    def test_non_owner_cannot_pause(self):
        client = Client()
        client.login(username='ep_landlord2', password='pw')
        response = client.post(reverse('properties:pause', kwargs={'pk': self.property.pk}))
        self.assertRedirects(response, reverse('properties:my_properties'))
        self.property.refresh_from_db()
        self.assertEqual(self.property.status, 'live')

    def test_pause_requires_post(self):
        client = Client()
        client.login(username='ep_landlord', password='pw')
        response = client.get(reverse('properties:pause', kwargs={'pk': self.property.pk}))
        self.assertEqual(response.status_code, 405)


# A minimal valid 1x1 transparent PNG, for image-upload tests - Pillow (via
# Django's ImageField) validates uploaded files are real images, so an
# arbitrary byte string isn't enough.
_ONE_PX_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDATx\x9cc\x64'
    b'\x60\x00\x00\x00\x05\x00\x01\x1f\xcd\xbb\xd3\x00\x00\x00\x00IEND\xaeB`\x82'
)


class PropertyWizardTests(TestCase):
    """The 5-step add/edit wizard - each step POST should persist straight
    to the DB (the 'real autosave'), not just hold client-side state."""

    def setUp(self):
        self.landlord = User.objects.create_user(username='wiz_landlord', password='pw', role='LANDLORD')
        self.other_landlord = User.objects.create_user(username='wiz_landlord2', password='pw', role='LANDLORD')
        self.tenant = User.objects.create_user(username='wiz_tenant', password='pw', role='TENANT')
        self.client = Client()
        self.client.login(username='wiz_landlord', password='pw')

    def test_start_creates_draft_and_redirects_to_basics(self):
        response = self.client.get(reverse('properties:wizard_start'))
        prop = Property.objects.get(landlord=self.landlord)
        self.assertEqual(prop.status, 'draft')
        self.assertFalse(prop.is_available)
        self.assertRedirects(response, reverse('properties:wizard_step', kwargs={'pk': prop.pk, 'step': 'basics'}))

    def test_tenant_cannot_start_wizard(self):
        client = Client()
        client.login(username='wiz_tenant', password='pw')
        response = client.get(reverse('properties:wizard_start'), follow=True)
        self.assertRedirects(response, reverse('core:dashboard'))
        self.assertFalse(Property.objects.exists())

    def test_basics_step_saves_and_advances_to_photos(self):
        self.client.get(reverse('properties:wizard_start'))
        prop = Property.objects.get(landlord=self.landlord)

        response = self.client.post(
            reverse('properties:wizard_step', kwargs={'pk': prop.pk, 'step': 'basics'}),
            {'title': 'Cozy Bedsitter', 'description': 'Near the market', 'property_type': 'BEDSITTER', 'location': 'Nyamagana'},
        )
        self.assertRedirects(response, reverse('properties:wizard_step', kwargs={'pk': prop.pk, 'step': 'photos'}))

        # The autosave: a fresh query on the DB row reflects step 1's data
        # even though the wizard hasn't been finished or published yet.
        prop.refresh_from_db()
        self.assertEqual(prop.title, 'Cozy Bedsitter')
        self.assertEqual(prop.status, 'draft')

    def test_photos_step_uploads_and_sets_primary(self):
        self.client.get(reverse('properties:wizard_start'))
        prop = Property.objects.get(landlord=self.landlord)

        image = SimpleUploadedFile('room.png', _ONE_PX_PNG, content_type='image/png')
        response = self.client.post(
            reverse('properties:wizard_step', kwargs={'pk': prop.pk, 'step': 'photos'}),
            {'property_images': [image]},
        )
        self.assertRedirects(response, reverse('properties:wizard_step', kwargs={'pk': prop.pk, 'step': 'location'}))
        self.assertEqual(PropertyImage.objects.filter(property=prop).count(), 1)
        self.assertTrue(PropertyImage.objects.get(property=prop).is_primary)

    def test_delete_photo(self):
        self.client.get(reverse('properties:wizard_start'))
        prop = Property.objects.get(landlord=self.landlord)
        image = PropertyImage.objects.create(
            property=prop, image=SimpleUploadedFile('room.png', _ONE_PX_PNG, content_type='image/png'), is_primary=True,
        )

        response = self.client.post(reverse('properties:wizard_delete_image', kwargs={'pk': prop.pk, 'image_id': image.id}))
        self.assertRedirects(response, reverse('properties:wizard_step', kwargs={'pk': prop.pk, 'step': 'photos'}))
        self.assertFalse(PropertyImage.objects.filter(pk=image.id).exists())

    def test_location_and_rent_steps_save(self):
        self.client.get(reverse('properties:wizard_start'))
        prop = Property.objects.get(landlord=self.landlord)

        self.client.post(
            reverse('properties:wizard_step', kwargs={'pk': prop.pk, 'step': 'location'}),
            {'distance_from_center_km': 3.2, 'latitude': -2.516, 'longitude': 32.898},
        )
        self.client.post(
            reverse('properties:wizard_step', kwargs={'pk': prop.pk, 'step': 'rent'}),
            {'monthly_rent': 120000, 'months_per_payment': 1},
        )
        prop.refresh_from_db()
        self.assertEqual(prop.distance_from_center_km, 3.2)
        self.assertEqual(prop.monthly_rent, 120000)
        self.assertEqual(prop.status, 'draft')  # still a draft until the Review step publishes it

    def test_review_step_publishes_draft(self):
        self.client.get(reverse('properties:wizard_start'))
        prop = Property.objects.get(landlord=self.landlord)

        response = self.client.post(
            reverse('properties:wizard_step', kwargs={'pk': prop.pk, 'step': 'review'}),
            {'action': 'publish'},
        )
        self.assertRedirects(response, reverse('properties:detail', kwargs={'pk': prop.pk}))
        prop.refresh_from_db()
        self.assertEqual(prop.status, 'live')
        self.assertTrue(prop.is_available)

    def test_review_step_on_already_live_property_does_not_change_status(self):
        prop = Property.objects.create(
            landlord=self.landlord, title='Existing Place', location='Mwanza',
            property_type='2BR', monthly_rent=200000, distance_from_center_km=2.0,
            status='live', is_available=True,
        )
        response = self.client.post(
            reverse('properties:wizard_step', kwargs={'pk': prop.pk, 'step': 'review'}),
            {'action': 'save'},
        )
        self.assertRedirects(response, reverse('properties:detail', kwargs={'pk': prop.pk}))
        prop.refresh_from_db()
        self.assertEqual(prop.status, 'live')

    def test_non_owner_cannot_access_wizard_step(self):
        self.client.get(reverse('properties:wizard_start'))
        prop = Property.objects.get(landlord=self.landlord)

        other_client = Client()
        other_client.login(username='wiz_landlord2', password='pw')
        response = other_client.get(reverse('properties:wizard_step', kwargs={'pk': prop.pk, 'step': 'basics'}), follow=True)
        self.assertRedirects(response, reverse('properties:my_properties'))

    def test_unknown_step_404s(self):
        self.client.get(reverse('properties:wizard_start'))
        prop = Property.objects.get(landlord=self.landlord)
        response = self.client.get(reverse('properties:wizard_step', kwargs={'pk': prop.pk, 'step': 'bogus'}))
        self.assertEqual(response.status_code, 404)

    def test_draft_shows_finish_listing_button_in_my_properties(self):
        self.client.get(reverse('properties:wizard_start'))
        response = self.client.get(reverse('properties:my_properties'))
        self.assertIn('Finish listing', response.content.decode())
