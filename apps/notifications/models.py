from django.db import models
from apps.users.models import User


class Notification(models.Model):
    """In-app notification for a single user - the durable counterpart to
    the dashboard's live-computed 'Needs your attention' queue, so events
    (booking approved, payment verified, account verified, ...) leave a
    record the recipient can see even after the thing that triggered them
    has moved on. Email/SMS delivery is intentionally out of scope - this
    is in-app only, created via the notify() classmethod from the view that
    already handles the underlying event."""

    KIND_CHOICES = [
        ('booking_request', 'New booking request'),
        ('booking_approved', 'Booking approved'),
        ('booking_declined', 'Booking declined'),
        ('payment_marked_paid', 'Payment marked as paid'),
        ('payment_confirmed', 'Payment confirmed'),
        ('payment_rejected', 'Payment not received'),
        ('account_verified', 'Account verified'),
        ('termination_requested', 'Termination requested'),
        ('termination_agreed', 'Termination agreed'),
        ('termination_declined', 'Termination declined'),
        ('termination_withdrawn', 'Termination request withdrawn'),
        ('booking_interest', 'Someone wants to rent your home next'),
        ('property_booked_next', 'Your home is booked after your contract'),
        ('renewal_requested', 'Renewal requested'),
        ('renewal_approved', 'Renewal approved'),
        ('renewal_declined', 'Renewal declined'),
    ]

    KIND_ICONS = {
        'booking_request': '📝',
        'booking_approved': '✅',
        'booking_declined': '❌',
        'payment_marked_paid': '💰',
        'payment_confirmed': '✅',
        'payment_rejected': '⚠️',
        'account_verified': '🎉',
        'termination_requested': '📄',
        'termination_agreed': '🤝',
        'termination_declined': '🚫',
        'termination_withdrawn': '↩️',
        'booking_interest': '👀',
        'property_booked_next': '📅',
        'renewal_requested': '🔄',
        'renewal_approved': '✅',
        'renewal_declined': '❌',
    }

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    body = models.CharField(max_length=255)
    link = models.CharField(max_length=255, blank=True, help_text="Where clicking this notification should go")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.body[:40]}"

    @classmethod
    def notify(cls, user, kind, body, link=''):
        max_len = cls._meta.get_field('body').max_length
        if len(body) > max_len:  # long property titles would otherwise make the INSERT fail
            body = body[:max_len - 1] + '…'
        return cls.objects.create(user=user, kind=kind, body=body, link=link)

    @property
    def icon(self):
        return self.KIND_ICONS.get(self.kind, '🔔')
