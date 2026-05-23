# apps/properties/models.py

from django.db import models
from apps.users.models import User

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
    amenities = models.TextField(help_text="Separate with commas", blank=True, null=True)
    is_available = models.BooleanField(default=True)
    
    # Google Maps Coordinates
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, 
                                   help_text="Latitude for Google Maps")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, 
                                    help_text="Longitude for Google Maps")
    google_maps_link = models.URLField(blank=True, null=True, 
                                         help_text="Direct Google Maps link to property")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def amenities_list(self):
        if not self.amenities:
            return []
        if isinstance(self.amenities, list):
            return [item.strip() for item in self.amenities if item.strip()]
        if isinstance(self.amenities, str):
            return [item.strip() for item in self.amenities.split(',') if item.strip()]
        return []

    def __str__(self):
        return f"{self.title} - {self.landlord.username}"


# Property Images Model
class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='property_images/%Y/%m/%d/')
    caption = models.CharField(max_length=200, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', '-uploaded_at']

    def __str__(self):
        return f"Image for {self.property.title}"
    
    def save(self, *args, **kwargs):
        # If this is marked as primary, unset other primaries
        if self.is_primary:
            PropertyImage.objects.filter(property=self.property, is_primary=True).exclude(id=self.id).update(is_primary=False)
        super().save(*args, **kwargs)