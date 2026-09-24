from django.contrib import admin
from django.utils.html import format_html
from .models import Booking, Tenancy

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


@admin.register(Tenancy)
class TenancyAdmin(admin.ModelAdmin):
    list_display = ('id', 'property', 'tenant', 'status_badge', 'start_date', 'end_date', 'progress_percent', 'days_remaining')
    list_filter = ('status', 'start_date', 'end_date')
    search_fields = ('property__title', 'tenant__username', 'tenant__email')
    ordering = ('-start_date',)

    # display_status/days_*/months_*/progress_percent/current_month_number/
    # available_from/is_ending_soon are all computed @property on the model
    # (never stored, see Tenancy.display_status) - Django admin renders a
    # model property in readonly_fields via plain getattr(), no extra
    # ModelAdmin method needed for these.
    readonly_fields = (
        'display_status', 'days_total', 'days_elapsed', 'days_remaining',
        'progress_percent', 'months_elapsed', 'months_remaining',
        'current_month_number', 'available_from', 'is_ending_soon',
        'created_at', 'updated_at',
    )

    fieldsets = (
        ('Tenancy', {'fields': ('booking', 'property', 'tenant', 'status', 'display_status')}),
        ('Dates', {'fields': ('start_date', 'end_date', 'duration_months', 'available_from')}),
        ('Progress (computed)', {'fields': (
            'days_total', 'days_elapsed', 'days_remaining', 'progress_percent',
            'months_elapsed', 'months_remaining', 'current_month_number', 'is_ending_soon',
        )}),
        ('Renewal / Termination', {'fields': ('renewal_requested', 'notice_given_at', 'terminated_at', 'termination_reason')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

    def status_badge(self, obj):
        colors = {
            'upcoming': '#17a2b8', 'active': '#28a745', 'ending_soon': '#d4a017',
            'ended': '#6c757d', 'terminated': '#dc3545', 'renewed': '#6c757d',
        }
        color = colors.get(obj.display_status, '#6c757d')
        return format_html(
            '<span style="color: white; background: {}; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color, obj.display_status.upper(),
        )
    status_badge.short_description = 'Status'