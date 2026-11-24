import tempfile
from datetime import timedelta

from django.test import TestCase, Client, override_settings
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
        self.landlord = User.objects.create_user(username='landlord', password='pw', role='LANDLORD', is_verified=True)
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
        self.landlord = User.objects.create_user(username='landlord', password='pw', role='LANDLORD', is_verified=True)
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
            username='pub_landlord', password='pw', role='LANDLORD', is_verified=True,
            email='landlord@example.com', phone='0711223344',
        )
        self.tenant = User.objects.create_user(username='pub_tenant', password='pw', role='TENANT')
        self.other_landlord = User.objects.create_user(username='pub_landlord2', password='pw', role='LANDLORD', is_verified=True)
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

        # Signed-in adds exactly 5 queries on top of the anonymous baseline,
        # verified empirically - not assumed: session lookup + loading the
        # user (both from AuthenticationMiddleware), plus one query each
        # from the saved_property_ids, unread_message_count and
        # unread_notification_count context processors
        # (apps/properties/context_processors.py,
        # apps/messaging/context_processors.py and
        # apps/notifications/context_processors.py) - all three only hit
        # the DB for authenticated requests, since the sidebar/top bar that
        # use them render on every page. The property-listing work itself
        # must be identical either way.
        self.assertEqual(len(anon_ctx.captured_queries) + 5, len(auth_ctx.captured_queries))


class PropertyEditPauseTests(TestCase):
    """Landlord-only Edit and Pause actions on their own listings."""

    def setUp(self):
        self.landlord = User.objects.create_user(username='ep_landlord', password='pw', role='LANDLORD', is_verified=True)
        self.other_landlord = User.objects.create_user(username='ep_landlord2', password='pw', role='LANDLORD', is_verified=True)
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
        self.landlord = User.objects.create_user(username='wiz_landlord', password='pw', role='LANDLORD', is_verified=True)
        self.other_landlord = User.objects.create_user(username='wiz_landlord2', password='pw', role='LANDLORD', is_verified=True)
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


class ShareButtonTests(TestCase):
    def setUp(self):
        landlord = User.objects.create_user(username='share_landlord', password='pw', role='LANDLORD', is_verified=True)
        self.property = Property.objects.create(
            landlord=landlord, title='Tom & Jerry "Studio"', location='Ilemela',
            property_type='2BR', monthly_rent=150000, distance_from_center_km=1.0,
        )
        self.url = reverse('properties:detail', kwargs={'pk': self.property.pk})

    def test_anonymous_visitor_sees_share_links(self):
        body = Client().get(self.url).content.decode()
        for host in ('wa.me', 'facebook.com/sharer', 'twitter.com/intent', 't.me/share', 'mailto:'):
            self.assertIn(host, body)
        self.assertIn('Copy link', body)

    def test_share_links_encode_title_and_page_url_once(self):
        links = dict(Client().get(self.url).context['share_links'])
        page_url = f'http://testserver{self.url}'
        from urllib.parse import quote
        self.assertIn(quote(page_url, safe=''), links['Facebook'])
        # '&' and quotes in the title are percent-encoded, not HTML-escaped
        self.assertIn('Tom%20%26%20Jerry%20%22Studio%22', links['WhatsApp'])
        self.assertIn('150%2C000', links['WhatsApp'])
        self.assertNotIn('&amp;', links['WhatsApp'])

    def test_share_options_visible_without_extra_click_and_include_sms(self):
        response = Client().get(self.url)
        body = response.content.decode()
        self.assertIn('Share with friends', body)
        self.assertNotIn('id="sharePanel" hidden', body)
        self.assertTrue(dict(response.context['share_links'])['SMS'].startswith('sms:?&body='))

    def test_listing_cards_have_share_button_for_everyone(self):
        body = Client().get(reverse('properties:list')).content.decode()
        self.assertIn('shareCard(event, this)', body)
        self.assertIn('2 Bedroom in Ilemela - TZS 150,000/month', body)

    def test_share_data_available_for_native_share_sheet(self):
        body = Client().get(self.url).content.decode()
        self.assertIn('id="share-data"', body)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LinkPreviewImageTests(TestCase):
    """og:image drives the picture WhatsApp/Facebook show for a shared link."""

    def setUp(self):
        landlord = User.objects.create_user(username='og_landlord', password='pw', role='LANDLORD', is_verified=True)
        self.property = Property.objects.create(
            landlord=landlord, title='Preview House', location='Ilemela',
            property_type='2BR', monthly_rent=150000, distance_from_center_km=1.0,
        )
        self.url = reverse('properties:detail', kwargs={'pk': self.property.pk})

    def _add_photo(self, name, primary=False):
        return PropertyImage.objects.create(
            property=self.property, is_primary=primary,
            image=SimpleUploadedFile(name, _ONE_PX_PNG, content_type='image/png'),
        )

    def _og_image(self):
        return Client().get(self.url).context['og_image_url']

    def test_no_photos_falls_back_to_logo(self):
        self.assertTrue(self._og_image().endswith('/photo.jpg?v=0'))

    def test_uses_cover_photo_as_absolute_url(self):
        photo = self._add_photo('cover.png', primary=True)
        og = self._og_image()
        self.assertEqual(og, f'http://testserver/properties/{self.property.pk}/photo.jpg?v={photo.pk}')

    def test_prefers_cover_over_first_photo(self):
        self._add_photo('first.png')
        cover = self._add_photo('cover.png', primary=True)
        self.assertTrue(self._og_image().endswith(f'?v={cover.pk}'))

    def test_without_cover_matches_listing_card_photo(self):
        self._add_photo('older.png')
        self._add_photo('newer.png')
        card_photo = self.property.images.all()[0]  # what _listing_card.html shows
        self.assertTrue(self._og_image().endswith(f'?v={card_photo.pk}'))


class AllHousesChipTests(TestCase):
    def _chip(self, query=''):
        body = Client().get(reverse('properties:list') + query).content.decode()
        start = body.index('🏠 All houses')
        return body[body.rindex('<a ', 0, start):start]

    def test_active_when_no_filters(self):
        chip = self._chip()
        self.assertIn(f'href="{reverse("properties:list")}"', chip)
        self.assertIn('active', chip)

    def test_inactive_and_clears_filters_when_filtered(self):
        for query in ('?max_price=500000', '?available_now=1', '?q=house', '?location=Nyegezi'):
            chip = self._chip(query)
            self.assertNotIn('active', chip, query)
            self.assertIn(f'href="{reverse("properties:list")}"', chip, query)


class LandlordApprovalTests(TestCase):
    """New landlords' listings stay hidden until an admin verifies them."""

    def setUp(self):
        from apps.notifications.models import Notification
        self.Notification = Notification
        self.admin = User.objects.create_user(username='appr_admin', password='pw', role='ADMIN', is_superuser=True)
        self.newbie = User.objects.create_user(username='appr_new', password='pw', role='LANDLORD', phone='0712000000')
        self.tenant = User.objects.create_user(username='appr_tenant', password='pw', role='TENANT')
        self.prop = Property.objects.create(
            landlord=self.newbie, title='Unverified Home', location='Nyegezi',
            property_type='1BR', monthly_rent=90000, distance_from_center_km=2.0,
        )

    def _client(self, username):
        c = Client()
        c.login(username=username, password='pw')
        return c

    def test_hidden_from_search_detail_booking_and_messages(self):
        self.assertNotContains(Client().get(reverse('properties:list')), 'Nyegezi')
        self.assertEqual(Client().get(reverse('properties:detail', args=[self.prop.pk])).status_code, 404)
        tenant = self._client('appr_tenant')
        self.assertEqual(tenant.get(reverse('bookings:create_booking', args=[self.prop.pk])).status_code, 404)
        self.assertEqual(tenant.get(reverse('messaging:start_conversation', args=[self.prop.pk])).status_code, 404)

    def test_owner_and_admin_can_still_open_it(self):
        owner = self._client('appr_new').get(reverse('properties:detail', args=[self.prop.pk]))
        self.assertContains(owner, 'Your listings are not public yet')
        self.assertEqual(self._client('appr_admin').get(reverse('properties:detail', args=[self.prop.pk])).status_code, 200)

    def test_verifying_landlord_makes_listing_public_and_tells_them(self):
        self._client('appr_admin').post(reverse('core:verify_user', args=[self.newbie.id]))
        self.assertContains(Client().get(reverse('properties:list')), 'Nyegezi')
        detail = Client().get(reverse('properties:detail', args=[self.prop.pk]))
        self.assertEqual(detail.status_code, 200)
        note = self.Notification.objects.get(user=self.newbie, kind='account_verified')
        self.assertIn('visible to renters', note.body)

    def test_publishing_while_unverified_warns_landlord_and_alerts_admin_once(self):
        owner = self._client('appr_new')
        self.prop.status, self.prop.is_available = 'paused', False
        self.prop.save()
        response = owner.post(reverse('properties:pause', args=[self.prop.pk]), follow=True)
        self.assertContains(response, "won&#x27;t see it until VOT verifies")
        owner.post(reverse('properties:pause', args=[self.prop.pk]))
        owner.post(reverse('properties:pause', args=[self.prop.pk]))
        alerts = self.Notification.objects.filter(user=self.admin, kind='landlord_awaiting_verification')
        self.assertEqual(alerts.count(), 1)
        queue = self._client('appr_admin').get(reverse('core:verification_queue'))
        self.assertContains(queue, f'id="landlord-{self.newbie.id}"')
        self.assertContains(queue, reverse('properties:detail', args=[self.prop.pk]))

    def test_tenant_with_existing_booking_keeps_access(self):
        from apps.bookings.models import Booking
        from datetime import date, timedelta
        Booking.objects.create(property=self.prop, tenant=self.tenant, move_in_date=date.today(),
                               move_out_date=date.today() + timedelta(days=60), status='PENDING')
        self.assertEqual(self._client('appr_tenant').get(reverse('properties:detail', args=[self.prop.pk])).status_code, 200)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ShareImageTests(TestCase):
    """Shared links and phone shares carry the property's photo, sized so
    WhatsApp (which drops preview images over ~300 KB) still shows it."""

    def setUp(self):
        self.landlord = User.objects.create_user(username='si_landlord', password='pw', role='LANDLORD', is_verified=True)
        self.property = Property.objects.create(
            landlord=self.landlord, title='Photo House', location='Ilemela',
            property_type='2BR', monthly_rent=150000, distance_from_center_km=1.0,
        )
        self.url = reverse('properties:share_image', args=[self.property.pk])

    def _big_photo(self):
        import io, os
        from PIL import Image
        img = Image.frombytes('RGB', (3000, 2000), os.urandom(3000 * 2000 * 3))  # noise: worst case for JPEG
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        return PropertyImage.objects.create(
            property=self.property, is_primary=True,
            image=SimpleUploadedFile('big.png', buf.getvalue(), content_type='image/png'),
        )

    def test_large_cover_is_shrunk_below_whatsapp_limit(self):
        import io
        from PIL import Image
        from apps.properties.views import SHARE_IMAGE_MAX_BYTES
        self._big_photo()
        response = Client().get(self.url)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertLessEqual(len(response.content), SHARE_IMAGE_MAX_BYTES)
        self.assertLessEqual(max(Image.open(io.BytesIO(response.content)).size), 1200)
        # second request is served from the cached copy, byte for byte
        self.assertEqual(Client().get(self.url).content, response.content)

    def test_photo_less_listing_gets_small_logo(self):
        from apps.properties.views import SHARE_IMAGE_MAX_BYTES
        response = Client().get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.content), SHARE_IMAGE_MAX_BYTES)

    def test_detail_page_points_previews_and_share_button_at_it(self):
        photo = self._big_photo()
        body = Client().get(reverse('properties:detail', args=[self.property.pk])).content.decode()
        self.assertIn(f'content="http://testserver{self.url}?v={photo.pk}"', body)
        self.assertIn(f"preloadSharePhoto('{self.url}?v\\u003D{photo.pk}')", body)  # escapejs turns = into \u003D
        cards = Client().get(reverse('properties:list')).content.decode()
        self.assertIn(f'data-share-photo="{self.url}?v={photo.pk}"', cards)

    def test_hidden_listing_photo_not_served(self):
        self.landlord.is_verified = False
        self.landlord.save()
        self.assertEqual(Client().get(self.url).status_code, 404)


class ReviewTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.bookings.models import Booking, Tenancy
        today = timezone.localdate()
        self.landlord = User.objects.create_user(username='rv_landlord', password='pw', role='LANDLORD', is_verified=True)
        self.tenant = User.objects.create_user(username='rv_tenant', password='pw', role='TENANT')
        self.other = User.objects.create_user(username='rv_other', password='pw', role='TENANT')
        self.prop = Property.objects.create(landlord=self.landlord, title='Review Home', location='Buswelu',
                                            property_type='1BR', monthly_rent=100000, distance_from_center_km=1)
        booking = Booking.objects.create(property=self.prop, tenant=self.tenant, status='COMPLETED',
                                         move_in_date=today - timedelta(days=90), move_out_date=today - timedelta(days=1))
        self.tenancy = Tenancy.objects.create(booking=booking, property=self.prop, tenant=self.tenant,
                                              start_date=today - timedelta(days=90), end_date=today - timedelta(days=1),
                                              duration_months=3, status='ended')
        self.url = reverse('properties:write_review', args=[self.tenancy.id])

    def _login(self, username):
        c = Client()
        c.login(username=username, password='pw')
        return c

    def _post(self, client):
        return client.post(self.url, {'home_rating': 4, 'landlord_rating': 5, 'comment': 'Water every day, kind landlord.'})

    def test_former_tenant_reviews_once_and_it_shows_everywhere(self):
        tenant = self._login('rv_tenant')
        self.assertContains(tenant.get(reverse('bookings:my_bookings')), 'Rate this home')
        self._post(tenant)
        self._post(tenant)
        self.assertEqual(self.prop.reviews.count(), 1)
        detail = Client().get(reverse('properties:detail', args=[self.prop.pk]))
        self.assertContains(detail, 'Water every day, kind landlord.')
        self.assertContains(detail, 'r***t')   # rv_tenant shortened
        self.assertNotContains(detail, 'rv_tenant')
        self.assertContains(Client().get(reverse('properties:list')), '★ 4.0 (1)')
        from apps.notifications.models import Notification
        self.assertTrue(Notification.objects.filter(user=self.landlord, kind='new_review').exists())
        self.assertNotContains(tenant.get(reverse('bookings:my_bookings')), 'Rate this home')

    def test_others_and_current_tenants_cannot_review(self):
        self._post(self._login('rv_other'))
        self.assertEqual(self.prop.reviews.count(), 0)
        from datetime import timedelta
        from django.utils import timezone
        self.tenancy.end_date = timezone.localdate() + timedelta(days=30)
        self.tenancy.status = 'active'
        self.tenancy.save()
        self._post(self._login('rv_tenant'))
        self.assertEqual(self.prop.reviews.count(), 0)

    def test_landlord_replies_once_and_hidden_reviews_disappear(self):
        self._post(self._login('rv_tenant'))
        review = self.prop.reviews.get()
        landlord = self._login('rv_landlord')
        reply_url = reverse('properties:reply_review', args=[review.id])
        self._login('rv_other').post(reply_url, {'reply': 'not mine'})
        landlord.post(reply_url, {'reply': 'Thank you for staying!'})
        landlord.post(reply_url, {'reply': 'second try'})
        review.refresh_from_db()
        self.assertEqual(review.landlord_reply, 'Thank you for staying!')
        review.is_hidden = True
        review.save()
        detail = Client().get(reverse('properties:detail', args=[self.prop.pk]))
        self.assertNotContains(detail, 'Water every day')
        self.assertContains(detail, 'No reviews yet')
