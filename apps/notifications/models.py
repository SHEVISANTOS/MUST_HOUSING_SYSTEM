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
    ]

    KIND_ICONS = {
        'booking_request': '📝',
        'booking_approved': '✅',
        'booking_declined': '❌',
        'payment_marked_paid': '💰',
        'payment_confirmed': '✅',
        'payment_rejected': '⚠️',
        'account_verified': '🎉',
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
        return cls.objects.create(user=user, kind=kind, body=body, link=link)

    @property
    def icon(self):
        return self.KIND_ICONS.get(self.kind, '🔔')
