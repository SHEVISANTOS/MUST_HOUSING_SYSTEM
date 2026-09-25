# apps/properties/models.py

from django.db import models
from django.utils import timezone
from apps.users.models import User

class Property(models.Model):
    PROPERTY_TYPES = [
        ('SINGLE', 'Single Room'),
        ('BEDSITTER', 'Bedsitter'),
        ('SELFCON', 'Self Contained'),
        ('1BR', '1 Bedroom'),
        ('2BR', '2 Bedroom'),
        ('3BR', '3 Bedroom'),
        ('4BR', '4+ Bedroom'),
        ('SQ', 'Servant Quarter (SQ)'),
        ('STANDALONE', 'Standalone House'),
        ('APARTMENT', 'Apartment/Flat'),
        ('MAISONETTE', 'Maisonette'),
        ('SHOP', 'Shop/Commercial Space'),
        ('OFFICE', 'Office Space'),
        ('GODOWN', 'Godown/Warehouse'),
        ('GUESTHOUSE', 'Guest House'),
    ]
    
    landlord = models.ForeignKey(User, on_delete=models.CASCADE, related_name='properties')
    title = models.CharField(max_length=200)
    description = models.TextField()
    property_type = models.CharField(max_length=10, choices=PROPERTY_TYPES)
    location = models.CharField(max_length=100)
    distance_from_center_km = models.FloatField(help_text="Distance in km from city center")
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

    def get_current_tenancy(self):
        """
        The Tenancy (apps.bookings.models.Tenancy) occupying this property
        today, if any. Availability is derived from Tenancy dates rather than
        a stored flag, so this - not `is_available` - is the source of truth
        for whether a property is actually occupied right now. Uses the
        reverse `tenancies` relation instead of importing Tenancy directly,
        since apps.bookings.models already imports Property (would be a
        circular import otherwise).

        Prefetch-aware: on a listing page showing many properties, calling
        this naively would be an N+1 query per card. A view can instead do
        `.prefetch_related(Prefetch('tenancies', queryset=..., to_attr=
        'prefetched_tenancies'))` (see apps.properties.views.property_list)
        and this method will filter that already-fetched list in Python
        instead of issuing a new query.
        """
        today = timezone.localdate()
        if hasattr(self, 'prefetched_tenancies'):
            live = [
                t for t in self.prefetched_tenancies
                if t.status not in ('terminated', 'renewed')
                and t.start_date <= today <= t.end_date
            ]
            return min(live, key=lambda t: t.start_date) if live else None
        return self.tenancies.exclude(
            status__in=['terminated', 'renewed']
        ).filter(
            start_date__lte=today, end_date__gte=today
        ).order_by('start_date').first()

    def get_next_available_date(self):
        """The date this property frees up, or None if it's free today."""
        current = self.get_current_tenancy()
        return current.available_from if current else None

    @property
    def is_occupied_now(self):
        return self.get_current_tenancy() is not None

    def __str__(self):
        return f"{self.title} - {self.landlord.username}"

    class Meta:
        verbose_name_plural = "Properties"


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