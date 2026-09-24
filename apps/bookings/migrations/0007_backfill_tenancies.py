from django.db import migrations


def _duration_months(move_in, move_out):
    months = (move_out.year - move_in.year) * 12 + (move_out.month - move_in.month)
    return max(1, months)


def _initial_status(today, start_date, end_date, ending_soon_days=30):
    if today < start_date:
        return 'upcoming'
    if today > end_date:
        return 'ended'
    if (end_date - today).days <= ending_soon_days:
        return 'ending_soon'
    return 'active'


def backfill_tenancies(apps, schema_editor):
    """
    Create Tenancy records for existing CONFIRMED/PAID bookings so current
    tenants and their properties show up correctly under the new feature.
    Uses plain date arithmetic (not the real model's computed properties,
    per Django's historical-model convention for data migrations) and skips
    - rather than crashes on - any legacy row with unusable dates, since
    this backfill must not block deployment.
    """
    Booking = apps.get_model('bookings', 'Booking')
    Tenancy = apps.get_model('bookings', 'Tenancy')

    from django.utils import timezone
    today = timezone.localdate()

    qs = Booking.objects.filter(status__in=['CONFIRMED', 'PAID']).select_related('property', 'tenant')
    for booking in qs:
        if Tenancy.objects.filter(booking=booking).exists():
            continue

        start_date = booking.move_in_date
        end_date = booking.move_out_date
        if not start_date or not end_date or end_date <= start_date:
            print(f"Skipping backfill for booking #{booking.id}: unusable dates ({start_date} - {end_date})")
            continue

        Tenancy.objects.create(
            booking=booking,
            property=booking.property,
            tenant=booking.tenant,
            start_date=start_date,
            end_date=end_date,
            duration_months=_duration_months(start_date, end_date),
            status=_initial_status(today, start_date, end_date),
        )


def noop_reverse(apps, schema_editor):
    # Reversing this would delete Tenancy rows that may have since accrued
    # real renewal/termination history - not safe to auto-reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0006_tenancy'),
    ]

    operations = [
        migrations.RunPython(backfill_tenancies, noop_reverse),
    ]
