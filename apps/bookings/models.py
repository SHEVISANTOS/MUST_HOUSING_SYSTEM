from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from apps.properties.models import Property
from apps.users.models import User
from django.utils import timezone
from builtins import property as builtin_property

class Booking(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('CONFIRMED', 'Confirmed'),
        ('PAID', 'Paid & Active'),
        ('CANCELLED', 'Cancelled'),
        ('COMPLETED', 'Completed'),
    ]
    
    # Field Definitions - Ensure all parentheses are closed
    property = models.ForeignKey(
        Property, 
        on_delete=models.CASCADE, 
        related_name='bookings'
    )
    
    tenant = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='bookings'
    )
    
    move_in_date = models.DateField()
    move_out_date = models.DateField()
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='PENDING'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Booking #{self.id} - {self.property.title}"

    # Helper Property to get the latest payment
    @builtin_property
    def payment(self):
        """
        Returns the most recent payment associated with this booking.
        Requires Payment model to have related_name='payments'
        """
        return self.payments.first()


class Tenancy(models.Model):
    """
    Tracks an approved Booking's occupancy period over time: progress,
    renewal and termination. Kept separate from Booking (which models the
    request/approval workflow) rather than extending it, since the two have
    genuinely different lifecycles that happen to share a date range.

    Availability for search/listings is derived from Tenancy dates via
    Property.get_current_tenancy() - not stored on Property.is_available.
    `status` here is only authoritative for the two terminal, non-date-
    derivable states (terminated/renewed); everything else is computed live
    by `display_status` so the UI is never stale between cron runs. The
    stored value is still kept in sync by the daily management command so it
    stays useful for DB-level filtering (admin list_filter, the (property,
    status) index) without needing to compute it row-by-row in Python.
    """
    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('active', 'Active'),
        ('ending_soon', 'Ending Soon'),
        ('ended', 'Ended'),
        ('terminated', 'Terminated'),
        ('renewed', 'Renewed'),
    ]

    # Statuses that represent a live, date-derivable occupancy (as opposed to
    # the two terminal states that are set explicitly by an action, not by
    # the calendar).
    DATE_DERIVED_STATUSES = ('upcoming', 'active', 'ending_soon', 'ended')

    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE, related_name='tenancy'
    )
    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name='tenancies'
    )
    tenant = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='tenancies'
    )

    start_date = models.DateField()
    end_date = models.DateField(db_index=True)
    duration_months = models.PositiveSmallIntegerField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='upcoming')

    renewal_requested = models.BooleanField(default=False)
    notice_given_at = models.DateTimeField(null=True, blank=True)

    terminated_at = models.DateTimeField(null=True, blank=True)
    termination_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['property', 'status']),
        ]
        verbose_name_plural = "Tenancies"

    def __str__(self):
        return f"Tenancy #{self.id} - {self.property.title} ({self.tenant.username})"

    def clean(self):
        errors = {}
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            errors['end_date'] = "End date must be after start date."

        if self.property_id and self.start_date and self.end_date:
            overlap = Tenancy.objects.filter(
                property_id=self.property_id,
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            ).exclude(status__in=['terminated', 'renewed'])
            if self.pk:
                overlap = overlap.exclude(pk=self.pk)
            if overlap.exists():
                errors['__all__'] = "This property already has an overlapping tenancy for those dates."

        if errors:
            raise ValidationError(errors)

    # ---- Computed, render-time properties (never stored) ----

    @builtin_property
    def days_total(self):
        return (self.end_date - self.start_date).days + 1

    @builtin_property
    def days_elapsed(self):
        """
        Inclusive count of days passed, so day 1 (start_date itself) counts
        as 1 elapsed day and day_remaining reaches exactly 0 once the
        tenancy has ended (rather than getting stuck at 1 forever).
        """
        today = timezone.localdate()
        if today < self.start_date:
            return 0
        elapsed = (min(today, self.end_date) - self.start_date).days + 1
        return max(0, min(elapsed, self.days_total))

    @builtin_property
    def days_remaining(self):
        return max(0, self.days_total - self.days_elapsed)

    @builtin_property
    def progress_percent(self):
        if self.days_total <= 0:
            return 0
        return max(0, min(100, round(self.days_elapsed / self.days_total * 100)))

    @builtin_property
    def months_elapsed(self):
        today = timezone.localdate()
        if today < self.start_date:
            return 0
        reference = min(today, self.end_date)
        diff = (reference.year - self.start_date.year) * 12 + (reference.month - self.start_date.month)
        if reference.day < self.start_date.day:
            diff -= 1
        return max(0, min(diff, self.duration_months))

    @builtin_property
    def months_remaining(self):
        return max(0, self.duration_months - self.months_elapsed)

    @builtin_property
    def current_month_number(self):
        """1-indexed month for "Month X of N" display."""
        return min(self.months_elapsed + 1, self.duration_months) if self.duration_months else 1

    @builtin_property
    def available_from(self):
        return self.end_date + timezone.timedelta(days=1)

    @builtin_property
    def display_status(self):
        """
        The status to actually show in the UI. Computed live from today's
        date except for the two terminal states, which are facts set by an
        explicit action (termination/renewal), not derivable from dates.
        """
        if self.status not in self.DATE_DERIVED_STATUSES:
            return self.status
        today = timezone.localdate()
        if today < self.start_date:
            return 'upcoming'
        if today > self.end_date:
            return 'ended'
        ending_soon_days = getattr(settings, 'ENDING_SOON_DAYS', 30)
        if (self.end_date - today).days <= ending_soon_days:
            return 'ending_soon'
        return 'active'

    @builtin_property
    def is_ending_soon(self):
        return self.display_status == 'ending_soon'