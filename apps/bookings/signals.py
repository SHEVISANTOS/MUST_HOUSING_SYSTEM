from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
# Absolute import - see the comment in apps.py's ready() for why.
from apps.bookings.models import Booking, Tenancy


@receiver(post_save, sender=Booking)
def terminate_tenancy_on_cancellation(sender, instance, **kwargs):
    """
    Whenever a Booking is saved with status='CANCELLED', terminate any live
    Tenancy tied to it. The property becomes available again automatically
    as a side effect - Property.get_current_tenancy() excludes terminated
    tenancies, so no separate "make it available" step is needed.

    Implemented as a signal (rather than inline in whichever view sets the
    status) so this holds true regardless of where a booking gets cancelled
    from - a view, the admin, or a future feature - without having to find
    every call site.
    """
    if instance.status != 'CANCELLED':
        return

    Tenancy.objects.filter(
        booking=instance
    ).exclude(
        status__in=['terminated', 'renewed', 'ended']
    ).update(
        status='terminated',
        terminated_at=timezone.now(),
        termination_reason='Booking cancelled',
    )
