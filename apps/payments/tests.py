from django.test import TestCase
from django.utils import timezone
from apps.payments.models import Payment
from apps.bookings.models import Booking
from datetime import timedelta

class RentAutomationTest(TestCase):
    def test_late_fee_calculation(self):
        booking = Booking.objects.create(tenant_id=1, property_id=1, move_in_date=timezone.now().date(), status='CONFIRMED')
        payment = Payment.objects.create(booking=booking, amount=100000, due_date=timezone.now().date() - timedelta(days=10))
        
        # Simulate cron run
        from apps.payments.management.commands.check_overdue_rent import Command
        Command().handle()
        
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'OVERDUE')
        self.assertGreater(payment.late_fee, 0)