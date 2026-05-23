from django.contrib import admin
from .models import Property, PropertyImage

# ✅ INLINE: Allows adding images directly on the Property form
class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 1
    fields = ('image', 'caption', 'is_primary')
    readonly_fields = ('uploaded_at',)
    classes = ('collapse',)  # Keeps the form clean, expand when needed

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('title', 'landlord', 'property_type', 'monthly_rent', 'location', 'is_available', 'created_at')
    list_filter = ('property_type', 'is_available', 'landlord', 'created_at')
    search_fields = ('title', 'location', 'description', 'landlord__username')
    list_editable = ('is_available',)
    readonly_fields = ('created_at', 'updated_at')
    
    # ✅ LINK INLINE TO PROPERTY ADMIN
    inlines = [PropertyImageInline]
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('landlord', 'title', 'description'),
            'description': 'Enter core property details'
        }),
        ('Location & Coordinates', {
            'fields': ('location', 'latitude', 'longitude', 'google_maps_link'),
            'description': 'Physical address and Google Maps data',
            'classes': ('collapse',)
        }),
        ('Details & Pricing', {
            'fields': ('property_type', 'monthly_rent', 'distance_from_must_km', 'amenities'),
            'description': 'Specifications, rent, and amenities'
        }),
        ('Status & Timestamps', {
            'fields': ('is_available', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    help_texts = {
        'location': "Full area/address (e.g., 'Iyunga, Mbeya')",
        'amenities': "Separate with commas: water, electricity, wifi, parking",
        'distance_from_must_km': "Distance from MUST campus in kilometers",
    }