from django.core.management.base import BaseCommand
from apps.payments.models import Payment
from apps.bookings.models import Booking
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Automated rent control: checks overdue payments, applies late fees, cancels expired bookings'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        overdue = Payment.objects.filter(status='PENDING', due_date__lt=today)

        for payment in overdue:
            days_late = (today - payment.due_date).days
            # 5% late fee per week
            payment.late_fee = payment.amount * 0.05 * (days_late // 7)
            payment.status = 'OVERDUE'
            payment.save()

            # Auto-cancel booking if > 14 days overdue
            if days_late > 14:
                booking = payment.booking
                booking.status = 'CANCELLED'
                booking.save()
                self.stdout.write(self.style.WARNING(
                    f"Cancelled booking #{booking.id} ({booking.property.title}) - {days_late} days overdue"
                ))

        self.stdout.write(self.style.SUCCESS(f"Processed {overdue.count()} overdue payments"))