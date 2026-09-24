"""
Views specific to Tenancy (occupancy contracts), as opposed to Booking
(the request/approval workflow) - see apps/bookings/models.py:Tenancy for
why the two are kept separate.
"""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Tenancy
from .services import sync_tenancy_statuses

logger = logging.getLogger(__name__)


@require_GET
def cron_update_tenancy_statuses(request):
    """
    Triggered daily by Vercel Cron (see vercel.json's `crons` entry).
    Vercel automatically sends "Authorization: Bearer <CRON_SECRET>" (from
    the CRON_SECRET env var configured on the Vercel project) when calling a
    scheduled path - that's Vercel's own documented convention, not
    something invented here. Fails closed: if CRON_SECRET isn't configured
    on this deployment, every request is rejected rather than allowed.

    Not behind @login_required - Vercel Cron isn't a logged-in user, and
    this endpoint is not reachable through any link in the site's UI.
    """
    expected = f"Bearer {settings.CRON_SECRET}" if settings.CRON_SECRET else None
    if not expected or request.headers.get('Authorization') != expected:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        result = sync_tenancy_statuses()
    except Exception:
        logger.exception("update_tenancy_statuses cron run failed")
        return JsonResponse({'error': 'Failed to update tenancy statuses'}, status=500)

    return JsonResponse({'status': 'ok', **result})


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
    ).order_by('-start_date')

    current_tenancies = []
    history_tenancies = []
    for t in tenancies:
        if t.display_status in ('upcoming', 'active', 'ending_soon'):
            payments = list(t.booking.payments.all())
            t.payment_paid = sum(p.amount for p in payments if p.status == 'COMPLETED')
            t.payment_outstanding = sum(p.amount for p in payments if p.status in ('PENDING', 'TENANT_PAID', 'OVERDUE'))
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
        html_string = render_to_string('bookings/tenancy_contract_pdf.html', {
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
    ).order_by('-start_date')

    ending_soon_days = getattr(settings, 'ENDING_SOON_DAYS', 30)

    return render(request, 'bookings/landlord_occupancy.html', {
        'tenancies': tenancies,
        'ending_soon_days': ending_soon_days,
    })


@login_required
def terminate_tenancy(request, tenancy_id):
    """
    Landlord ends a tenancy early with a reason. Routed through the same
    "cancel the booking" mechanism the rest of the app uses (see
    apps.bookings.signals) rather than mutating Tenancy directly, so there
    is exactly one place that decides what happens when a booking ends -
    the landlord-supplied reason is applied as a follow-up update.
    """
    if request.user.role != 'LANDLORD':
        messages.error(request, "Unauthorized access.")
        return redirect('core:dashboard')

    tenancy = get_object_or_404(Tenancy, id=tenancy_id, property__landlord=request.user)

    if tenancy.display_status in ('ended', 'terminated', 'renewed'):
        messages.warning(request, "This tenancy has already ended.")
        return redirect('bookings:landlord_occupancy')

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip() or 'Terminated early by landlord'

        booking = tenancy.booking
        booking.status = 'CANCELLED'
        booking.save()  # triggers the cancellation signal -> tenancy becomes 'terminated'

        tenancy.refresh_from_db()
        tenancy.termination_reason = reason
        tenancy.save(update_fields=['termination_reason'])

        messages.success(request, "Tenancy terminated.")
        return redirect('bookings:landlord_occupancy')

    return render(request, 'bookings/terminate_tenancy.html', {'tenancy': tenancy})
