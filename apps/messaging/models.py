from django.db import models
from apps.properties.models import Property
from apps.users.models import User
from apps.bookings.models import Booking


class Conversation(models.Model):
    """
    One thread per (property, tenant, landlord) - landlord is denormalized
    off property.landlord at creation time rather than derived live, so a
    conversation's landlord stays stable even if the listing later changes
    hands (get_or_create_for always passes property.landlord anyway).
    """
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='conversations')
    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tenant_conversations')
    landlord = models.ForeignKey(User, on_delete=models.CASCADE, related_name='landlord_conversations')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('property', 'tenant', 'landlord')
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.tenant.username} <-> {self.landlord.username} on {self.property.title}"

    @classmethod
    def get_or_create_for(cls, property, tenant, booking=None):
        """The one place a conversation gets created - keeps landlord
        always sourced from property.landlord and booking attached/updated
        when one is known (e.g. once a booking request exists)."""
        conversation, _ = cls.objects.get_or_create(
            property=property, tenant=tenant, landlord=property.landlord,
        )
        if booking and conversation.booking_id != booking.id:
            conversation.booking = booking
            conversation.save(update_fields=['booking', 'updated_at'])
        return conversation

    def other_party(self, user):
        return self.landlord if user.id == self.tenant_id else self.tenant

    def unread_count_for(self, user):
        return self.messages.filter(read_at__isnull=True).exclude(sender=user).count()


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.username}: {self.body[:40]}"
