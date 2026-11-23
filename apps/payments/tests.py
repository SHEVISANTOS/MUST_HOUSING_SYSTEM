from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from apps.users.models import User
from apps.properties.models import Property
from apps.bookings.models import Booking
from apps.payments.models import Payment
from apps.notifications.models import Notification

class PaymentTests(TestCase):
    def setUp(self):
        """Setup test data before every test"""
        # 1. Create Landlord
        self.landlord = User.objects.create_user(
            username='landlord', password='test123', role='LANDLORD'
        )
        
        # 2. Create Tenant
        self.tenant = User.objects.create_user(
            username='tenant', password='test123', role='TENANT'
        )
        
        # 3. Create Property
        self.property = Property.objects.create(
            landlord=self.landlord,
            title='Test Property',
            location='Mwanza',
            property_type='SINGLE',
            monthly_rent=50000,
            distance_from_center_km=2.5
        )
        
        # 4. Create Booking (Include move_out_date!)
        self.move_in = timezone.now().date()
        self.move_out = self.move_in + timedelta(days=30) # 1 month stay
        
        self.booking = Booking.objects.create(
            property=self.property,
            tenant=self.tenant,
            move_in_date=self.move_in,
            move_out_date=self.move_out, 
            status='CONFIRMED'
        )

    def test_payment_creation(self):
        """Test that a payment can be created for a booking"""
        payment = Payment.objects.create(
            booking=self.booking,
            tenant=self.tenant,
            amount=50000,
            due_date=self.move_in
        )
        
        self.assertEqual(payment.status, 'PENDING')
        self.assertEqual(payment.amount, 50000)

    def test_late_fee_calculation(self):
        """Test late fee logic (example)"""
        # Create a payment that is overdue
        past_date = timezone.now().date() - timedelta(days=10)
        overdue_payment = Payment.objects.create(
            booking=self.booking,
            tenant=self.tenant,
            amount=50000,
            due_date=past_date,
            status='OVERDUE',
            late_fee=5000
        )
        
        self.assertTrue(overdue_payment.late_fee > 0)


class PaymentNotificationTests(TestCase):
    """Each payment action should leave an in-app Notification for whoever
    needs to act on or see it - see apps.notifications.models.Notification."""

    def setUp(self):
        self.landlord = User.objects.create_user(username='pn_landlord', password='pw', role='LANDLORD', is_verified=True)
        self.tenant = User.objects.create_user(username='pn_tenant', password='pw', role='TENANT')
        self.property = Property.objects.create(
            landlord=self.landlord, title='Notif Property', location='Mwanza',
            property_type='SINGLE', monthly_rent=50000, distance_from_center_km=2.5,
        )
        self.move_in = timezone.now().date()
        self.booking = Booking.objects.create(
            property=self.property, tenant=self.tenant,
            move_in_date=self.move_in, move_out_date=self.move_in + timedelta(days=30),
            status='CONFIRMED',
        )

    def test_mark_payment_made_notifies_landlord(self):
        client = Client()
        client.login(username='pn_tenant', password='pw')
        client.post(reverse('payments:mark_payment', kwargs={'booking_id': self.booking.id}), {
            'payment_method': 'CASH', 'payment_reference': 'REF123',
        })
        n = Notification.objects.get(user=self.landlord, kind='payment_marked_paid')
        self.assertIn('pn_tenant', n.body)

    def test_verify_payment_notifies_tenant(self):
        payment = Payment.objects.create(
            booking=self.booking, tenant=self.tenant, amount=50000,
            due_date=self.move_in, status='TENANT_PAID',
        )
        client = Client()
        client.login(username='pn_landlord', password='pw')
        client.post(reverse('payments:verify', kwargs={'payment_id': payment.id}))
        self.assertTrue(Notification.objects.filter(user=self.tenant, kind='payment_confirmed').exists())

    def test_reject_payment_notifies_tenant(self):
        payment = Payment.objects.create(
            booking=self.booking, tenant=self.tenant, amount=50000,
            due_date=self.move_in, status='TENANT_PAID',
        )
        client = Client()
        client.login(username='pn_landlord', password='pw')
        client.post(reverse('payments:reject_payment', kwargs={'payment_id': payment.id}), {
            'rejection_reason': 'Wrong reference code',
        })
        self.assertTrue(Notification.objects.filter(user=self.tenant, kind='payment_rejected').exists())

class DocumentVerificationTests(TestCase):
    """QR codes on payment slips/invoices: signed, unforgeable, and the
    public page shows the official record without contact details."""

    def setUp(self):
        from apps.payments.verification import make_token
        self.make_token = make_token
        landlord = User.objects.create_user(username='dv_landlord', password='pw', role='LANDLORD', is_verified=True)
        self.tenant = User.objects.create_user(
            username='dv_tenant', password='pw', role='TENANT',
            first_name='Amina', last_name='Juma', email='amina@example.com', phone='0712000111',
        )
        prop = Property.objects.create(
            landlord=landlord, title='Verify House', location='Mwanza',
            property_type='SINGLE', monthly_rent=50000, distance_from_center_km=1,
        )
        booking = Booking.objects.create(
            property=prop, tenant=self.tenant, move_in_date=timezone.now().date(),
            move_out_date=timezone.now().date() + timedelta(days=30), status='CONFIRMED',
        )
        self.payment = Payment.objects.create(
            booking=booking, tenant=self.tenant, amount=150000, due_date=timezone.now().date(),
        )

    def _page(self, token):
        return Client().get(reverse('verify_document', kwargs={'token': token}))

    def test_token_round_trip(self):
        from apps.payments.verification import read_token
        data = read_token(self.make_token(self.payment, 'invoice'))
        self.assertEqual(data['p'], self.payment.id.hex)
        self.assertEqual(data['a'], '150000.00')
        self.assertEqual(data['s'], 'PENDING')
        self.assertEqual(data['d'], 'i')

    def test_any_change_to_token_is_rejected(self):
        token = self.make_token(self.payment, 'invoice')
        body, mac = token.rsplit('.', 1)
        forged = [
            body[:23] + 'C' + body[24:] + '.' + mac,   # status -> COMPLETED
            's' + body[1:] + '.' + mac,                # invoice -> slip
            body + '.' + 'A' * 22,                     # guessed signature
            'garbage',
        ]
        for tok in forged:
            response = self._page(tok)
            self.assertEqual(response.status_code, 404, tok)
            self.assertContains(response, 'Not a valid', status_code=404)

    def test_token_signed_with_another_key_is_rejected(self):
        with self.settings(SECRET_KEY='x' * 50):
            token = self.make_token(self.payment, 'invoice')
        self.assertEqual(self._page(token).status_code, 404)

    def test_old_codes_survive_key_rotation(self):
        old_key = 'o' * 50
        with self.settings(SECRET_KEY=old_key):
            token = self.make_token(self.payment, 'invoice')
        with self.settings(SECRET_KEY='n' * 50, SECRET_KEY_FALLBACKS=[old_key]):
            self.assertEqual(self._page(token).status_code, 200)

    def test_genuine_page_shows_record_but_no_contact_details(self):
        response = self._page(self.make_token(self.payment, 'invoice'))
        self.assertContains(response, 'Genuine document')
        self.assertContains(response, 'TZS 150,000')
        self.assertContains(response, 'Verify House')
        self.assertContains(response, 'A**** J***')
        for private in ('Amina', 'amina@example.com', '0712000111'):
            self.assertNotContains(response, private)

    def test_confirmed_payment_shows_as_paid(self):
        self.payment.status = 'COMPLETED'
        self.payment.save()
        self.assertContains(self._page(self.make_token(self.payment, 'invoice')), 'payment confirmed')

    def test_warns_when_amount_changed_after_issue(self):
        token = self.make_token(self.payment, 'invoice')
        self.payment.amount = 300000
        self.payment.save()
        self.assertContains(self._page(token), 'Amount changed since issue')

    def test_warns_when_confirmation_withdrawn_after_issue(self):
        self.payment.status = 'COMPLETED'
        self.payment.save()
        token = self.make_token(self.payment, 'invoice')
        self.payment.status = 'PENDING'
        self.payment.save()
        self.assertContains(self._page(token), 'confirmation withdrawn')

    def test_deleted_payment_is_reported(self):
        token = self.make_token(self.payment, 'invoice')
        self.payment.delete()
        self.assertContains(self._page(token), 'no longer valid')

    def test_qr_points_to_official_site(self):
        from django.test import RequestFactory
        from apps.payments.verification import document_context
        with self.settings(SITE_URL='https://vothousefinding.com'):
            ctx = document_context(RequestFactory().get('/'), self.payment, 'slip')
        self.assertTrue(ctx['verify_url'].startswith('https://vothousefinding.com/v/'))
        self.assertEqual(ctx['verify_host'], 'vothousefinding.com')
        self.assertTrue(ctx['verify_qr'].startswith('data:image/png;base64,'))

    def test_pdfs_download_with_verification(self):
        client = Client()
        client.login(username='dv_tenant', password='pw')
        for name in ('download_slip', 'download_invoice'):
            response = client.get(reverse(f'payments:{name}', kwargs={'payment_id': self.payment.id}))
            self.assertEqual(response.status_code, 200, name)
            self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_check_blocks_public_fallback_key_in_production(self):
        from apps.payments.verification import check_signing_key
        with self.settings(DEBUG=False, SECRET_KEY='fallback-dev-key-replace-in-vercel'):
            self.assertEqual([e.id for e in check_signing_key(None)], ['payments.E001'])
        with self.settings(DEBUG=False, SECRET_KEY='k' * 50):
            self.assertEqual(check_signing_key(None), [])
