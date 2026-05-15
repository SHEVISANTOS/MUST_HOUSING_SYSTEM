from django.db import models
from apps.users.models import User
from django.utils import timezone

created_at = models.DateTimeField(default=timezone.now)
updated_at = models.DateTimeField(auto_now=True)

class Property(models.Model):
    PROPERTY_TYPES = [
        ('SINGLE', 'Single Room'),
        ('BEDSITTER', 'Bedsitter'),
        ('1BR', '1 Bedroom'),
        ('2BR', '2 Bedroom'),
    ]
    landlord = models.ForeignKey(User, on_delete=models.CASCADE, related_name='properties')
    title = models.CharField(max_length=200)
    description = models.TextField()
    property_type = models.CharField(max_length=10, choices=PROPERTY_TYPES)
    location = models.CharField(max_length=100)
    distance_from_must_km = models.FloatField(help_text="Distance in km from MUST campus")
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2)
    amenities = models.TextField(help_text="Separate with commas (e.g., water, electricity, wifi)")
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def amenities_list(self):
        """Convert amenities to proper list format for display"""
        if not self.amenities:
            return []
        
        # If amenities is already a list
        if isinstance(self.amenities, list):
            return [item.strip() for item in self.amenities if item.strip()]
        
        # If amenities is a string (comma-separated)
        if isinstance(self.amenities, str):
            return [item.strip() for item in self.amenities.split(',') if item.strip()]
        
        return []

    def __str__(self):
        return self.title
