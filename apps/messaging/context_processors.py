from django.utils.functional import SimpleLazyObject


def unread_message_count(request):
    """{{ unread_message_count }} for the sidebar's Messages badge - lazy
    so pages that don't render the sidebar badge don't pay for the query
    (in practice the sidebar always renders it, but this keeps the cost
    opt-in and consistent with saved_property_ids)."""
    def _compute():
        if not request.user.is_authenticated:
            return 0
        from django.db.models import Q
        from .models import Message
        return Message.objects.filter(
            Q(conversation__tenant=request.user) | Q(conversation__landlord=request.user),
            read_at__isnull=True,
        ).exclude(sender=request.user).count()

    return {'unread_message_count': SimpleLazyObject(_compute)}
