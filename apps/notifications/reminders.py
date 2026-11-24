"""Daily reminders: rent coming due, rent overdue, contract ending, and an
invitation to review a home after moving out.

send_due_reminders() is run once a day by `manage.py send_reminders` (also
called from update_tenancy_statuses, which the server's daily timer runs).
Every reminder is recorded in SentReminder first, so running it twice, or
after a few days of downtime, never sends the same reminder twice.

Rent is one bill per contract (Payment, due on the move-in date) - see
apps.bookings.views.approve_booking.
"""
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from .models import Notification, SentReminder

DUE_SOON_DAYS = 3
OVERDUE_REPEAT_DAYS = 7
CONTRACT_NOTICES = (30, 7)   # days before the end date
REVIEW_INVITE_WINDOW = 30    # only invite for tenancies that ended this recently


def _send_once(key, user, kind, body, link):
    try:
        with transaction.atomic():
            SentReminder.objects.create(key=key)
            Notification.notify(user, kind, body, link=link)
    except IntegrityError:
        return False
    return True


def _money(amount):
    return f"TZS {amount:,.0f}"


def _rent_reminders(today, counts):
    from apps.payments.models import Payment

    unpaid = (Payment.objects.filter(status__in=['PENDING', 'OVERDUE'])
              .exclude(booking__status='CANCELLED')
              .select_related('booking__property__landlord', 'booking__tenant'))
    for p in unpaid:
        prop, tenant = p.booking.property, p.booking.tenant
        days = (p.due_date - today).days
        pay_link = reverse('payments:payment_detail', args=[p.id])
        due = date_format(p.due_date, 'j M Y')
        if 1 <= days <= DUE_SOON_DAYS:
            counts['rent'] += _send_once(
                f'rent_due_soon:{p.id}', tenant, 'rent_due_soon',
                f"Rent of {_money(p.amount)} for '{prop.title}' is due on {due}.", pay_link)
        elif days == 0:
            counts['rent'] += _send_once(
                f'rent_due_today:{p.id}', tenant, 'rent_due_today',
                f"Rent of {_money(p.amount)} for '{prop.title}' is due today. "
                "After paying the landlord, mark it as paid with your reference code.", pay_link)
        elif days < 0:
            late = -days
            round_no = (late - 1) // OVERDUE_REPEAT_DAYS  # day 1, 8, 15, ...
            counts['rent'] += _send_once(
                f'rent_overdue:{p.id}:{round_no}', tenant, 'rent_overdue',
                f"Rent of {_money(p.amount)} for '{prop.title}' was due on {due} ({late} day"
                f"{'s' if late != 1 else ''} ago). Pay the landlord and mark it as paid, or message them.",
                pay_link)
            counts['rent'] += _send_once(
                f'rent_overdue_landlord:{p.id}:{round_no}', prop.landlord, 'rent_overdue',
                f"{tenant.username}'s rent of {_money(p.amount)} for '{prop.title}' was due on {due} "
                f"and is not marked as paid yet.", reverse('payments:landlord_payments'))


def _contract_reminders(today, counts):
    from apps.bookings.models import Tenancy

    live = (Tenancy.objects.exclude(status__in=['terminated', 'renewed'])
            .filter(end_date__gte=today, start_date__lte=today, renewal_requested=False)
            .select_related('property', 'tenant'))
    for t in live:
        days_left = (t.end_date - today).days
        # The tightest notice that applies; a missed day still gets it.
        notice = next((n for n in sorted(CONTRACT_NOTICES) if days_left <= n), None)
        if notice is None:
            continue
        counts['contract'] += _send_once(
            f'contract_ending:{t.id}:{notice}', t.tenant, 'contract_ending',
            f"Your contract for '{t.property.title}' ends on {date_format(t.end_date, 'j M Y')} "
            f"({days_left} day{'s' if days_left != 1 else ''} left). Ask to renew now, or plan your move.",
            reverse('bookings:my_contract'))


def _review_invites(today, counts):
    from apps.bookings.models import Tenancy

    finished = (Tenancy.objects.filter(end_date__lt=today,
                                       end_date__gte=today - timezone.timedelta(days=REVIEW_INVITE_WINDOW))
                .exclude(status='renewed')
                .filter(review__isnull=True)
                .select_related('property', 'tenant'))
    for t in finished:
        counts['review'] += _send_once(
            f'review_invite:{t.id}', t.tenant, 'review_invite',
            f"How was your stay at '{t.property.title}'? Rate the home and landlord to help other renters.",
            reverse('properties:write_review', args=[t.id]))


def send_due_reminders(today=None):
    today = today or timezone.localdate()
    counts = {'rent': 0, 'contract': 0, 'review': 0}
    _rent_reminders(today, counts)
    _contract_reminders(today, counts)
    _review_invites(today, counts)
    return counts
