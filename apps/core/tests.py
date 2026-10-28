from datetime import date, timedelta

from django.test import TestCase, Client
from django.urls import reverse

from apps.users.models import User
from apps.properties.models import Property
from apps.bookings.models import Booking
from apps.payments.models import Payment
from apps.messaging.models import Conversation, Message


class LandlordAttentionQueueTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username='attn_landlord', password='pw', role='LANDLORD')
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
