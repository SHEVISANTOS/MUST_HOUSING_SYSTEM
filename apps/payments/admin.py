from django.contrib import admin
from django.utils.html import format_html
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'booking_info', 'amount', 'due_date', 'status_badge', 'late_fee')
    list_filter = ('status', 'due_date')
    search_fields = ('booking__id', 'booking__tenant__username', 'booking__property__title')
    ordering = ('-due_date',)
    
    fieldsets = (
        ('Payment Details', {'fields': ('booking', 'amount', 'due_date')}),
        ('Status', {'fields': ('status', 'late_fee')}),
    )
    
    def booking_info(self, obj):
        return f"Booking #{obj.booking.id} - {obj.booking.property.title}"
    booking_info.short_description = 'Booking'
    
    def status_badge(self, obj):
        colors = {'PENDING': '#ffc107', 'COMPLETED': '#28a745', 'OVERDUE': '#dc3545'}
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            f'<span style="color: white; background: {color}; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{obj.status}</span>'
        )
    status_badge.short_description = 'Status'