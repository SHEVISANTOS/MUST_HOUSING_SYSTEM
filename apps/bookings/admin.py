from django.contrib import admin
from django.utils.html import format_html
from .models import Booking

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'property', 'tenant', 'status_badge', 'move_in_date', 'move_out_date')
    list_filter = ('status', 'move_in_date')
    search_fields = ('property__title', 'tenant__username', 'tenant__email')
    ordering = ('-id',)
    
    fieldsets = (
        ('Booking Info', {'fields': ('property', 'tenant', 'status')}),
        ('Dates', {'fields': ('move_in_date', 'move_out_date')}),
    )
    
    def status_badge(self, obj):
        colors = {'PENDING': '#ffc107', 'CONFIRMED': '#28a745', 'CANCELLED': '#dc3545', 'COMPLETED': '#17a2b8'}
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            f'<span style="color: white; background: {color}; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{obj.status}</span>'
        )
    status_badge.short_description = 'Status'