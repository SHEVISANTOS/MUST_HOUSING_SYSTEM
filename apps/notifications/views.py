from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from .models import Notification


@login_required
def inbox(request):
    """The notification list. Viewing it marks everything as read, the
    same way opening a messaging thread marks its messages read - but the
    template still needs to know which rows *were* unread on load, to show
    them visually distinct, so that's captured before the update."""
    notifications = list(request.user.notifications.all()[:50])
    unread_ids = {n.id for n in notifications if n.read_at is None}

    Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())

    for n in notifications:
        n.was_unread = n.id in unread_ids

    return render(request, 'notifications/inbox.html', {'notifications': notifications})
