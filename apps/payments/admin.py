from django.contrib import admin
from django.utils.html import format_html
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    # ✅ list_display shows custom badge
    list_display = ('short_id', 'booking_info', 'amount', 'due_date', 'status_badge', 'late_fee')
    list_filter = ('status', 'due_date', 'payment_method')
    search_fields = ('booking__id', 'booking__tenant__username', 'booking__property__title', 'payment_reference')
    ordering = ('-due_date',)
    
    # ❌ REMOVED: list_editable = ('status',)  # Can't edit a field not in list_display
    
    fieldsets = (
        ('Payment Details', {'fields': ('booking', 'amount', 'due_date', 'paid_date')}),
        ('Status & Fees', {'fields': ('status', 'late_fee', 'payment_method', 'payment_reference')}),
        ('Proof & Notes', {'fields': ('payment_proof', 'payment_notes'), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at', 'tenant_paid_at', 'landlord_confirmed_at'), 'classes': ('collapse',)}),
    )
    
    readonly_fields = ('created_at', 'updated_at', 'tenant_paid_at', 'landlord_confirmed_at')
    
    def short_id(self, obj):
        return f"#{str(obj.id)[:8]}"
    short_id.short_description = 'ID'
    
    def booking_info(self, obj):
        return f"#{obj.booking.id} - {obj.booking.property.title}"
    booking_info.short_description = 'Booking'
    booking_info.admin_order_field = 'booking__property__title'
    
    def status_badge(self, obj):
        """Display status with colored badge"""
        colors = {
            'PENDING': '#ffc107',
            'TENANT_PAID': '#17a2b8',
            'COMPLETED': '#28a745',
            'OVERDUE': '#dc3545',
            'CANCELLED': '#6c757d',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="color: white; background: {}; padding: 4px 12px; border-radius: 4px; font-weight: 500; font-size: 0.85rem;">{}</span>',
            color,
            obj.status
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'