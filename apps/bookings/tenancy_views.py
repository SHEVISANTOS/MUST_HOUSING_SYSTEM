"""
Views specific to Tenancy (occupancy contracts), as opposed to Booking
(the request/approval workflow) - see apps/bookings/models.py:Tenancy for
why the two are kept separate.
"""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponse
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Booking, Tenancy, TerminationRequest

logger = logging.getLogger(__name__)

# Each tenancy's termination requests, newest first, for _termination_panel.html.
_TERMINATIONS = Prefetch(
    'termination_requests',
    queryset=TerminationRequest.objects.select_related('requested_by', 'tenancy__property'),
    to_attr='termination_list',
)



# ==================== TENANT: MY CONTRACT ====================

@login_required
def my_contract(request):
    """
    Tenant dashboard: current contract(s) with progress/payment summary,
    plus a history of past tenancies. A tenant can rent from more than one
    landlord at once, so this supports multiple "current" cards rather than
    assuming exactly one.
    """
    if request.user.role != 'TENANT':
        messages.error(request, "This page is for tenants.")
        return redirect('core:dashboard')

    tenancies = Tenancy.objects.filter(tenant=request.user).select_related(
        'property', 'property__landlord', 'booking'
    ).prefetch_related(_TERMINATIONS).order_by('-start_date')

    current_tenancies = []
    history_tenancies = []
    for t in tenancies:
        if t.display_status in ('upcoming', 'active', 'ending_soon'):
            payments = list(t.booking.payments.all())
            t.payment_paid = sum(p.amount for p in payments if p.status == 'COMPLETED')
            t.payment_outstanding = sum(p.amount for p in payments if p.status in ('PENDING', 'TENANT_PAID', 'OVERDUE'))
            # Someone else lined up for this home after this contract? (never says who)
            t.booked_next = Tenancy.objects.filter(
                property_id=t.property_id, start_date__gt=t.end_date, status__in=_LIVE_STATUSES,
            ).exclude(tenant=request.user).order_by('start_date').first()
            t.pending_interest = None if t.booked_next else Booking.objects.filter(
                property_id=t.property_id, status='PENDING', move_in_date__gt=t.end_date,
            ).exclude(tenant=request.user).order_by('move_in_date').first()
            current_tenancies.append(t)
        else:
            history_tenancies.append(t)

    return render(request, 'bookings/my_contract.html', {
        'current_tenancies': current_tenancies,
        'history_tenancies': history_tenancies,
    })


@login_required
def give_notice(request, tenancy_id):
    """Tenant records their intent to leave. Informational only - does not
    change the tenancy's dates or end it early; it still runs its course."""
    tenancy = get_object_or_404(Tenancy, id=tenancy_id, tenant=request.user)

    if tenancy.display_status not in ('upcoming', 'active', 'ending_soon'):
        messages.warning(request, "Notice can only be given on a live tenancy.")
    elif tenancy.notice_given_at:
        messages.info(request, "You've already given notice for this tenancy.")
    else:
        tenancy.notice_given_at = timezone.now()
        tenancy.save(update_fields=['notice_given_at', 'updated_at'])
        messages.success(request, "✅ Notice to leave recorded. Your landlord has been informed.")

    return redirect('bookings:my_contract')


@login_required
def download_contract_pdf(request, tenancy_id):
    """
    Printable contract summary PDF for either party on the tenancy - reuses
    the same xhtml2pdf + logo + watermark pipeline as the payment documents
    (apps.payments.views) rather than duplicating that setup.
    """
    tenancy = get_object_or_404(
        Tenancy,
        Q(tenant=request.user) | Q(property__landlord=request.user),
        id=tenancy_id,
    )

    from apps.payments.views import PDF_AVAILABLE, _get_logo_data_uri, _get_watermark_data_uri
    if not PDF_AVAILABLE:
        return HttpResponse('PDF generation service is currently unavailable.', status=503)

    from xhtml2pdf import pisa

    payments = list(tenancy.booking.payments.all())
    total_paid = sum(p.amount for p in payments if p.status == 'COMPLETED')
    total_outstanding = sum(p.amount for p in payments if p.status in ('PENDING', 'TENANT_PAID', 'OVERDUE'))

    try:
        from .verification import contract_document_context
        html_string = render_to_string('bookings/tenancy_contract_pdf.html', {
            **contract_document_context(request, tenancy),
            'tenancy': tenancy,
            'total_paid': total_paid,
            'total_outstanding': total_outstanding,
            'now': timezone.now(),
            'logo': _get_logo_data_uri(),
            'watermark': _get_watermark_data_uri(),
        })
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="contract_{tenancy.id}.pdf"'
        pisa_status = pisa.CreatePDF(html_string, dest=response)
        if pisa_status.err:
            logger.error(f"PDF generation failed for contract summary {tenancy_id}")
            return HttpResponse('Error generating contract summary.', status=500)
        return response
    except Exception as e:
        logger.error(f"PDF generation failed for contract summary {tenancy_id}: {e}")
        return HttpResponse('Error generating contract summary.', status=500)


# ==================== LANDLORD: OCCUPANCY ====================

@login_required
def landlord_occupancy(request):
    """Landlord dashboard: occupancy timeline across all their properties."""
    if request.user.role != 'LANDLORD':
        messages.error(request, "This page is for landlords.")
        return redirect('core:dashboard')

    tenancies = Tenancy.objects.filter(property__landlord=request.user).select_related(
        'property', 'tenant', 'booking'
    ).prefetch_related(_TERMINATIONS).order_by('-start_date')

    ending_soon_days = getattr(settings, 'ENDING_SOON_DAYS', 30)

    return render(request, 'bookings/landlord_occupancy.html', {
        'tenancies': tenancies,
        'ending_soon_days': ending_soon_days,
    })


# ==================== EARLY TERMINATION (BOTH PARTIES MUST AGREE) ====================

_LIVE_STATUSES = ('upcoming', 'active', 'ending_soon')


def _party_tenancy(user, tenancy_id):
    """The tenancy, if this user is its tenant or landlord (404 otherwise)."""
    return get_object_or_404(
        Tenancy.objects.select_related('property__landlord', 'tenant', 'booking'),
        Q(tenant=user) | Q(property__landlord=user),
        id=tenancy_id,
    )


def _contract_page(user, tenancy):
    if user.id == tenancy.property.landlord_id:
        return redirect('bookings:landlord_occupancy')
    return redirect('bookings:my_contract')


def _notify_party(user, tenancy, kind, body):
    from apps.notifications.models import Notification
    page = 'bookings:landlord_occupancy' if user.id == tenancy.property.landlord_id else 'bookings:my_contract'
    Notification.notify(user, kind, body, link=reverse(page))


@login_required
def request_termination(request, tenancy_id):
    """Either party asks to end the tenancy early, with a reason. Nothing ends
    until the other party agrees (see respond_termination)."""
    tenancy = _party_tenancy(request.user, tenancy_id)

    if tenancy.display_status not in _LIVE_STATUSES:
        messages.warning(request, "This contract has already ended.")
        return _contract_page(request.user, tenancy)
    pending = tenancy.termination_requests.filter(status='pending').first()
    if pending:
        messages.info(request, "There is already a termination request waiting for an answer.")
        return _contract_page(request.user, tenancy)

    reason = request.POST.get('reason', '').strip()
    if request.method == 'POST':
        if len(reason) < 10:
            messages.error(request, "Please explain the reason (at least 10 characters).")
        else:
            termination = TerminationRequest.objects.create(
                tenancy=tenancy, requested_by=request.user, reason=reason,
            )
            _notify_party(
                termination.responder, tenancy, 'termination_requested',
                f"{request.user.username} asked to end the contract for '{tenancy.property.title}' - please agree or disagree",
            )
            messages.success(request, "Termination requested. The contract continues unless the other party agrees.")
            return _contract_page(request.user, tenancy)

    return render(request, 'bookings/request_termination.html', {
        'tenancy': tenancy,
        'is_landlord': request.user.id == tenancy.property.landlord_id,
        'reason': reason,
    })


@require_POST
@login_required
def respond_termination(request, request_id):
    """The other party agrees (tenancy terminates) or declines (it continues)."""
    action = request.POST.get('action')
    note = request.POST.get('note', '').strip()

    with transaction.atomic():
        termination = get_object_or_404(
            TerminationRequest.objects.select_for_update().select_related(
                'tenancy__property__landlord', 'tenancy__tenant', 'tenancy__booking', 'requested_by',
            ),
            id=request_id,
        )
        tenancy = termination.tenancy
        if request.user.id != termination.responder.id:
            raise Http404  # only the other party can answer - not the requester, not outsiders
        if termination.status != 'pending' or action not in ('agree', 'decline'):
            messages.warning(request, "This request has already been answered.")
            return _contract_page(request.user, tenancy)

        termination.responded_at = timezone.now()
        if tenancy.display_status not in _LIVE_STATUSES:  # ended on its own while waiting
            termination.status = 'withdrawn'
            termination.save()
            messages.info(request, "This contract has already ended, so the request was closed.")
            return _contract_page(request.user, tenancy)
        if action == 'agree':
            termination.status = 'agreed'
            termination.save()
            booking = tenancy.booking
            booking.status = 'CANCELLED'
            booking.save()  # cancellation signal marks the tenancy terminated and frees the property
            tenancy.refresh_from_db()
            tenancy.termination_reason = f"Agreed by both parties: {termination.reason}"[:255]
            tenancy.save(update_fields=['termination_reason'])
        else:
            termination.status = 'declined'
            termination.response_note = note
            termination.save()

    if termination.status == 'agreed':
        _notify_party(termination.requested_by, tenancy, 'termination_agreed',
                      f"{request.user.username} agreed: the contract for '{tenancy.property.title}' is terminated")
        messages.success(request, "You agreed. The contract has been terminated.")
    else:
        _notify_party(termination.requested_by, tenancy, 'termination_declined',
                      f"{request.user.username} disagreed with ending the contract for '{tenancy.property.title}' - it continues")
        messages.info(request, "You disagreed. The contract continues.")
    return _contract_page(request.user, tenancy)


@require_POST
@login_required
def withdraw_termination(request, request_id):
    termination = get_object_or_404(
        TerminationRequest.objects.select_related('tenancy__property__landlord', 'tenancy__tenant'),
        id=request_id, requested_by=request.user, status='pending',
    )
    termination.status = 'withdrawn'
    termination.responded_at = timezone.now()
    termination.save()
    _notify_party(termination.responder, termination.tenancy, 'termination_withdrawn',
                  f"{request.user.username} withdrew the request to end the contract for '{termination.tenancy.property.title}'")
    messages.success(request, "Termination request withdrawn.")
    return _contract_page(request.user, termination.tenancy)


# ==================== PUBLIC: CONTRACT VERIFICATION ====================

def _mask(name):
    return ' '.join(word[0] + '*' * (len(word) - 1) for word in name.split())


def _contract_result(request, tenancy, snapshot=None, status=200, **extra):
    """Render the official record of a contract. `snapshot` = terms recorded
    in a QR token at issue time; differences from today's record are flagged."""
    from urllib.parse import urlparse
    from .verification import confirmation_code

    context = {
        'official_host': urlparse(settings.SITE_URL).netloc or request.get_host(),
        'checked': True,
        **extra,
    }
    if tenancy is None:
        return render(request, 'bookings/verify_contract.html', {**context, 'valid': False}, status=status)

    landlord = tenancy.property.landlord
    context.update({
        'valid': True,
        'tenancy': tenancy,
        'confirmation_code': confirmation_code(tenancy),
        'tenant_masked': _mask(tenancy.tenant.get_full_name() or tenancy.tenant.username),
        'landlord_masked': _mask(landlord.get_full_name() or landlord.username),
        'agreed_termination': tenancy.termination_requests.filter(status='agreed').select_related(
            'tenancy__property').first(),
    })
    if snapshot:
        from datetime import datetime, timezone as dt_timezone
        context.update({
            'issued_at': datetime.fromtimestamp(snapshot['issued'], tz=dt_timezone.utc),
            'snapshot': snapshot,
            'dates_changed': (snapshot['start'], snapshot['end']) != (tenancy.start_date, tenancy.end_date),
            'rent_changed': snapshot['rent'] != tenancy.property.monthly_rent,
        })
    return render(request, 'bookings/verify_contract.html', context)


def _find_tenancy(tenancy_id):
    return Tenancy.objects.select_related(
        'property__landlord', 'tenant', 'booking'
    ).filter(id=tenancy_id).first()


def verify_contract(request, token):
    """QR code on a contract PDF (dispatched from /v/<token>/)."""
    from .verification import read_contract_token
    snapshot = read_contract_token(token)
    if snapshot is None:
        return _contract_result(request, None, status=404)
    tenancy = _find_tenancy(snapshot['id'])
    if tenancy is None:
        return _contract_result(request, None, status=404, deleted=True)
    return _contract_result(request, tenancy, snapshot)


def verify_by_code(request):
    """Public page: type a contract's confirmation code to check it."""
    from .verification import read_confirmation_code
    code = request.GET.get('code', '').strip()
    if not code:
        from urllib.parse import urlparse
        return render(request, 'bookings/verify_contract.html', {
            'official_host': urlparse(settings.SITE_URL).netloc or request.get_host(),
            'checked': False,
        })
    tenancy_id = read_confirmation_code(code)
    tenancy = _find_tenancy(tenancy_id) if tenancy_id else None
    return _contract_result(request, tenancy, status=200 if tenancy else 404, entered_code=code)
