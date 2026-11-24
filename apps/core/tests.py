from datetime import date, timedelta

from django.test import TestCase, Client
from django.urls import reverse

from apps.users.models import User
from apps.properties.models import Property
from apps.bookings.models import Booking
from apps.payments.models import Payment
from apps.messaging.models import Conversation, Message


class HealthzTests(TestCase):
    def test_healthz_returns_ok_without_auth(self):
        response = Client().get(reverse('healthz'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})


class LandlordAttentionQueueTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username='attn_landlord', password='pw', role='LANDLORD', is_verified=True)
        self.tenant = User.objects.create_user(username='attn_tenant', password='pw', role='TENANT')
        self.property = Property.objects.create(
            landlord=self.landlord, title='Attention Test Property', location='Mwanza',
            property_type='2BR', monthly_rent=100000, distance_from_center_km=1.0,
        )
        self.client = Client()
        self.client.login(username='attn_landlord', password='pw')

    def test_empty_queue_not_shown(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertNotIn('Needs your attention', response.content.decode())

    def test_pending_booking_shows_in_queue(self):
        Booking.objects.create(
            property=self.property, tenant=self.tenant,
            move_in_date=date.today(), move_out_date=date.today() + timedelta(days=180),
            status='PENDING',
        )
        response = self.client.get(reverse('core:dashboard'))
        body = response.content.decode()
        self.assertIn('Needs your attention', body)
        self.assertIn('Booking request', body)
        self.assertIn(reverse('bookings:landlord_bookings'), body)

    def test_payment_awaiting_verification_shows_in_queue(self):
        booking = Booking.objects.create(
            property=self.property, tenant=self.tenant,
            move_in_date=date.today(), move_out_date=date.today() + timedelta(days=180),
            status='CONFIRMED',
        )
        Payment.objects.create(
            booking=booking, amount=100000, due_date=date.today(), status='TENANT_PAID',
        )
        response = self.client.get(reverse('core:dashboard'))
        body = response.content.decode()
        self.assertIn('Needs your attention', body)
        self.assertIn('Verify payments', body)
        self.assertIn(reverse('payments:landlord_payments'), body)

    def test_unread_message_shows_in_queue(self):
        conv = Conversation.get_or_create_for(self.property, self.tenant)
        Message.objects.create(conversation=conv, sender=self.tenant, body='Is it available?')

        response = self.client.get(reverse('core:dashboard'))
        body = response.content.decode()
        self.assertIn('Needs your attention', body)
        self.assertIn('Open inbox', body)
        self.assertIn(reverse('messaging:inbox'), body)

    def test_tenant_does_not_see_attention_queue(self):
        tenant_client = Client()
        tenant_client.login(username='attn_tenant', password='pw')
        response = tenant_client.get(reverse('core:dashboard'))
        self.assertNotIn('Needs your attention', response.content.decode())


class VerificationQueueTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='vq_admin', password='pw', role='ADMIN', is_superuser=True)
        self.landlord = User.objects.create_user(username='vq_landlord', password='pw', role='LANDLORD', is_verified=False)
        self.tenant = User.objects.create_user(username='vq_tenant', password='pw', role='TENANT', is_verified=False)
        self.client = Client()
        self.client.login(username='vq_admin', password='pw')

    def test_non_admin_cannot_access_queue(self):
        client = Client()
        client.login(username='vq_landlord', password='pw')
        response = client.get(reverse('core:verification_queue'), follow=True)
        self.assertRedirects(response, reverse('core:dashboard'))

    def test_queue_lists_unverified_users(self):
        response = self.client.get(reverse('core:verification_queue'))
        body = response.content.decode()
        self.assertIn('vq_landlord', body)
        self.assertIn('vq_tenant', body)

    def test_verify_user_marks_verified(self):
        response = self.client.post(reverse('core:verify_user', args=[self.landlord.id]), follow=True)
        self.landlord.refresh_from_db()
        self.assertTrue(self.landlord.is_verified)
        self.assertRedirects(response, reverse('core:verification_queue'))

    def test_verify_user_sends_notification(self):
        from apps.notifications.models import Notification
        self.client.post(reverse('core:verify_user', args=[self.landlord.id]))
        self.assertTrue(Notification.objects.filter(user=self.landlord, kind='account_verified').exists())

    def test_verified_user_drops_off_queue(self):
        self.landlord.is_verified = True
        self.landlord.save()
        response = self.client.get(reverse('core:verification_queue'))
        self.assertNotIn('vq_landlord', response.content.decode())

    def test_non_admin_cannot_verify_user(self):
        client = Client()
        client.login(username='vq_tenant', password='pw')
        client.post(reverse('core:verify_user', args=[self.landlord.id]))
        self.landlord.refresh_from_db()
        self.assertFalse(self.landlord.is_verified)


def _boom(request):
    raise RuntimeError('deliberate failure for the 500 page test')


urlpatterns = [
    __import__('django.urls', fromlist=['path']).path('boom/', _boom),
]


class LaunchReadinessTests(TestCase):
    def test_friendly_404(self):
        response = Client().get('/no-such-page-here/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "We couldn't find that page", status_code=404)

    def test_friendly_500_without_leaking_details(self):
        from django.test import override_settings
        with override_settings(ROOT_URLCONF='apps.core.tests', DEBUG=False):
            response = Client(raise_request_exception=False).get('/boom/')
        self.assertEqual(response.status_code, 500)
        body = response.content.decode()
        self.assertIn('Something went wrong on our side', body)
        self.assertNotIn('deliberate failure', body)
        self.assertNotIn('Traceback', body)

    def test_robots_txt_hides_private_pages_but_not_admin_location(self):
        from django.conf import settings
        response = Client().get('/robots.txt')
        self.assertEqual(response['Content-Type'], 'text/plain')
        body = response.content.decode()
        for path in ('/v/', '/verify/', '/payments/', '/messages/'):
            self.assertIn(f'Disallow: {path}', body)
        self.assertNotIn(settings.ADMIN_URL, body)

    def test_listing_form_tells_landlords_area_only(self):
        landlord = User.objects.create_user(username='hint_landlord', password='pw', role='LANDLORD', is_verified=True)
        client = Client()
        client.login(username='hint_landlord', password='pw')
        draft = client.get(reverse('properties:wizard_start'))
        self.assertContains(client.get(draft['Location']), 'include a street or house number')


class LegalPagesTests(TestCase):
    def test_privacy_and_terms_are_public_and_linked(self):
        for name, heading in (('privacy', 'Privacy Policy'), ('terms', 'Terms of Use')):
            response = Client().get(reverse(name))
            self.assertContains(response, f'<h1>{heading}</h1>', html=False)
            self.assertContains(response, 'VOT MWANZA LIMITED')
        register = Client().get(reverse('users:register'))
        self.assertContains(register, reverse('terms'))
        self.assertContains(register, reverse('privacy'))


class SwahiliTests(TestCase):
    def tearDown(self):
        from django.utils import translation
        translation.activate('en')   # a /sw/ request leaves Swahili active for reverse() in later tests

    def setUp(self):
        landlord = User.objects.create_user(username='sw_landlord', password='pw', role='LANDLORD', is_verified=True)
        self.prop = Property.objects.create(landlord=landlord, title='Nyumba Test', location='Ilemela',
                                            property_type='2BR', monthly_rent=150000, distance_from_center_km=1.0)

    def test_english_by_default(self):
        body = Client().get(reverse('properties:list')).content.decode()
        self.assertIn('<html lang="en">', body)
        self.assertIn('Available Houses', body)

    def test_switch_to_swahili_and_back_keeps_page(self):
        c = Client()
        detail = reverse('properties:detail', args=[self.prop.pk])
        sw_detail = f'/sw{detail}'
        response = c.post(reverse('set_language'), {'language': 'sw', 'next': detail})
        self.assertRedirects(response, sw_detail, fetch_redirect_response=False)
        body = c.get(sw_detail).content.decode()
        self.assertIn('<html lang="sw">', body)
        for text in ('Ingia Ili Kupanga', 'Shiriki na marafiki', 'Vyumba 2 vya kulala', 'Taarifa za Kodi'):
            self.assertIn(text, body)
        self.assertIn('Nyumba Test', body)   # landlord's own text is never translated
        # the remembered choice follows English links to the Swahili page
        self.assertRedirects(c.get(detail), sw_detail, fetch_redirect_response=False)
        response = c.post(reverse('set_language'), {'language': 'en', 'next': sw_detail})
        self.assertRedirects(response, detail, fetch_redirect_response=False)
        self.assertIn('Sign in to Book', c.get(detail).content.decode())

    def test_phone_set_to_swahili_is_offered_swahili_and_can_open_it(self):
        en = Client(HTTP_ACCEPT_LANGUAGE='sw').get('/users/register/').content.decode()
        self.assertIn('Create Account', en)      # same URL always gives Google the same page
        self.assertIn('Soma ukurasa huu kwa Kiswahili', en)
        self.assertIn('/sw/users/register/', en)
        body = Client().get('/sw/users/register/').content.decode()
        self.assertIn('Fungua Akaunti', body)
        self.assertIn('Masharti ya Matumizi', body)
        self.assertIn('id="register-form"', body)

    def test_verification_links_and_admin_link_unaffected(self):
        login = Client().get(reverse('users:login')).content.decode()
        from django.conf import settings
        self.assertNotIn(settings.ADMIN_URL, login)   # hidden admin address is not linked publicly
        self.assertNotIn('XXX XXX', login)
        self.assertEqual(Client().get('/verify/').status_code, 200)
        self.assertEqual(Client().get('/sw/verify/').status_code, 200)


class SeoTests(TestCase):
    def tearDown(self):
        from django.utils import translation
        translation.activate('en')   # a /sw/ request leaves Swahili active for reverse() in later tests

    def setUp(self):
        landlord = User.objects.create_user(username='seo_landlord', password='pw', role='LANDLORD', is_verified=True)
        hidden = User.objects.create_user(username='seo_hidden', password='pw', role='LANDLORD')
        self.prop = Property.objects.create(landlord=landlord, title='Lake View Flat', location='Nyegezi, Mwanza',
                                            property_type='APARTMENT', monthly_rent=250000, distance_from_center_km=6,
                                            description='Two rooms near SAUT.')
        self.hidden = Property.objects.create(landlord=hidden, title='Hidden Flat', location='Buswelu',
                                              property_type='1BR', monthly_rent=90000, distance_from_center_km=8)

    def test_home_is_a_real_page_for_visitors(self):
        r = Client().get('/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '<h1>Houses for Rent in Mwanza</h1>', html=False)
        self.assertContains(r, '"@type": "Organization"')
        self.assertContains(r, reverse('area', args=['nyegezi']))
        sw = Client().get('/sw/')
        self.assertContains(sw, 'Nyumba za Kupanga Mwanza')

    def test_listing_has_seo_title_description_hreflang_and_structured_data(self):
        body = Client().get(f'/properties/{self.prop.pk}/').content.decode()
        self.assertIn('<title>Lake View Flat - Apartment/Flat for rent in Nyegezi, Mwanza | VOT House Finding</title>', body)
        self.assertIn('TZS 250,000 per month', body)
        self.assertIn(f'hreflang="sw" href="http://testserver/sw/properties/{self.prop.pk}/"', body)
        self.assertIn('hreflang="x-default"', body)
        self.assertIn('"priceCurrency": "TZS"', body)
        self.assertIn('"addressRegion": "Mwanza"', body)
        sw = Client().get(f'/sw/properties/{self.prop.pk}/').content.decode()
        self.assertIn('ya kupanga', sw)

    def test_area_pages_in_both_languages_and_empty_ones_are_noindex(self):
        r = Client().get('/houses-for-rent/nyegezi/')
        self.assertContains(r, 'Houses for Rent in Nyegezi, Mwanza')
        self.assertContains(r, 'near St. Augustine University (SAUT)')
        self.assertNotContains(r, 'noindex')
        sw = Client().get('/sw/nyumba-za-kupanga/nyegezi/')
        self.assertContains(sw, 'Nyumba za Kupanga Nyegezi, Mwanza')
        self.assertContains(sw, 'hreflang="en" href="http://testserver/houses-for-rent/nyegezi/"')
        empty = Client().get('/houses-for-rent/buswelu/')   # only an unverified landlord's home there
        self.assertContains(empty, 'noindex')
        self.assertNotContains(empty, 'Hidden Flat')
        self.assertEqual(Client().get('/houses-for-rent/atlantis/').status_code, 404)

    def test_sitemap_lists_public_pages_in_both_languages_only(self):
        body = Client().get('/sitemap.xml').content.decode()
        self.assertIn(f'/properties/{self.prop.pk}/</loc>', body)
        self.assertIn(f'/sw/properties/{self.prop.pk}/</loc>', body)
        self.assertIn('/houses-for-rent/nyegezi/</loc>', body)
        self.assertIn('/sw/nyumba-za-kupanga/nyegezi/</loc>', body)
        self.assertNotIn(f'/properties/{self.hidden.pk}/', body)
        self.assertNotIn('buswelu', body)
        self.assertIn('hreflang="sw"', body)
        self.assertIn('/privacy/</loc>', body)
        self.assertNotIn('/sw/privacy/', body)   # legal text is English-only

    def test_robots_points_to_sitemap_and_blocks_private_swahili_pages(self):
        body = Client().get('/robots.txt').content.decode()
        self.assertIn('Sitemap: http://testserver/sitemap.xml', body)
        self.assertIn('Disallow: /sw/bookings/', body)

    def test_search_console_verification_file_is_served(self):
        r = Client().get('/googlea6274c7c17e11000.html')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content.decode().strip(), 'google-site-verification: googlea6274c7c17e11000.html')

    def test_search_console_tag_only_when_configured(self):
        from django.test import override_settings
        self.assertNotContains(Client().get('/'), 'google-site-verification')
        with override_settings(GOOGLE_SITE_VERIFICATION='abc123'):
            self.assertContains(Client().get('/'), '<meta name="google-site-verification" content="abc123">', html=False)

    def test_other_hostnames_redirect_to_the_one_official_address(self):
        from django.test import override_settings
        with override_settings(SITE_URL='https://vothousefinding.com', DEBUG=False,
                               ALLOWED_HOSTS=['vothousefinding.com', 'www.vothousefinding.com']):
            from apps.core.middleware import CanonicalHostMiddleware
            from django.test import RequestFactory
            mw = CanonicalHostMiddleware(lambda r: None)
            resp = mw(RequestFactory().get('/properties/?q=x', HTTP_HOST='www.vothousefinding.com'))
            self.assertEqual(resp.status_code, 301)
            self.assertEqual(resp['Location'], 'https://vothousefinding.com/properties/?q=x')
            self.assertIsNone(mw(RequestFactory().get('/healthz', HTTP_HOST='www.vothousefinding.com')))
            self.assertIsNone(mw(RequestFactory().get('/', HTTP_HOST='vothousefinding.com')))
