from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse

from apps.users.models import User
from apps.properties.models import Property
from config.uploads import RandomName, validate_image_upload


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
            'username': 'nr_newtenant', 'email': 'nt@example.com', 'phone': '0712345678',
            'role': 'TENANT', 'password1': 'Str0ngPassw0rd!', 'password2': 'Str0ngPassw0rd!',
            'next': self.booking_url,
        })
        self.assertRedirects(response, self.booking_url)

    def test_registration_as_landlord_with_booking_next_goes_to_dashboard(self):
        client = Client()
        response = client.post(reverse('users:register'), {
            'username': 'nr_newlandlord', 'email': 'nl@example.com', 'phone': '0712345679',
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
            'username': 'nr_newtenant2', 'email': 'nt2@example.com', 'phone': '0712345680',
            'role': 'TENANT', 'password1': 'Str0ngPassw0rd!', 'password2': 'Str0ngPassw0rd!',
            'next': 'https://evil.com',
        }, follow=True)
        self.assertFalse(any('evil.com' in url for url, _ in response.redirect_chain))


class RegistrationSecurityTests(TestCase):
    """
    Self-registration must never be able to grant ADMIN - the UI's role
    dropdown only offers Tenant/Landlord, but that's not a security
    boundary on its own (CustomUserCreationForm's choices are what actually
    enforce it server-side; see apps/users/forms.py).
    """

    def test_posting_role_admin_is_rejected(self):
        client = Client()
        response = client.post(reverse('users:register'), {
            'username': 'would_be_admin', 'email': 'wba@example.com', 'phone': '',
            'role': 'ADMIN', 'password1': 'Str0ngPassw0rd!', 'password2': 'Str0ngPassw0rd!',
        })
        self.assertEqual(response.status_code, 200)  # re-renders the form, no redirect
        self.assertFalse(User.objects.filter(username='would_be_admin').exists())
        self.assertIn('role', response.context['form'].errors)


# A minimal valid 1x1 transparent PNG - validate_image_upload checks real
# file extension/size, not content, but this stands in for "a real upload".
_ONE_PX_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDATx\x9cc\x64'
    b'\x60\x00\x00\x00\x05\x00\x01\x1f\xcd\xbb\xd3\x00\x00\x00\x00IEND\xaeB`\x82'
)


class UploadValidationTests(TestCase):
    """config.uploads - shared by User.profile_picture, Payment.payment_proof
    and PropertyImage.image. Recovered from a server-only, never-committed
    change (2026-11-03) and wired back into the three models here - these
    tests cover the module directly rather than duplicating per-model."""

    def test_accepts_allowed_extensions_under_size_limit(self):
        for ext in ('.jpg', '.jpeg', '.png', '.webp'):
            f = SimpleUploadedFile(f'photo{ext}', _ONE_PX_PNG, content_type='image/png')
            validate_image_upload(f)  # must not raise

    def test_rejects_disallowed_extension(self):
        f = SimpleUploadedFile('payload.svg', _ONE_PX_PNG, content_type='image/svg+xml')
        with self.assertRaises(ValidationError):
            validate_image_upload(f)

    def test_rejects_oversized_file(self):
        oversized = _ONE_PX_PNG + b'\x00' * (10 * 1024 * 1024)
        f = SimpleUploadedFile('big.jpg', oversized, content_type='image/jpeg')
        with self.assertRaises(ValidationError):
            validate_image_upload(f)

    def test_random_name_keeps_extension_and_date_formats_folder(self):
        namer = RandomName('profile_pics/%Y/%m')
        path = namer(None, 'my photo.JPG')
        self.assertTrue(path.endswith('.jpg'))
        self.assertNotIn('my photo', path)  # original name is discarded, not just sanitized
        from django.utils import timezone
        self.assertTrue(path.startswith(timezone.now().strftime('profile_pics/%Y/%m/')))

    def test_random_name_equality_is_by_folder_not_identity(self):
        # Must hold, or Django's migration autodetector sees a "change"
        # every time it compares the model field to the migration state,
        # even when neither actually changed - exactly the drift this
        # module's recovery was fixing.
        self.assertEqual(RandomName('profile_pics'), RandomName('profile_pics'))
        self.assertNotEqual(RandomName('profile_pics'), RandomName('payment_proofs/%Y/%m'))

    def test_profile_picture_upload_gets_randomized_path(self):
        user = User.objects.create_user(username='upload_user', password='pw', role='TENANT')
        user.profile_picture = SimpleUploadedFile('me.png', _ONE_PX_PNG, content_type='image/png')
        user.save()
        self.assertNotIn('me.png', user.profile_picture.name)
        self.assertTrue(user.profile_picture.name.startswith('profile_pics/'))
        user.profile_picture.delete(save=False)

    def test_profile_picture_field_rejects_disallowed_type(self):
        # Exercises the validator exactly as Django wires it on the field,
        # scoped to just this field (not full_clean(), which would also
        # validate unrelated required fields like password).
        bad_file = SimpleUploadedFile('virus.exe', b'not an image', content_type='application/octet-stream')
        field = User._meta.get_field('profile_picture')
        with self.assertRaises(ValidationError):
            for validator in field.validators:
                validator(bad_file)


class PhoneNumberTests(TestCase):
    """A spaced number like '+255 712 345 678' (16 chars) used to overflow
    User.phone's 15-char column and 500 the profile page."""

    def setUp(self):
        self.user = User.objects.create_user(username='phone_user', password='pw', role='TENANT', email='pu@example.com')
        self.client = Client()
        self.client.login(username='phone_user', password='pw')

    def test_profile_accepts_spaced_international_number(self):
        response = self.client.post(reverse('core:profile'), {'email': 'pu@example.com', 'phone': '+255 712 345 678'})
        self.assertRedirects(response, reverse('core:profile'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, '+255712345678')

    def test_profile_accepts_dashed_local_number(self):
        self.client.post(reverse('core:profile'), {'email': 'pu@example.com', 'phone': '0712-345-678'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, '0712345678')

    def test_profile_rejects_garbage_without_crashing(self):
        response = self.client.post(reverse('core:profile'), {'email': 'pu@example.com', 'phone': 'call me maybe'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, '')
        messages = [str(m) for m in response.context['messages']]
        self.assertTrue(any('valid phone number' in m for m in messages))

    def test_profile_allows_clearing_phone(self):
        self.user.phone = '0712345678'
        self.user.save()
        self.client.post(reverse('core:profile'), {'email': 'pu@example.com', 'phone': ''})
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, '')

    def test_registration_accepts_spaced_number(self):
        response = Client().post(reverse('users:register'), {
            'username': 'spaced_phone', 'email': 'sp@example.com', 'phone': '+255 712 345 678',
            'role': 'TENANT', 'password1': 'Str0ngPassw0rd!', 'password2': 'Str0ngPassw0rd!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.get(username='spaced_phone').phone, '+255712345678')
