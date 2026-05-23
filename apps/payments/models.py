from django.db import models
from apps.bookings.models import Booking
from apps.users.models import User
from django.utils import timezone
import uuid

class Payment(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('TENANT_PAID', 'Tenant Marked Paid'),
        ('COMPLETED', 'Landlord Confirmed'),
        ('OVERDUE', 'Overdue'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Cash'),
        ('MPESA_DIRECT', 'M-Pesa (Direct)'),
        ('TIGO_PESA', 'Tigo Pesa'),
        ('AIRTEL_MONEY', 'Airtel Money'),
        ('BANK_TRANSFER', 'Bank Transfer'),  
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='payments')  
    
    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tenant_payments', null=True, blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True, null=True)
    payment_reference = models.CharField(max_length=100, blank=True, null=True, help_text="M-Pesa code, Bank Ref, etc.")
    payment_proof = models.ImageField(upload_to='payment_proofs/', blank=True, null=True)
    payment_notes = models.TextField(blank=True, null=True)
    
    tenant_paid_at = models.DateTimeField(null=True, blank=True)
    landlord_confirmed_at = models.DateTimeField(null=True, blank=True)
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)  
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')  
    late_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(default=timezone.now)  
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Payment for Booking #{self.booking.id} - {self.status}"  
    
    def save(self, *args, **kwargs):
        if self.booking and not self.tenant_id:
            self.tenant = self.booking.tenant
        super().save(*args, **kwargs)  
    
    @property
    def is_confirmed(self):
        return self.status == 'COMPLETED'
    
    @property
    def is_overdue(self):
        if self.status in ['COMPLETED', 'TENANT_PAID']:
            return False
        return timezone.now().date() > self.due_date