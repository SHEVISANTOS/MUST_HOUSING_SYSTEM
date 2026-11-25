from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from .models import Property, PropertyImage, PropertyReview, SavedProperty

# ✅ INLINE: Allows adding images directly on the Property form
class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 1
    fields = ('image', 'caption', 'is_primary')
    readonly_fields = ('uploaded_at',)
    classes = ('collapse',)  # Keeps the form clean, expand when needed

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    """Deleting a listing here only removes it from the site: its landlord
    keeps read-only access to its bookings, contracts and payments for
    DELETED_PROPERTY_RETENTION_DAYS, then the daily job erases it. Deleting
    an already-removed listing erases it immediately."""
    list_display = ('title', 'landlord', 'property_type', 'monthly_rent', 'location', 'is_available', 'removed_until', 'created_at')
    list_filter = (('deleted_at', admin.EmptyFieldListFilter), 'property_type', 'is_available', 'landlord', 'created_at')
    delete_confirmation_template = 'admin/properties/property/remove_confirmation.html'
    actions = ['remove_selected', 'restore_selected']

    def get_queryset(self, request):
        qs = Property.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        return qs.order_by(*ordering) if ordering else qs

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop('delete_selected', None)   # would erase records at once; use "Remove" instead
        return actions

    @admin.display(description='Removed (records kept until)', ordering='deleted_at')
    def removed_until(self, obj):
        return obj.records_until.strftime('%d %b %Y') if obj.is_removed else '-'

    def render_delete_form(self, request, context):
        context['retention_days'] = settings.DELETED_PROPERTY_RETENTION_DAYS
        return super().render_delete_form(request, context)

    def delete_model(self, request, obj):
        if obj.is_removed:
            super().delete_model(request, obj)   # second delete: erase for good
        else:
            obj.remove()

    def response_delete(self, request, obj_display, obj_id):
        prop = Property.all_objects.filter(pk=obj_id).first()
        if prop is None:
            return super().response_delete(request, obj_display, obj_id)
        self.message_user(request, f'"{obj_display}" was removed from the site. Its landlord can still open its '
                                   f'records until {prop.records_until:%d %b %Y}.')
        return HttpResponseRedirect(reverse('admin:properties_property_changelist'))

    @admin.action(description='Remove from site (landlord keeps records for a while)')
    def remove_selected(self, request, queryset):
        todo = [p for p in queryset if not p.is_removed]
        for prop in todo:
            prop.remove()
        self.message_user(request, f'{len(todo)} listing(s) removed. Their landlords keep their records for '
                                   f'{settings.DELETED_PROPERTY_RETENTION_DAYS} days.')

    @admin.action(description='Restore removed listings (they come back switched off)')
    def restore_selected(self, request, queryset):
        todo = [p for p in queryset if p.is_removed]
        for prop in todo:
            prop.restore()
        self.message_user(request, f'{len(todo)} listing(s) restored. They stay hidden until their landlord switches them on.')
    search_fields = ('title', 'location', 'description', 'landlord__username')
    list_editable = ('is_available',)
    readonly_fields = ('created_at', 'updated_at', 'deleted_at')
    
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
            'fields': ('property_type', 'monthly_rent', 'distance_from_center_km', 'amenities'),
            'description': 'Specifications, rent, and amenities'
        }),
        ('Status & Timestamps', {
            'fields': ('is_available', 'deleted_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    help_texts = {
        'location': "Full area/address (e.g., 'Ilemela, Mwanza')",
        'amenities': "Separate with commas: water, electricity, wifi, parking",
        'distance_from_center_km': "Distance from city center in kilometers",
    }


@admin.register(SavedProperty)
class SavedPropertyAdmin(admin.ModelAdmin):
    list_display = ('user', 'property', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'property__title')
    readonly_fields = ('created_at',)

@admin.register(PropertyReview)
class PropertyReviewAdmin(admin.ModelAdmin):
    list_display = ('property', 'tenant', 'home_rating', 'landlord_rating', 'is_hidden', 'created_at')
    list_filter = ('is_hidden', 'home_rating')
    list_editable = ('is_hidden',)
    search_fields = ('property__title', 'tenant__username', 'comment')
    readonly_fields = ('tenancy', 'property', 'tenant', 'created_at', 'replied_at')
