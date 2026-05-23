from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from apps.users.models import User
from apps.properties.models import Property
from apps.bookings.models import Booking
from apps.payments.models import Payment

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
            location='Mbeya',
            property_type='SINGLE',
            monthly_rent=50000,
            distance_from_must_km=2.5
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