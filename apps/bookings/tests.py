from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from apps.users.models import User
from apps.properties.models import Property
from apps.bookings.models import Booking
from apps.payments.models import Payment

class BookingApprovalTests(TestCase):
    def setUp(self):
        self.client = Client()
        # 1. Create Landlord
        self.landlord = User.objects.create_user(
            username='landlord', password='testpassword', role='LANDLORD'
        )
        
        # 2. Create Tenant
        self.tenant = User.objects.create_user(
            username='tenant', password='testpassword', role='TENANT'
        )
        
        # 3. Create Property
        self.property = Property.objects.create(
            landlord=self.landlord,
            title='Nice Bedsitter',
            location='Iyunga',
            property_type='BEDSITTER',
            monthly_rent=100000,
            distance_from_must_km=1.2
        )
        
        # 4. Create Booking for 3 months stay
        self.move_in = timezone.now().date()
        # 3 months in the future:
        self.move_out = self.move_in + timedelta(days=90)
        
        self.booking = Booking.objects.create(
            property=self.property,
            tenant=self.tenant,
            move_in_date=self.move_in,
            move_out_date=self.move_out,
            status='PENDING'
        )

    def test_approve_booking_creates_correct_payment(self):
        """
        Test that when a landlord approves a booking:
        1. Booking status becomes CONFIRMED.
        2. A Payment object is created for the tenant.
        3. The Payment amount is calculated correctly (monthly_rent * duration).
        4. The payment doesn't cause a FieldError due to 'landlord' key.
        """
        # Log in landlord
        self.client.login(username='landlord', password='testpassword')
        
        # Call the approve endpoint
        response = self.client.post(reverse('bookings:approve_booking', kwargs={'booking_id': self.booking.id}))
        
        # Should redirect to landlord bookings page
        self.assertRedirects(response, reverse('bookings:landlord_bookings'))
        
        # Reload booking from DB
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'CONFIRMED')
        
        # Check if payment was created
        payment_exists = Payment.objects.filter(booking=self.booking).exists()
        self.assertTrue(payment_exists)
        
        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.tenant, self.tenant)
        self.assertEqual(payment.status, 'PENDING')
        
        # Calculate expected amount based on stay duration (90 days = 3 months stay)
        move_in = self.booking.move_in_date
        move_out = self.booking.move_out_date
        months_diff = (move_out.year - move_in.year) * 12 + (move_out.month - move_in.month)
        if months_diff <= 0:
            months_diff = 1
        expected_amount = self.property.monthly_rent * months_diff
        
        self.assertEqual(payment.amount, expected_amount)
