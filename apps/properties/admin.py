from django.contrib import admin
from .models import Property

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('title', 'landlord', 'location', 'property_type', 'monthly_rent', 'is_available')
    list_filter = ('property_type', 'is_available', 'location')
    search_fields = ('title', 'description', 'location', 'landlord__username')
    ordering = ('-id',)
    
    fieldsets = (
        ('Property Details', {'fields': ('title', 'description', 'property_type', 'location', 'distance_from_must_km')}),
        ('Pricing', {'fields': ('monthly_rent', 'amenities')}),
        ('Status', {'fields': ('landlord', 'is_available')}),
    )