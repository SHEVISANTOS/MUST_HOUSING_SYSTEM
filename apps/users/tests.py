from django.test import TestCase, Client
from django.urls import reverse

from apps.users.models import User
from apps.properties.models import Property


class NextRedirectTests(TestCase):
    """
    Login/registration must carry a `next` param through and redirect back
    to it afterwards (e.g. so "Sign in to book" actually lands a visitor
    back on the booking form) - with an open-redirect guard, and a special
    case for a landlord registering via a booking-related next.
    """

    def setUp(self):
        self.landlord = User.objects.create_user(username='nr_landlord', password='pw', role='LANDLORD')
        self.tenant = User.objects.create_user(username='nr_tenant', password='pw', role='TENANT')
        self.property = Property.objects.create(
            landlord=self.landlord, title='Next Redirect Property', location='Mwanza',
            property_type='2BR', monthly_rent=100000, distance_from_center_km=1.0,
        )
        self.booking_url = reverse('bookings:create_booking', kwargs={'property_id': self.property.id})

    def test_login_with_valid_next_redirects_back(self):
        client = Client()
        response = client.post(
            f"{reverse('users:login')}?next={self.booking_url}",
            {'username': 'nr_tenant', 'password': 'pw', 'next': self.booking_url},
        )
        self.assertRedirects(response, self.booking_url)

    def test_login_shows_welcome_back_message_for_booking_next(self):
        client = Client()
        response = client.post(
            f"{reverse('users:login')}?next={self.booking_url}",
            {'username': 'nr_tenant', 'password': 'pw', 'next': self.booking_url},
            follow=True,
        )
        messages = [str(m) for m in response.context[-1]['messages']]
        self.assertTrue(any('Welcome back' in m and self.property.title in m for m in messages))

    def test_login_with_external_next_falls_back_to_dashboard(self):
        client = Client()
        response = client.post(
            f"{reverse('users:login')}?next=https://evil.com",
            {'username': 'nr_tenant', 'password': 'pw', 'next': 'https://evil.com'},
            follow=True,
        )
        self.assertFalse(any('evil.com' in url for url, _ in response.redirect_chain))

    def test_registration_carries_next_through_for_tenant(self):
        client = Client()
        response = client.post(reverse('users:register'), {
            'username': 'nr_newtenant', 'email': 'nt@example.com', 'phone': '',
            'role': 'TENANT', 'password1': 'Str0ngPassw0rd!', 'password2': 'Str0ngPassw0rd!',
            'next': self.booking_url,
        })
        self.assertRedirects(response, self.booking_url)

    def test_registration_as_landlord_with_booking_next_goes_to_dashboard(self):
        client = Client()
        response = client.post(reverse('users:register'), {
            'username': 'nr_newlandlord', 'email': 'nl@example.com', 'phone': '',
            'role': 'LANDLORD', 'password1': 'Str0ngPassw0rd!', 'password2': 'Str0ngPassw0rd!',
            'next': self.booking_url,
        }, follow=True)
        # Landed on the dashboard route, not the booking form
        self.assertNotIn((self.booking_url, 302), response.redirect_chain)
        messages = [str(m) for m in response.context[-1]['messages']]
        self.assertTrue(any('landlord' in m.lower() and 'dashboard' in m.lower() for m in messages))

    def test_registration_with_external_next_is_ignored(self):
        client = Client()
        response = client.post(reverse('users:register'), {
            'username': 'nr_newtenant2', 'email': 'nt2@example.com', 'phone': '',
            'role': 'TENANT', 'password1': 'Str0ngPassw0rd!', 'password2': 'Str0ngPassw0rd!',
            'next': 'https://evil.com',
        }, follow=True)
        self.assertFalse(any('evil.com' in url for url, _ in response.redirect_chain))
