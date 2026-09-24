from .models import Tenancy


def sync_tenancy_statuses():
    """
    Brings Tenancy.status in line with what display_status computes live
    from today's date (upcoming/active/ending_soon/ended), and marks a
    Booking COMPLETED once its Tenancy naturally ends. Terminated/renewed
    tenancies are skipped - those are final, explicit-action states, not
    something the calendar should ever move on from.

    Shared by the update_tenancy_statuses management command and the
    Vercel Cron endpoint so both report the same counts without
    duplicating the loop.
    """
    tenancies_updated = 0
    bookings_completed = 0

    live_qs = Tenancy.objects.exclude(status__in=['terminated', 'renewed']).select_related('booking')
    for tenancy in live_qs:
        computed = tenancy.display_status
        if computed == tenancy.status:
            continue

        tenancy.status = computed
        tenancy.save(update_fields=['status', 'updated_at'])
        tenancies_updated += 1

        if computed == 'ended' and tenancy.booking.status not in ('CANCELLED', 'COMPLETED'):
            tenancy.booking.status = 'COMPLETED'
            tenancy.booking.save(update_fields=['status', 'updated_at'])
            bookings_completed += 1

    return {'tenancies_updated': tenancies_updated, 'bookings_completed': bookings_completed}
