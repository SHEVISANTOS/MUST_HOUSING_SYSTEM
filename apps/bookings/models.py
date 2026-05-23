from django.db import models
from apps.properties.models import Property
from apps.users.models import User
from django.utils import timezone
from builtins import property as builtin_property

class Booking(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('CONFIRMED', 'Confirmed'),
        ('PAID', 'Paid & Active'),
        ('CANCELLED', 'Cancelled'),
        ('COMPLETED', 'Completed'),
    ]
    
    # Field Definitions - Ensure all parentheses are closed
    property = models.ForeignKey(
        Property, 
        on_delete=models.CASCADE, 
        related_name='bookings'
    )
    
    tenant = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='bookings'
    )
    
    move_in_date = models.DateField()
    move_out_date = models.DateField()
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='PENDING'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Booking #{self.id} - {self.property.title}"

    # Helper Property to get the latest payment
    @builtin_property
    def payment(self):
        """
        Returns the most recent payment associated with this booking.
        Requires Payment model to have related_name='payments'
        """
        return self.payments.first()