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
        response = c.post(reverse('set_language'), {'language': 'sw', 'next': detail})
        self.assertRedirects(response, detail, fetch_redirect_response=False)
        body = c.get(detail).content.decode()
        self.assertIn('<html lang="sw">', body)
        for text in ('Ingia Ili Kupanga', 'Shiriki na marafiki', 'Vyumba 2 vya kulala', 'Taarifa za Kodi'):
            self.assertIn(text, body)
        self.assertIn('Nyumba Test', body)   # landlord's own text is never translated
        c.post(reverse('set_language'), {'language': 'en', 'next': detail})
        self.assertIn('Sign in to Book', c.get(detail).content.decode())

    def test_phone_set_to_swahili_gets_it_automatically(self):
        body = Client(HTTP_ACCEPT_LANGUAGE='sw').get(reverse('users:register')).content.decode()
        self.assertIn('Fungua Akaunti', body)
        self.assertIn('Masharti ya Matumizi', body)
        self.assertIn('id="register-form"', body)

    def test_verification_links_and_admin_link_unaffected(self):
        login = Client().get(reverse('users:login')).content.decode()
        from django.conf import settings
        self.assertNotIn(settings.ADMIN_URL, login)   # hidden admin address is not linked publicly
        self.assertNotIn('XXX XXX', login)
        self.assertEqual(Client(HTTP_ACCEPT_LANGUAGE='sw').get('/verify/').status_code, 200)
