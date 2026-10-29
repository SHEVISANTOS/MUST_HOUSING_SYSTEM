from django.utils.functional import SimpleLazyObject


def unread_notification_count(request):
    """{{ unread_notification_count }} for the bell icon badge - lazy so
    pages that don't render it don't pay for the query, same pattern as
    saved_property_ids and unread_message_count."""
    def _compute():
        if not request.user.is_authenticated:
            return 0
        from .models import Notification
        return Notification.objects.filter(user=request.user, read_at__isnull=True).count()

    return {'unread_notification_count': SimpleLazyObject(_compute)}
