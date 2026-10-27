from django.test import TestCase, Client
from django.urls import reverse

from apps.users.models import User
from apps.properties.models import Property
from .models import Conversation, Message


class MessagingTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username='msg_landlord', password='pw', role='LANDLORD')
        self.tenant = User.objects.create_user(username='msg_tenant', password='pw', role='TENANT')
        self.other_tenant = User.objects.create_user(username='msg_other_tenant', password='pw', role='TENANT')
        self.property = Property.objects.create(
            landlord=self.landlord, title='Messaging Test Property', location='Mwanza',
            property_type='2BR', monthly_rent=100000, distance_from_center_km=1.0,
        )

    def test_tenant_can_start_conversation(self):
        client = Client()
        client.login(username='msg_tenant', password='pw')
        response = client.get(reverse('messaging:start_conversation', kwargs={'property_id': self.property.id}))
        conv = Conversation.objects.get(property=self.property, tenant=self.tenant)
        self.assertRedirects(response, reverse('messaging:thread', kwargs={'conversation_id': conv.id}))
        self.assertEqual(conv.landlord, self.landlord)

    def test_starting_conversation_twice_reuses_it(self):
        client = Client()
        client.login(username='msg_tenant', password='pw')
        client.get(reverse('messaging:start_conversation', kwargs={'property_id': self.property.id}))
        client.get(reverse('messaging:start_conversation', kwargs={'property_id': self.property.id}))
        self.assertEqual(Conversation.objects.filter(property=self.property, tenant=self.tenant).count(), 1)

    def test_landlord_cannot_start_conversation(self):
        client = Client()
        client.login(username='msg_landlord', password='pw')
        client.get(reverse('messaging:start_conversation', kwargs={'property_id': self.property.id}))
        self.assertFalse(Conversation.objects.filter(property=self.property).exists())

    def test_tenant_and_landlord_can_exchange_messages(self):
        conv = Conversation.get_or_create_for(self.property, self.tenant)
        tenant_client = Client()
        tenant_client.login(username='msg_tenant', password='pw')
        tenant_client.post(reverse('messaging:thread', kwargs={'conversation_id': conv.id}), {'body': 'Is it available?'})

        landlord_client = Client()
        landlord_client.login(username='msg_landlord', password='pw')
        landlord_client.post(reverse('messaging:thread', kwargs={'conversation_id': conv.id}), {'body': 'Yes it is!'})

        self.assertEqual(Message.objects.filter(conversation=conv).count(), 2)

    def test_non_participant_cannot_view_thread(self):
        conv = Conversation.get_or_create_for(self.property, self.tenant)
        client = Client()
        client.login(username='msg_other_tenant', password='pw')
        response = client.get(reverse('messaging:thread', kwargs={'conversation_id': conv.id}), follow=True)
        self.assertRedirects(response, reverse('messaging:inbox'))
        self.assertNotIn('Is it available', response.content.decode())

    def test_unread_count_and_mark_read_on_view(self):
        conv = Conversation.get_or_create_for(self.property, self.tenant)
        Message.objects.create(conversation=conv, sender=self.tenant, body='Hello')

        self.assertEqual(conv.unread_count_for(self.landlord), 1)
        self.assertEqual(conv.unread_count_for(self.tenant), 0)  # own message, not unread to self

        landlord_client = Client()
        landlord_client.login(username='msg_landlord', password='pw')
        landlord_client.get(reverse('messaging:thread', kwargs={'conversation_id': conv.id}))

        conv.refresh_from_db()
        self.assertEqual(conv.unread_count_for(self.landlord), 0)

    def test_unread_badge_appears_in_sidebar(self):
        conv = Conversation.get_or_create_for(self.property, self.tenant)
        Message.objects.create(conversation=conv, sender=self.tenant, body='Hello')

        landlord_client = Client()
        landlord_client.login(username='msg_landlord', password='pw')
        response = landlord_client.get(reverse('core:dashboard'))
        self.assertIn('nav-badge', response.content.decode())

    def test_inbox_only_shows_own_conversations(self):
        Conversation.get_or_create_for(self.property, self.tenant)
        client = Client()
        client.login(username='msg_other_tenant', password='pw')
        response = client.get(reverse('messaging:inbox'))
        self.assertNotIn('Messaging Test Property', response.content.decode())
